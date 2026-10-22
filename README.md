# accountify-social

Posts Accountify reels to YouTube Shorts and Instagram from GitHub Actions, through the official APIs.
Nothing runs on a personal PC.

- `brand/schedule.json`: what to post and when (IST date and time; YouTube goes up 2 h before Instagram).
- `reels/`: the videos.
- `brand/posted.log`: what already went out. The workflow commits it after each run, so nothing posts twice.
- `scripts/`: copied from the `shorts-studio` skill (`yt.py`, `ig.py`, `post_due.py`).

Secrets (Settings → Secrets → Actions): `IG_TOKEN`, `YT_TOKEN_JSON`, `YT_CLIENT_SECRET_JSON`,
`HOSTING_SA_JSON` (a service account that can only manage Firebase Hosting on the separate
`amazon-clone-chatbot-wsqi` project, used for 1-hour preview links Instagram downloads from).

The Instagram token lasts 60 days. Refresh it at least monthly:
`python ig.py --brand accountify refresh` locally, then `gh secret set IG_TOKEN < ~/.social-brands/accountify/ig_token.txt`.

Run now: Actions → post reels → Run workflow.
