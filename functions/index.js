// GitHub's own cron silently skips runs (23-24 Oct 2026: whole days missed), so Cloud Scheduler
// pokes the "post reels" workflow instead. The workflow decides what's due; posted.log stops repeats.
// GH_DISPATCH_TOKEN: fine-grained GitHub token, Actions read/write on Triamb/accountify-social only.
const { onSchedule } = require("firebase-functions/v2/scheduler");

const URL = "https://api.github.com/repos/Triamb/accountify-social/actions/workflows/post.yml/dispatches";

exports.pokeReelPoster = onSchedule(
  { schedule: "7,37 17-23 * * *", timeZone: "Asia/Kolkata", region: "asia-south1", secrets: ["GH_DISPATCH_TOKEN"],
    memory: "128MiB", retryCount: 0 },
  async () => {
    const r = await fetch(URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.GH_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json" },
      body: JSON.stringify({ ref: "main" }),
    });
    if (r.status !== 204) throw new Error(`GitHub dispatch failed: ${r.status} ${await r.text()}`);
  },
);
