# CPG Europe Daily

A free, self-updating daily newsletter of European CPG/FMCG news (M&A,
product launches, retail moves, regulation), published as a web page on
GitHub Pages and optionally emailed each morning.

How it works: a scheduled GitHub Action runs `collect_news.py` every day,
which pulls the RSS feeds in `feeds.txt`, keeps the last ~24 hours of
stories, groups them into sections, and writes a fresh `docs/index.html`
plus a dated archive copy and a JSON data file.

## Setup (one time, ~15 minutes)

1. Create a free account at github.com if you don't have one.
2. Create a new **public** repository, e.g. `cpg-daily`
   (public = free GitHub Pages + free unlimited Actions minutes).
3. Upload everything in this folder to the repository, keeping the
   folder structure (especially `.github/workflows/daily.yml`).
   Easiest way: on the repo page, "Add file" > "Upload files",
   drag the whole folder contents in, commit.
4. Turn on the website: repo **Settings > Pages** > under "Build and
   deployment" choose **Deploy from a branch**, branch `main`,
   folder `/docs`, Save.
5. Run it once manually: **Actions** tab > "CPG Europe Daily build" >
   **Run workflow**. Wait ~2 minutes for it to finish.
6. Your page is live at `https://YOURNAME.github.io/cpg-daily/`.
   From now on it rebuilds itself every morning automatically.

## Editing your sources

Open `feeds.txt` and add or remove RSS feed URLs (one per line).
Any feed that fails is skipped and reported in the Action run log —
check the log after your first run and replace dead URLs.
To find a site's feed, try adding `/feed`, `/rss`, or `/rss/news` to its
homepage URL, or look for an RSS icon on the site.

## Optional: daily email

1. Use a Gmail account. Enable 2-Step Verification, then create an
   **App Password** (Google Account > Security > App passwords).
2. In the repo: Settings > Secrets and variables > Actions > add:
   - `SMTP_USER` = your Gmail address
   - `SMTP_PASS` = the 16-character app password
   - `MAIL_TO`   = recipient1@x.com, recipient2@y.com
3. That's it — the workflow's email step activates automatically.
   (Gmail allows ~500 recipients/day, plenty for a team list.)

## Tuning

- Schedule: edit the `cron:` line in `.github/workflows/daily.yml`
  (times are UTC).
- Sections & keywords: edit `CATEGORIES` and `TOP_STORY_WORDS` at the
  top of `collect_news.py`.
- Look & feel: edit the `CSS` block in `collect_news.py`.
- Lookback window: set `LOOKBACK_HOURS` (default 26).

## Costs

Zero, as long as the repo stays public: GitHub Actions and Pages are
free for public repositories, RSS is free, and Gmail SMTP is free.
