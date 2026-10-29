"""Post today's scheduled reel (IST date) from a brand's schedule manifest. Safe to re-run:
every successful post is recorded in ~/.social-brands/<brand>/posted.log and never repeated.

  python post_due.py --brand accountify --manifest week1-schedule.json --platform ig
  python post_due.py --brand accountify --manifest week1-schedule.json --platform yt
  python post_due.py --brand accountify --manifest week1-schedule.json --catchup   (today + yesterday)

Manifest entries: {date, ig_time_ist, file, caption, yt_title, yt_desc}. Meant to be run by
Windows Task Scheduler at the slot time (ig) or ~2 h earlier (yt: uploads land private
until the YouTube API audit, so the human flips them Public in Studio).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
p = argparse.ArgumentParser()
p.add_argument("--brand", required=True)
p.add_argument("--manifest", required=True)
p.add_argument("--platform", choices=["ig", "yt"])
p.add_argument("--date", help="override IST date YYYY-MM-DD (testing)")
p.add_argument("--slot", help="pick the entry with this slot name when a day has several posts")
p.add_argument("--catchup", action="store_true",
               help="post every entry of TODAY whose time has passed but isn't in posted.log (power-cut safety net)")
a = p.parse_args()

if a.catchup:  # re-invoke this script once per overdue (entry, platform)
    now = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
    # Yesterday too: if the PC was off all evening, boot-time runs can die (they race for
    # post-run.log) and a today-only sweep would drop that day's post for good.
    days = {(now - dt.timedelta(days=n)).strftime("%Y-%m-%d") for n in (0, 1)}
    brand_dir = Path.home() / ".social-brands" / a.brand
    done = (brand_dir / "posted.log").read_text(encoding="utf-8") if (brand_dir / "posted.log").exists() else ""
    for e in json.loads((brand_dir / a.manifest).read_text(encoding="utf-8")):
        day = e["date"]
        if day not in days:
            continue
        slot_at = dt.datetime.strptime(f"{day} {e['ig_time_ist']}", "%Y-%m-%d %H:%M")
        plats = ["ig"] + ([] if e.get("images") or e.get("ig_only") else ["yt"])
        for plat in plats:
            due = slot_at - (dt.timedelta(hours=2) if plat == "yt" else dt.timedelta(0))
            key = f"{day} {plat} {Path(e.get('file') or e['images'][0]).name}"
            if now >= due and key not in done:
                extra = ["--slot", e["slot"]] if e.get("slot") else []
                subprocess.run([sys.executable, __file__, "--brand", a.brand, "--manifest", a.manifest,
                                "--platform", plat, "--date", day, *extra])
    sys.exit(0)

brand_dir = Path.home() / ".social-brands" / a.brand
today = a.date or (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
entries = [e for e in json.loads((brand_dir / a.manifest).read_text(encoding="utf-8")) if e["date"] == today and e.get("slot") == a.slot]
if not entries:
    sys.exit(f"nothing scheduled for {today}")
if not a.platform:
    sys.exit("--platform is required (or use --catchup)")
e = entries[0]
log = brand_dir / "posted.log"
key = f"{today} {a.platform} {Path(e.get('file') or e['images'][0]).name}"
if log.exists() and key in log.read_text(encoding="utf-8"):
    sys.exit(f"already posted: {key}")
# Exclusive claim BEFORE publishing: two runs (scheduled + catch-up/manual) can't both
# post. Created atomically (O_EXCL); kept after success, removed only on failure.
import hashlib, os
locks = brand_dir / "locks"
locks.mkdir(exist_ok=True)
lock = locks / (hashlib.sha1(key.encode()).hexdigest() + ".lock")
try:
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
except FileExistsError:
    sys.exit(f"already claimed by another run: {key}")

if a.platform == "ig" and e.get("images"):
    cmd = [sys.executable, str(HERE / "ig.py"), "--brand", a.brand, "carousel", *e["images"], "--caption", e["caption"]]
elif a.platform == "ig":
    cmd = [sys.executable, str(HERE / "ig.py"), "--brand", a.brand, "post", e["file"], "--caption", e["caption"], *(["--trial"] if e.get("trial") else [])]
else:
    import shutil  # scheduled tasks may have a thin PATH; fall back to uv's default install
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv.exe")
    cmd = [uv, "run", "--with", "google-api-python-client", "--with", "google-auth-oauthlib", "python", str(HERE / "yt.py"),
           "--brand", a.brand, "upload", e["file"], "--title", e["yt_title"], "--desc", e["yt_desc"], "--privacy", "private"]
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
print(r.stdout, r.stderr)
if r.returncode != 0:
    lock.unlink(missing_ok=True)  # release so a later run can retry
    sys.exit(f"FAILED {key}")
with log.open("a", encoding="utf-8") as f:
    f.write(f"{key} {r.stdout.strip()}\n")
print(f"posted {key}")
