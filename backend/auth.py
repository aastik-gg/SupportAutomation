from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"

flow = InstalledAppFlow.from_client_secrets_file(
    str(CREDENTIALS),
    SCOPES,
)

creds = flow.run_local_server(port=8080)

with open(TOKEN_PATH, "w") as token:
    token.write(creds.to_json())

print("Authorization complete. token.json saved.")
