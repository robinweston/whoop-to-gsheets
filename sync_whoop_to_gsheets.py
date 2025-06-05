import os
import click
import logging
from dotenv import load_dotenv
from whoop import WhoopClient
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
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

def get_running_activities(username, password, start_date, end_date):
    logger.info(f"Authenticating with WHOOP as {username}")
    client = WhoopClient(username, password)
    logger.info(f"Fetching workouts from {start_date} to {end_date}")
    workouts = client.get_workout_collection(start_date, end_date)
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
            logger.info(f"Updating {date} ({day_name}) in week {week_monday}: {minutes} min")
            worksheet.update_cell(row_idx, col_idx+1, minutes)
            updates += 1
        else:
            logger.error(f"Could not find cell for {date} ({day_name}) in week starting {week_monday}")
    logger.info(f"Sheet update complete. {updates} cell(s) updated.")
    return updates

@main.command()
@click.option('--start-date', default=default_start_date, show_default='5 days ago', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', default=default_end_date, show_default='today', help='End date (YYYY-MM-DD)')
@click.option('--sheet-name', default='Robin Strength Program', show_default=True, help='Google Sheet name')
@click.option('--creds-path', default='google-creds.json', show_default=True, help='Path to Google service account credentials JSON')
def sync(start_date, end_date, sheet_name, creds_path):
    logger.info(f"Starting sync for {sheet_name} from {start_date} to {end_date}")
    load_dotenv()
    username = os.getenv('WHOOP_USERNAME')
    password = os.getenv('WHOOP_PASSWORD')
    if not username or not password:
        logger.error('WHOOP_USERNAME and WHOOP_PASSWORD must be set in .env')
        return

    running_per_day = get_running_activities(username, password, start_date, end_date)
    if not running_per_day:
        logger.warning('No running workouts found in the given date range.')
        return

    updates = update_running_sheet(sheet_name, creds_path, running_per_day)
    logger.info(f"Updated {updates} running day(s) in the Running sheet.")

if __name__ == "__main__":
    main() 