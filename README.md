# sync-whoop-gsheets

CLI to sync WHOOP running activities to a Google Sheets "Running" tab.

## Features
- Aggregates total running time per day from WHOOP (using local time from WHOOP's timezone offset)
- Updates your Google Sheet's "Running" tab, matching week rows and day columns
- Handles both `YYYY-MM-DD` and `DD/MM/YY` week start formats
- Robust to extra spaces in day-of-week headers
- Defaults to last 14 days, but can be customized

## Setup

1. **Set up your WHOOP OAuth credentials:**
   - Create a WHOOP OAuth app (client ID and secret) and add to a `.env` file in the project root:
     ```env
     WHOOP_CLIENT_ID="..."
     WHOOP_CLIENT_SECRET="..."
     ```
   - For syncing (and for the GitHub Actions workflow), also set:
     ```env
     WHOOP_USERNAME="your_whoop_email@example.com"
     WHOOP_PASSWORD="your_whoop_password"
     ```

2. **Obtain WHOOP tokens (one-time or when expired):**
   - Run the auth flow to save tokens locally:
     ```sh
     uv run sync_whoop_to_gsheets.py auth
     ```
   - Complete the OAuth flow in the browser. Tokens are written to `whoop-tokens.json`.
   - To use the same tokens in GitHub Actions, encode and upload them to your repo secrets:
     ```sh
     uv run sync_whoop_to_gsheets.py upload-tokens
     ```
   - Optional: `uv run sync_whoop_to_gsheets.py upload-tokens --token-file path/to/tokens.json`. Requires [GitHub CLI](https://cli.github.com/) (`gh`) to be installed and logged in with permission to set repository secrets.

3. **Set up Google Sheets API:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable the Google Sheets API and Drive API.
   - Create a Service Account and download the credentials JSON file.
   - Share your target Google Sheet with the service account email (as Editor).
   - Place the credentials file as `google-creds.json` in your project root (or specify with `--creds-path`).

3. **Sheet Format:**
   - The first row of the "Running" tab should have headers: `Monday`, `Tuesday`, ..., `Sunday` (case-insensitive, spaces are OK).
   - The first column of each week row should be the Monday date, in either `YYYY-MM-DD` or `DD/MM/YY` format.

## Usage

**Sync running data to Google Sheets:**
```sh
uv run sync_whoop_to_gsheets.py sync --days-ago 14 --sheet-name "Your Sheet Name"
```

**Get WHOOP OAuth tokens (saves to `whoop-tokens.json`):**
```sh
uv run sync_whoop_to_gsheets.py auth
```

**Upload token file to GitHub repo secret (for CI):**
```sh
uv run sync_whoop_to_gsheets.py upload-tokens
```
Sets the `WHOOP_TOKENS_JSON` secret via `gh secret set`. Use `--token-file` to specify a path (default: `whoop-tokens.json`).

### Sync options
- `--days-ago` Number of days ago to start syncing from (up to today), default: 14
- `--sheet-name` Name of the Google Sheet
- `--creds-path` Path to Google service account credentials JSON, default: `google-creds.json`
- `--token-file` Path to WHOOP token JSON, default: `whoop-tokens.json`

Example:
```sh
uv run sync_whoop_to_gsheets.py sync --days-ago 30 --sheet-name "Robin Strength Program"
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