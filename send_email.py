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
"""

import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
data_file = Path(__file__).parent / "docs" / "data" / f"{stamp}.json"
if not data_file.exists():
    sys.exit(f"No data file for {stamp}; run collect_news.py first.")

data = json.loads(data_file.read_text())
items = data["items"]
if not items:
    sys.exit("No items today, skipping email.")

sections = {}
for it in items:
    sections.setdefault(it["category"], []).append(it)

rows = []
for cat, its in sections.items():
    rows.append(f"<h3 style='color:#0E3B2E;border-bottom:2px solid #FFD84D;"
                f"padding-bottom:4px'>{cat}</h3>")
    for it in its[:8]:
        rows.append(
            f"<p style='margin:10px 0'><a href='{it['link']}' "
            f"style='color:#122B22;font-weight:bold;text-decoration:none'>"
            f"{it['title']}</a><br>"
            f"<span style='color:#5C6B60;font-size:13px'>{it['summary']}"
            f"<br><i>{it['source']}</i></span></p>")

body = (f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>"
        f"<h2 style='background:#0E3B2E;color:#F3F1E7;padding:12px 16px'>"
        f"CPG Europe Daily — {stamp}</h2>{''.join(rows)}"
        f"<p style='font-size:12px;color:#888'>Auto-generated digest. "
        f"Links belong to their original publishers.</p></div>")

msg = MIMEText(body, "html")
msg["Subject"] = f"CPG Europe Daily — {stamp} ({len(items)} stories)"
msg["From"] = os.environ["SMTP_USER"]
recipients = [r.strip() for r in os.environ["MAIL_TO"].split(",")]
msg["To"] = ", ".join(recipients)

host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
port = int(os.environ.get("SMTP_PORT", "465"))
with smtplib.SMTP_SSL(host, port) as server:
    server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    server.sendmail(msg["From"], recipients, msg.as_string())

print(f"Emailed {len(items)} stories to {len(recipients)} recipient(s).")
