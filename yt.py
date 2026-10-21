import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BASE = os.path.dirname(os.path.abspath(__file__))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def upload(path, judul, deskripsi="", tag=None, privasi="private"):
    token_path = os.path.join(BASE, "token.json")
    cred = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not cred.valid:
        cred.refresh(Request())
        with open(token_path, "w") as f:
            f.write(cred.to_json())
    yt = build("youtube", "v3", credentials=cred)
    body = {
        "snippet": {"title": judul[:100], "description": deskripsi,
                    "tags": tag or [], "categoryId": "22"},
        "status": {"privacyStatus": privasi,
                   "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return "https://youtu.be/" + resp["id"]

if __name__ == "__main__":
    import glob
    v = sorted(glob.glob(os.path.join(BASE, "proyek", "*", "video.mp4")))[-1]
    print(upload(v, "Tes upload ytbot", "Video tes dari bot", ["tes"], "private"))
