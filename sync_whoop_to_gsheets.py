import click
import logging
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
from whoop_auth import start_auth_web_server, get_valid_whoop_token

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Sync WHOOP activities to Google Sheets."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(sync)

def default_start_date():
    return (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d')

def default_end_date():
    return datetime.today().strftime('%Y-%m-%d')

def parse_whoop_local_datetime(dt_str, timezone_offset):
    dt_utc = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    sign = 1 if timezone_offset[0] == '+' else -1
    hours, minutes = map(int, timezone_offset[1:].split(':'))
    offset = timedelta(hours=hours, minutes=minutes) * sign
    local_tz = timezone(offset)
    return dt_utc.astimezone(local_tz)

def parse_whoop_local_date(start_str, timezone_offset):
    """Parse WHOOP UTC start time and timezone_offset to local date."""
    return parse_whoop_local_datetime(start_str, timezone_offset).date()

def get_running_activities_with_token(access_token, start_date, end_date):
    logger.info(f"Fetching workouts from {start_date} to {end_date} using OAuth token")
    import requests
    url = f"https://api.prod.whoop.com/activities/v1/workouts?start={start_date}&end={end_date}"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch workouts: {resp.status_code} {resp.text}")
        return {}
    workouts = resp.json()
    logger.info(f"Fetched {len(workouts) if workouts else 0} workouts from WHOOP")
    running_per_day = {}
    RUNNING_SPORT_IDS = {0}
    for w in workouts or []:
        if w.get('sport_id') in RUNNING_SPORT_IDS:
            start_dt = parse_whoop_local_datetime(w['start'], w.get('timezone_offset', '+00:00'))
            end_dt = parse_whoop_local_datetime(w['end'], w.get('timezone_offset', '+00:00'))
            duration_min = int((end_dt - start_dt).total_seconds() / 60)
            if duration_min == 0:
                logger.warning(f"Workout {w.get('id')} on {start_dt.date()} has 0 duration!")
            workout_date = start_dt.date()
            running_per_day[workout_date] = running_per_day.get(workout_date, 0) + duration_min
            logger.info(f"Found running workout on {workout_date}: {duration_min} min")
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

    updates = 0
    for date, minutes in running_per_day.items():
        week_monday = get_monday(date)
        day_name = get_day_name(date)
        row_idx = week_row_map.get(week_monday)
        col_idx = day_columns.get(day_name)
        if row_idx and col_idx is not None:
            if minutes > 0:
                logger.info(f"Updating {date} ({day_name}) in week {week_monday}: {minutes} min")
                worksheet.update_cell(row_idx, col_idx+1, minutes)
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
    from datetime import date, timedelta
    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
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