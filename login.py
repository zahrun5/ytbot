import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
d = os.path.expanduser("~/ytbot")
flow = InstalledAppFlow.from_client_secrets_file(d + "/client_secret.json", SCOPES)
cred = flow.run_local_server(port=8080, open_browser=False,
                             access_type="offline", prompt="consent")
tok = d + "/token.json"
with open(tok, "w") as f:
    f.write(cred.to_json())
os.chmod(tok, 0o600)
print("Token tersimpan")
