import click
import logging
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone, date
from whoop_auth import start_auth_web_server, get_valid_whoop_token
import requests
import time
import random

logging.basicConfig(level=logging.INFO, force=True)

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, base_delay=1, max_delay=60):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        logger.error(f"Failed after {max_retries} retries: {e}")
                        raise
                    
                    # Calculate delay with exponential backoff and jitter
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Sync WHOOP activities to Google Sheets."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sync)


def parse_whoop_local_datetime(dt_str, timezone_offset):
    dt_utc = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    sign = 1 if timezone_offset[0] == '+' else -1
    hours, minutes = map(int, timezone_offset[1:].split(':'))
    offset = timedelta(hours=hours, minutes=minutes) * sign
    local_tz = timezone(offset)
    return dt_utc.astimezone(local_tz)

def get_running_activities_with_token(access_token, start_date, end_date):
    logger.info(f"Fetching workouts from {start_date} to {end_date} using OAuth token")
    base_url = "https://api.prod.whoop.com/developer/v2/activity/workout"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"start": start_date, "end": end_date, "limit": 25}
    all_workouts = []
    page_count = 0

    while True:
        page_count += 1
        logger.info(f"Requesting page {page_count} with params: {params}")
        resp = requests.get(base_url, headers=headers, params=params)
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch workouts: {resp.status_code} {resp.text}")
        data = resp.json()
        workouts = data.get("records", [])
        logger.info(f"Fetched {len(workouts)} records on page {page_count}")
        if workouts:
            ids = [w.get('id') for w in workouts]
            logger.info(f"Record IDs on page {page_count}: {ids}")
        all_workouts.extend(workouts)

        # Check for next_token in the response (WHOOP API uses 'next_token' field)
        next_token = data.get("next_token")
        if not next_token:
            logger.info(f"No more pages available. Completed pagination after {page_count} page(s)")
            break

        # Update params for next request using 'nextToken' parameter (WHOOP API specification)
        params["nextToken"] = next_token
        logger.info(f"Added pagination token for next request: {next_token}")

        # Safety check to prevent infinite loops
        if page_count > 100:  # Reasonable upper limit
            logger.warning(f"Reached maximum page limit ({page_count}). Stopping pagination to prevent infinite loop.")
            break

    logger.info(f"Fetched {len(all_workouts)} workouts from WHOOP across {page_count} page(s)")
    running_per_day = {}

    # Track unique workout IDs during processing
    seen_workout_ids = set()
    
    RUNNING_SPORT_IDS = {0}
    for w in all_workouts:
        workout_id = w.get('id')
        if not workout_id:
            logger.warning(f"Skipping workout with missing ID: {w}")
            continue
        if workout_id in seen_workout_ids:
            logger.warning(f"Skipping duplicate workout ID: {workout_id}")
            continue
        if w.get('sport_id') not in RUNNING_SPORT_IDS:
            continue
            
        start_dt = parse_whoop_local_datetime(w['start'], w.get('timezone_offset', '+00:00'))
        end_dt = parse_whoop_local_datetime(w['end'], w.get('timezone_offset', '+00:00'))
        duration_min = int((end_dt - start_dt).total_seconds() / 60)
        if duration_min == 0:
            logger.warning(f"Workout {w.get('id')} on {start_dt.date()} has 0 duration!")
        workout_date = start_dt.date()

        logger.info(f"Found running workout on {workout_date}: {duration_min} min")
        if workout_date not in running_per_day:
            running_per_day[workout_date] = 0
        running_per_day[workout_date] += duration_min
        logger.info(f"Total running minutes for {workout_date}: {running_per_day[workout_date]}")
        
        # Add to seen IDs after successful processing
        seen_workout_ids.add(workout_id)

    logger.info(f"Aggregated running minutes for {len(running_per_day)} day(s)")
    return running_per_day

def update_running_sheet(sheet_name, creds_path, running_per_day):
    logger.info(f"Authenticating with Google Sheets using creds at {creds_path}")
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)
    logger.info(f"Opening Google Sheet: {sheet_name}")
    sh = gc.open(sheet_name)
    worksheet = sh.worksheet('Running')
    logger.info(f"Accessed 'Running' worksheet")

    all_values = worksheet.get_all_values()
    if not all_values:
        logger.error('Running sheet is empty!')
        return 0
    headers = all_values[0]
    day_columns = {day.strip(): idx for idx, day in enumerate(headers) if day.strip().lower() in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']}
    if not day_columns:
        logger.error('No day-of-week columns found in Running sheet!')
        return 0

    def get_monday(date):
        if isinstance(date, str):
            d = datetime.strptime(date, '%Y-%m-%d').date()
        else:
            d = date  # already a date object
        return d - timedelta(days=d.weekday())
    def get_day_name(date):
        if isinstance(date, str):
            d = datetime.strptime(date, '%Y-%m-%d').date()
        else:
            d = date  # already a date object
        return d.strftime('%A')

    week_row_map = {}
    for i, row in enumerate(all_values[1:], start=2):
        for cell in row:
            try:
                # Try both formats: YYYY-MM-DD and DD/MM/YY
                try:
                    week_monday = datetime.strptime(cell, '%Y-%m-%d').date()
                except ValueError:
                    week_monday = datetime.strptime(cell, '%d/%m/%y').date()
                week_row_map[week_monday] = i
                break
            except Exception:
                continue

    @retry_with_backoff(max_retries=3, base_delay=2, max_delay=30)
    def update_single_cell(row_idx, col_idx, minutes):
        """Update a single cell with retry logic"""
        worksheet.update_cell(row_idx, col_idx+1, minutes)

    updates = 0
    for date, minutes in running_per_day.items():
        week_monday = get_monday(date)
        day_name = get_day_name(date)
        row_idx = week_row_map.get(week_monday)
        col_idx = day_columns.get(day_name)
        if row_idx and col_idx is not None:
            if minutes > 0:
                logger.info(f"Updating {date} ({day_name}) in week {week_monday}: {minutes} min")
                update_single_cell(row_idx, col_idx, minutes)
                updates += 1
            else:
                logger.info(f"Skipping update for {date} ({day_name}) in week {week_monday}: 0 min (cell left blank)")
        else:
            logger.error(f"Could not find cell for {date} ({day_name}) in week starting {week_monday}")
    logger.info(f"Sheet update complete. {updates} cell(s) updated.")
    return updates

@main.command()
@click.option('--days-ago', default=14, show_default=True, help='Number of days ago to start syncing from (up to today)')
@click.option('--sheet-name', help='Google Sheet name')
@click.option('--creds-path', default='google-creds.json', show_default=True, help='Path to Google service account credentials JSON')
@click.option('--token-file', default='whoop-tokens.json', show_default=True, help='Path to WHOOP OAuth token JSON file')
def sync(days_ago, sheet_name, creds_path, token_file):
    logger.info(f"Starting sync for {sheet_name} for the last {days_ago} days")
    access_token = get_valid_whoop_token(token_file=token_file)
    # Use full ISO 8601 UTC date-time strings for WHOOP API
    end_date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    running_per_day = get_running_activities_with_token(access_token, start_date, end_date)
    if not running_per_day:
        logger.warning('No running workouts found in the given date range.')
        return
    updates = update_running_sheet(sheet_name, creds_path, running_per_day)
    logger.info(f"Updated {updates} running day(s) in the Running sheet.")

@main.command(name='auth')
@click.option('--token-file', default='whoop-tokens.json', show_default=True, help='Path to WHOOP OAuth token JSON file')
@click.option('--port', default=5000, show_default=True, help='Port for local HTTPS server')
def whoop_auth(token_file, port):
    """Start a local HTTPS server to obtain WHOOP OAuth tokens and save them to a JSON file."""
    start_auth_web_server(token_file=token_file, port=port)

if __name__ == "__main__":
    main() 