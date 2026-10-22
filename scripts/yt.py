"""YouTube Shorts for any brand via the official Data API v3 (OAuth; tokens stay local).

  uv run --with google-api-python-client --with google-auth-oauthlib python yt.py --brand <b> auth
  ... yt.py --brand <b> upload reel.mp4 --title "..." [--desc ..] [--tags a,b]
                               [--privacy private|unlisted|public] [--publish-at 2026-10-01T18:30:00Z]
                               [--synthetic]   # realistic AI people/voices/events -> YouTube disclosure
  ... yt.py --brand <b> comments [--limit 20]

Brand folder: ~/.social-brands/<b>/ holds client_secret.json + yt_token.json.
"""
import argparse
import json
import sys
sys.stdout.reconfigure(encoding="utf-8")  # titles have emoji; Windows console is cp1252
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # read + reply to comments
]


def yt(brand_dir, interactive=False):
    token = brand_dir / "yt_token.json"
    c = Credentials.from_authorized_user_file(token, SCOPES) if token.exists() else None
    if c and c.expired and c.refresh_token:
        c.refresh(Request())
    if not c or not c.valid:
        if not interactive:
            sys.exit(f"Not authorized. Run: yt.py --brand {brand_dir.name} auth")
        # Browser opens; the human picks the brand's channel and clicks Allow.
        c = InstalledAppFlow.from_client_secrets_file(brand_dir / "client_secret.json", SCOPES).run_local_server(port=0)
    token.write_text(c.to_json())
    return build("youtube", "v3", credentials=c)


def cmd_auth(a, d):
    ch = yt(d, True).channels().list(part="snippet", mine=True).execute()["items"][0]
    print(f"Authorized as channel: {ch['snippet']['title']} ({ch['id']})")


def cmd_upload(a, d):
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": a.synthetic}
    if a.publish_at:  # scheduled release; YouTube requires private until then
        status.update(privacyStatus="private", publishAt=a.publish_at)
    body = {
        "snippet": {
            "title": a.title[:100],
            "description": a.desc,
            "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
            "categoryId": a.category,
        },
        "status": status,
    }
    req = yt(d).videos().insert(part="snippet,status", body=body,
                                media_body=MediaFileUpload(a.file, chunksize=-1, resumable=True))
    res = None
    while res is None:
        _, res = req.next_chunk()
    print(json.dumps({"id": res["id"], "url": f"https://youtube.com/shorts/{res['id']}",
                      "privacy": res["status"]["privacyStatus"]}))


def cmd_comments(a, d):
    y = yt(d)
    ch = y.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    r = y.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=ch,
                                maxResults=min(a.limit, 100), order="time").execute()
    for t in r.get("items", []):
        s = t["snippet"]["topLevelComment"]["snippet"]
        print(f"[{s['publishedAt'][:10]}] {s['authorDisplayName']} on {t['snippet'].get('videoId')}: {s['textOriginal']}")


def cmd_stats(a, d):
    y = yt(d)
    ch = y.channels().list(part="statistics,contentDetails", mine=True).execute()["items"][0]
    s = ch["statistics"]
    print(f"channel  subs={s.get('subscriberCount')}  views={s.get('viewCount')}  videos={s.get('videoCount')}")
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = y.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=25).execute()["items"]
    ids = ",".join(i["contentDetails"]["videoId"] for i in items)
    for v in (y.videos().list(part="snippet,statistics,status", id=ids).execute()["items"] if ids else []):
        st = v["statistics"]
        print(f"{v['snippet']['publishedAt'][:16]}  {v['status']['privacyStatus']:8} views={st.get('viewCount', 0):>6} "
              f"likes={st.get('likeCount', 0):>4} comments={st.get('commentCount', 0):>3}  "
              f"https://youtube.com/shorts/{v['id']}  {v['snippet']['title'][:40]}")


p = argparse.ArgumentParser()
p.add_argument("--brand", required=True)
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("auth").set_defaults(f=cmd_auth)
u = sub.add_parser("upload")
u.add_argument("file")
u.add_argument("--title", required=True)
u.add_argument("--desc", default="")
u.add_argument("--tags", default="")
u.add_argument("--category", default="26")  # 26 Howto & Style, 22 People & Blogs, 24 Entertainment, 28 Sci & Tech
u.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
u.add_argument("--publish-at", default="")
u.add_argument("--synthetic", action="store_true")
u.set_defaults(f=cmd_upload)
c = sub.add_parser("comments")
c.add_argument("--limit", type=int, default=20)
c.set_defaults(f=cmd_comments)
sub.add_parser("stats").set_defaults(f=cmd_stats)
args = p.parse_args()
brand_dir = Path.home() / ".social-brands" / args.brand
if not brand_dir.is_dir():
    sys.exit(f"No brand folder {brand_dir}. See the skill's references/youtube-setup.md")
args.f(args, brand_dir)
