"""Instagram Reels for any brand via the official Instagram API (Instagram Login). Stdlib only.

  python ig.py --brand <b> whoami
  python ig.py --brand <b> post reel.mp4 --caption "..."
  python ig.py --brand <b> comments [--limit 20]
  python ig.py --brand <b> refresh      # extend the 60-day token; run at least monthly

Brand folder ~/.social-brands/<b>/ holds ig_token.txt and brand.json with
  {"ig_username": "...", "hosting_project": "<firebase project with a Hosting site>"}.
HARD LOCK: refuses to post unless the token's account == brand.json ig_username.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

V = "v25.0"
p = argparse.ArgumentParser()
p.add_argument("--brand", required=True)
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("whoami")
po = sub.add_parser("post")
po.add_argument("file")
po.add_argument("--caption", default="")
po.add_argument("--trial", action="store_true", help="Trial Reel: non-followers only; IG shares it to followers if it performs")
ca = sub.add_parser("carousel")  # 2-10 JPEGs (4:5, 1080x1350 recommended)
ca.add_argument("files", nargs="+")
ca.add_argument("--caption", default="")
co = sub.add_parser("comments")
co.add_argument("--limit", type=int, default=20)
sub.add_parser("refresh")
sub.add_parser("stats")
args = p.parse_args()

BRAND_DIR = Path.home() / ".social-brands" / args.brand
if not (BRAND_DIR / "ig_token.txt").exists():
    sys.exit(f"No {BRAND_DIR / 'ig_token.txt'}. See the skill's references/instagram-setup.md")
BRAND = json.loads((BRAND_DIR / "brand.json").read_text(encoding="utf-8"))
TOKEN = (BRAND_DIR / "ig_token.txt").read_text(encoding="utf-8-sig").strip()


def call(method, url, params=None):
    params = dict(params or {}, access_token=TOKEN)
    data, headers = None, {}
    if method == "POST":  # Graph wants POST params as a form body
        data, headers = urllib.parse.urlencode(params).encode(), {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode()}")


def me():
    return call("GET", f"https://graph.instagram.com/{V}/me", {"fields": "user_id,username,account_type,media_count"})


def host(file, extra=()):
    """Instagram-Login accounts can't use resumable upload ("video_url is required"), so IG
    must fetch a public URL. Serve it from a throwaway Firebase Hosting preview channel:
    never touches the live site, expires in 1h, and we delete it right after publishing."""
    channel = f"reel-{int(time.time())}"
    d = Path(tempfile.mkdtemp())
    shutil.copy(file, d / "reel.mp4") if file else None
    for i, f in enumerate(extra):
        shutil.copy(f, d / f"s{i}.jpg")
    (d / "firebase.json").write_text(json.dumps({"hosting": {"public": ".", "ignore": ["firebase.json"]}}))
    r = subprocess.run(f"firebase hosting:channel:deploy {channel} --expires 1h --project {BRAND['hosting_project']} --json",
                       shell=True, capture_output=True, text=True, cwd=d)
    out = json.loads(r.stdout[r.stdout.index("{"):]) if "{" in r.stdout else {}
    if out.get("status") != "success":
        sys.exit(f"hosting deploy failed: {r.stdout[-500:]} {r.stderr[-500:]}")
    base = next(iter(out["result"].values()))["url"]
    return channel, (base + "/reel.mp4" if file else [f"{base}/s{i}.jpg" for i in range(len(extra))])


def post(file, caption, trial=False):
    who = me()
    if who.get("username") != BRAND["ig_username"]:
        sys.exit(f"REFUSING: token belongs to @{who.get('username')}, not @{BRAND['ig_username']}")
    ig = who["user_id"]
    channel, video_url = host(file)
    try:
        cid = call("POST", f"https://graph.instagram.com/{V}/{ig}/media",
                   {"media_type": "REELS", "video_url": video_url, "caption": caption,
                    **({"trial_params": json.dumps({"graduation_strategy": "SS_PERFORMANCE"})} if trial
                       else {"share_to_feed": "true"})})["id"]
        for _ in range(60):  # IG fetches + transcodes before it can publish
            s = call("GET", f"https://graph.instagram.com/{V}/{cid}", {"fields": "status_code,status"})
            if s.get("status_code") == "FINISHED":
                break
            if s.get("status_code") in ("ERROR", "EXPIRED"):
                sys.exit(f"processing failed: {s}")
            time.sleep(5)
        else:
            sys.exit("timed out waiting for Instagram to process the video")
    finally:
        subprocess.run(f"firebase hosting:channel:delete {channel} --force --project {BRAND['hosting_project']}",
                       shell=True, capture_output=True)
    pub = call("POST", f"https://graph.instagram.com/{V}/{ig}/media_publish", {"creation_id": cid})
    link = call("GET", f"https://graph.instagram.com/{V}/{pub['id']}", {"fields": "permalink"})
    print(json.dumps({"media_id": pub["id"], "url": link.get("permalink")}))


def carousel(files, caption):
    who = me()
    if who.get("username") != BRAND["ig_username"]:
        sys.exit(f"REFUSING: token belongs to @{who.get('username')}, not @{BRAND['ig_username']}")
    if not 2 <= len(files) <= 10:
        sys.exit("a carousel needs 2-10 images")
    ig = who["user_id"]
    channel, urls = host(None, files)
    try:
        kids = [call("POST", f"https://graph.instagram.com/{V}/{ig}/media", {"image_url": u, "is_carousel_item": "true"})["id"] for u in urls]
        cid = call("POST", f"https://graph.instagram.com/{V}/{ig}/media",
                   {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption})["id"]
        for _ in range(30):
            s = call("GET", f"https://graph.instagram.com/{V}/{cid}", {"fields": "status_code"})
            if s.get("status_code") == "FINISHED":
                break
            time.sleep(3)
    finally:
        subprocess.run(f"firebase hosting:channel:delete {channel} --force --project {BRAND['hosting_project']}",
                       shell=True, capture_output=True)
    pub = call("POST", f"https://graph.instagram.com/{V}/{ig}/media_publish", {"creation_id": cid})
    link = call("GET", f"https://graph.instagram.com/{V}/{pub['id']}", {"fields": "permalink"})
    print(json.dumps({"media_id": pub["id"], "url": link.get("permalink")}))


if args.cmd == "whoami":
    print(json.dumps(me(), indent=2))
elif args.cmd == "post":
    post(args.file, args.caption, args.trial)
elif args.cmd == "carousel":
    carousel(args.files, args.caption)
elif args.cmd == "comments":
    media = call("GET", f"https://graph.instagram.com/{V}/me/media", {"fields": "id,permalink", "limit": 10})
    for m in media.get("data", []):
        cs = call("GET", f"https://graph.instagram.com/{V}/{m['id']}/comments",
                  {"fields": "username,text,timestamp", "limit": args.limit})
        for c in cs.get("data", []):
            print(f"[{c['timestamp'][:10]}] @{c.get('username')} on {m['permalink']}: {c['text']}")
elif args.cmd == "stats":
    acct = call("GET", f"https://graph.instagram.com/{V}/me", {"fields": "username,followers_count,media_count"})
    print(f"@{acct['username']}  followers={acct.get('followers_count')}  posts={acct.get('media_count')}")
    media = call("GET", f"https://graph.instagram.com/{V}/me/media", {"fields": "id,timestamp,permalink,like_count,comments_count", "limit": 25})
    for m in media.get("data", []):
        ins = call("GET", f"https://graph.instagram.com/{V}/{m['id']}/insights", {"metric": "views,reach,saved,shares"})
        v = {d["name"]: d["values"][0]["value"] for d in ins.get("data", [])}
        print(f"{m['timestamp'][:16]}  views={v.get('views', 0):>6} reach={v.get('reach', 0):>6} "
              f"likes={m.get('like_count', 0):>4} comments={m.get('comments_count', 0):>3} "
              f"shares={v.get('shares', 0):>4} saves={v.get('saved', 0):>4}  {m['permalink']}")
elif args.cmd == "refresh":
    r = call("GET", "https://graph.instagram.com/refresh_access_token", {"grant_type": "ig_refresh_token"})
    (BRAND_DIR / "ig_token.txt").write_text(r["access_token"])
    print(f"refreshed; valid ~{r.get('expires_in', 0) // 86400} days")
