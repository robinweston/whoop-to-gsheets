# sync-whoop-gsheets

CLI to sync WHOOP activities to Google Sheets.

## Setup

1. **Clone the repo and install dependencies with uv:**
   ```sh
   uv pip install -r pyproject.toml
   ```

2. **Set up your WHOOP credentials:**
   - Create a `.env` file in the project root:
     ```env
     USERNAME="your_whoop_email@example.com"
     PASSWORD="your_whoop_password"
     ```

3. **Set up Google Sheets API:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable the Google Sheets API.
   - Create a Service Account and download the credentials JSON file.
   - Share your target Google Sheet with the service account email.

## Usage

```sh
uv pip install .

sync-whoop-gsheets sync \
  --start-date 2024-06-01 \
  --end-date 2024-06-07 \
  --sheet-name "Whoop Activities" \
  --creds-path "/path/to/credentials.json"
```

## Options
- `--start-date` Start date (YYYY-MM-DD)
- `--end-date` End date (YYYY-MM-DD)
- `--sheet-name` Name of the Google Sheet
- `--creds-path` Path to Google service account credentials JSON

## License
MIT 