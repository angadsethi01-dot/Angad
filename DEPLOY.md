# Deploy as a public website (one shareable link)

This hosts the tracker on **Streamlit Community Cloud** (free) and keeps the data
fresh with a **GitHub Actions** job that runs every day and commits new data back
to the repo. Anyone you share the link with just opens it in a browser — Windows,
Mac, phone, all fine. No install for them.

The repo is already prepared: data is committed so the app shows data on first
load, and `.github/workflows/daily_refresh.yml` handles the daily refresh.

---

## One-time setup (~10 minutes)

### 1. Put the code on GitHub
You need a free GitHub account: https://github.com/signup

This folder is already a git repo with an initial commit. Create an empty repo on
GitHub (no README/.gitignore), then push:

```bash
cd oem_award_tracker
git remote add origin https://github.com/<your-username>/oem-award-tracker.git
git branch -M main
git push -u origin main
```

(If GitHub asks for a password, use a Personal Access Token, or install the
GitHub CLI `gh` and run `gh auth login` first.)

### 2. Deploy the website on Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in **with your GitHub account**.
2. Click **Create app → Deploy a public app from GitHub**.
3. Select your repo, branch `main`, and set **Main file path** to `app.py`.
4. Click **Deploy**. After a minute you get a public URL like
   `https://oem-award-tracker.streamlit.app` — that's the link you share.

It redeploys automatically whenever the repo changes (including the daily refresh).

### 3. Turn on the daily refresh
The workflow runs on GitHub's schedule automatically once the repo is on GitHub —
no extra setup. To confirm or trigger it manually:
1. In your GitHub repo → **Actions** tab → enable workflows if prompted.
2. Open **Daily USAspending Refresh** → **Run workflow** to test it now.
3. It pulls fresh USAspending data, commits the updated files, and Streamlit
   redeploys with the new data.

That's it. The link is live, public, and refreshes daily.

---

## Notes
- **Privacy:** a Streamlit Community Cloud public app is visible to anyone with the
  link. There's no sensitive data here (all public USAspending records), but if you
  want it locked down, Streamlit supports viewer authentication on paid tiers, or
  host on a private service instead.
- **The macOS launchd agent is for your *local* copy only** — the hosted site uses
  the GitHub Action instead. You can leave the local agent or remove it:
  ```
  launchctl unload ~/Library/LaunchAgents/com.oemtracker.dailyrefresh.plist
  rm ~/Library/LaunchAgents/com.oemtracker.dailyrefresh.plist
  ```
- **Schedule timing:** the Action runs at 11:00 UTC (~7:00 AM ET). Edit the `cron:`
  line in `.github/workflows/daily_refresh.yml` to change it.
- **Local use still works** exactly as before (`./run.sh` or the `.command`).
