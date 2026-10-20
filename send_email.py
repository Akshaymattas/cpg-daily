#!/usr/bin/env python3
"""
Optional email digest for CPG Europe Daily.

Reads today's docs/data/YYYY-MM-DD.json and emails a simple HTML digest
via SMTP. Free option: a Gmail account + App Password (Google Account >
Security > 2-Step Verification > App passwords).

Required environment variables:
  SMTP_USER  e.g. yourname@gmail.com
  SMTP_PASS  the 16-character app password
  MAIL_TO    comma-separated recipient list
Optional:
  SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 465)
  SITE_URL  link to the web edition (defaults to this repo's GitHub Pages)
"""

import html
import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from collect_news import SITE_TITLE, split_sections


def esc(s):
    return html.escape(s or "", quote=True)


def site_url():
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def render_item(it):
    return (f"<p style='margin:10px 0'><a href='{esc(it['link'])}' "
            f"style='color:#122B22;font-weight:bold;text-decoration:none'>"
            f"{esc(it['title'])}</a><br>"
            f"<span style='color:#5C6B60;font-size:13px'>{esc(it['summary'])}"
            f"<br><i>{esc(it['source'])}</i></span></p>")


def section(title, items, colour="#0E3B2E"):
    return (f"<h3 style='color:{colour};border-bottom:2px solid #FFD84D;"
            f"padding-bottom:4px;margin-top:22px'>{esc(title)}</h3>"
            + "".join(render_item(i) for i in items))


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data_file = Path(__file__).parent / "docs" / "data" / f"{stamp}.json"
    if not data_file.exists():
        sys.exit(f"No data file for {stamp}; run collect_news.py first.")

    items = json.loads(data_file.read_text(encoding="utf-8"))["items"]
    if not items:
        print("No items today, skipping email.")
        return

    top, sections = split_sections(items)
    rows = []
    if top:
        rows.append(section("Top Stories", top, colour="#C8451F"))
    rows += [section(cat, its[:8]) for cat, its in sections]

    url = site_url()
    link = (f"<p style='margin:16px 0'><a href='{esc(url)}' style='background:"
            f"#FFD84D;color:#122B22;font-weight:bold;padding:8px 14px;"
            f"text-decoration:none'>Read &amp; search on the web →</a></p>"
            if url else "")

    body = (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>"
            f"<h2 style='background:#0E3B2E;color:#F3F1E7;padding:12px 16px;"
            f"border-bottom:4px solid #FFD84D'>{SITE_TITLE} — {stamp}</h2>"
            f"{link}{''.join(rows)}{link}"
            f"<p style='font-size:12px;color:#888'>Auto-generated digest. "
            f"Links belong to their original publishers.</p></div>")

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"{SITE_TITLE} — {stamp} ({len(items)} stories)"
    msg["From"] = os.environ["SMTP_USER"]
    recipients = [r.strip() for r in os.environ["MAIL_TO"].split(",")
                  if r.strip()]
    msg["To"] = ", ".join(recipients)

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as server:
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        server.sendmail(msg["From"], recipients, msg.as_string())

    print(f"Emailed {len(items)} stories to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
