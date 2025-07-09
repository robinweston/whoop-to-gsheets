import os
import json
import logging
from dotenv import load_dotenv
from flask import Flask, request, redirect
from requests_oauthlib import OAuth2Session

load_dotenv()

# Configure logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# WHOOP OAuth configuration
CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
AUTHORIZATION_BASE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPE = ["offline", "read:workout"]  # Add other scopes as needed


def __get_whoop_token(token_file):
    if not os.path.exists(token_file):
        logger.error(
            f"{token_file} not found. Please run the whoop-auth command first."
        )
        raise RuntimeError(f"{token_file} not found.")
    with open(token_file, "r") as f:
        token = json.load(f)
    return token


def __save_whoop_token(token, token_file):
    with open(token_file, "w") as f:
        json.dump(token, f, indent=2)


def get_valid_whoop_token(token_file):
    token = __get_whoop_token(token_file)
    # Check if token is expired
    import time

    if token.get("expires_at") and token["expires_at"] < time.time():
        logger.info("Access token expired, refreshing...")
        extra = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        oauth = OAuth2Session(
            CLIENT_ID,
            token=token,
            auto_refresh_url=TOKEN_URL,
            auto_refresh_kwargs=extra,
            token_updater=lambda t: __save_whoop_token(t, token_file),
        )
        new_token = oauth.refresh_token(
            TOKEN_URL,
            refresh_token=token["refresh_token"],
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        __save_whoop_token(new_token, token_file)
        return new_token["access_token"]
    return token["access_token"]


def start_auth_web_server(token_file, port=5000):
    """Start a local HTTPS server to obtain WHOOP OAuth tokens and save them to a JSON file."""
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET must be set in .env")
        return

    state = os.urandom(8).hex()
    redirect_uri = f"https://localhost:{port}/callback"

    app = Flask(__name__)
    oauth = OAuth2Session(
        CLIENT_ID, redirect_uri=redirect_uri, scope=SCOPE, state=state
    )

    @app.route("/")
    def index():
        authorization_url, _ = oauth.authorization_url(
            AUTHORIZATION_BASE_URL, state=state
        )
        return redirect(authorization_url)

    @app.route("/callback")
    def callback():
        try:
            token = oauth.fetch_token(
                TOKEN_URL,
                authorization_response=request.url,
                client_secret=CLIENT_SECRET,
                include_client_id=True,
                verify=True,
            )
            with open(token_file, "w") as f:
                json.dump(token, f, indent=2)
            shutdown_func = request.environ.get("werkzeug.server.shutdown")
            if shutdown_func:
                shutdown_func()
            return f"Tokens saved to {token_file}. You may close this window."
        except Exception as e:
            logger.error(f"Error obtaining token: {e}")
            return f"Error obtaining token: {e}", 500

    # Generate a self-signed cert if not present
    cert_file = "localhost.pem"
    key_file = "localhost-key.pem"
    if not (os.path.exists(cert_file) and os.path.exists(key_file)):
        import subprocess

        logger.info(f"Generating self-signed certificate for {redirect_uri}")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                key_file,
                "-out",
                cert_file,
                "-days",
                "365",
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
        )

    logger.info(f"Starting local HTTPS server at {redirect_uri}")
    app.run(host="localhost", port=port, ssl_context=(cert_file, key_file))
