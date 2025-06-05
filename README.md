# sync-whoop-gsheets

CLI to sync WHOOP running activities to a Google Sheets "Running" tab.

## Features
- Aggregates total running time per day from WHOOP (using local time from WHOOP's timezone offset)
- Updates your Google Sheet's "Running" tab, matching week rows and day columns
- Handles both `YYYY-MM-DD` and `DD/MM/YY` week start formats
- Robust to extra spaces in day-of-week headers
- Defaults to last 14 days, but can be customized

## Setup

1. **Set up your WHOOP credentials:**
   - Create a `.env` file in the project root:
     ```env
     WHOOP_USERNAME="your_whoop_email@example.com"
     WHOOP_PASSWORD="your_whoop_password"
     ```

2. **Set up Google Sheets API:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable the Google Sheets API and Drive API.
   - Create a Service Account and download the credentials JSON file.
   - Share your target Google Sheet with the service account email (as Editor).
   - Place the credentials file as `google-creds.json` in your project root (or specify with `--creds-path`).

3. **Sheet Format:**
   - The first row of the "Running" tab should have headers: `Monday`, `Tuesday`, ..., `Sunday` (case-insensitive, spaces are OK).
   - The first column of each week row should be the Monday date, in either `YYYY-MM-DD` or `DD/MM/YY` format.

## Usage

```sh
uv run sync_whoop_to_gsheets.py
```

### Options
- `--days-ago` Number of days ago to start syncing from (up to today), default: 14
- `--sheet-name` Name of the Google Sheet, default: "Robin Strength Program"
- `--creds-path` Path to Google service account credentials JSON, default: `google-creds.json`

You can override any option, e.g.:
```sh
uv run sync_whoop_to_gsheets.py --days-ago 30
```

## Troubleshooting
- **Sheet not found:**
  - Double-check the sheet name and that you've shared it with your service account email.
- **No running data appears:**
  - Make sure your WHOOP activities are labeled as running (sport_id 0).
- **Could not find cell for ...:**
  - Check that your week start dates and day headers match the expected formats (see above).
  - Remove extra spaces from headers, or let the script handle them.
- **Authentication errors:**
  - Ensure your credentials file is correct and the service account has Editor access.

## License
MIT 