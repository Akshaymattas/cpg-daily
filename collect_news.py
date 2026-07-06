#!/usr/bin/env python3
"""
CPG Europe Daily — news collector & page generator.

Reads RSS feeds from feeds.txt, keeps items from the last LOOKBACK_HOURS,
filters/categorizes for CPG relevance, then writes:
  docs/index.html            -> today's live page (GitHub Pages serves this)
  docs/archive/YYYY-MM-DD.html
  docs/archive/index.html    -> archive listing
  docs/data/YYYY-MM-DD.json  -> raw data (used by the optional emailer)

No API keys required. Only dependency: feedparser.
"""

import feedparser
import json
import html
import re
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ----------------------------- settings ------------------------------------

LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "26"))  # small overlap
MAX_ITEMS_PER_SECTION = 12
SITE_TITLE = "CPG Europe Daily"
BASE = Path(__file__).parent
DOCS = BASE / "docs"

# Category keyword rules (checked in order; first match wins)
CATEGORIES = [
    ("M&A & Investments", [
        "acquisition", "acquires", "acquired", "merger", "merges", "takeover",
        "buyout", "stake", "invests", "investment", "funding", "raises",
        "series a", "series b", "venture", "divest", "sells its", "to buy",
        "joint venture", "ipo", "valuation", "private equity",
    ]),
    ("Product & Innovation", [
        "launch", "launches", "unveils", "debuts", "new range", "new product",
        "introduces", "innovation", "reformulat", "flavour", "flavor",
        "packaging redesign", "limited edition", "rebrand", "npd",
    ]),
    ("Retail & Distribution", [
        "supermarket", "retailer", "retail", "store", "stores", "grocer",
        "e-commerce", "ecommerce", "online sales", "distribution", "listing",
        "shelf", "discounter", "hypermarket", "convenience", "wholesale",
        "supply chain", "logistics", "carrefour", "tesco", "aldi", "lidl",
        "sainsbury", "ahold", "rewe", "edeka", "auchan", "mercadona",
    ]),
    ("Regulatory & Sustainability", [
        "regulation", "regulator", "eu commission", "european commission",
        "ban", "law", "legislation", "compliance", "recall", "efsa",
        "sustainab", "recycl", "emissions", "carbon", "packaging waste",
        "deforestation", "eudr", "labelling", "labeling", "health claim",
        "tariff", "tax",
    ]),
]
FALLBACK_CATEGORY = "Other Headlines"

# Words that boost an item into "Top Stories"
TOP_STORY_WORDS = [
    "acquisition", "acquires", "merger", "takeover", "billion", "€", "recall",
    "ceo", "closes", "shuts", "bankrupt", "strike", "lawsuit", "record",
    "nestle", "nestlé", "unilever", "danone", "p&g", "procter", "coca-cola",
    "pepsico", "mondelez", "heineken", "ab inbev", "l'oreal", "l'oréal",
    "henkel", "carlsberg", "diageo", "ferrero", "lactalis", "kraft",
]

# Europe relevance signals (used to score, not hard-filter — most feeds
# are already EU-focused)
EUROPE_WORDS = [
    "europe", "european", "eu ", " uk", "britain", "germany", "france",
    "spain", "italy", "netherlands", "belgium", "poland", "ireland",
    "scandinav", "nordic", "switzerland", "austria", "portugal", "denmark",
    "sweden", "norway", "finland", "greece", "czech", "romania", "hungary",
]

# ----------------------------- collection ----------------------------------


def load_feeds():
    feeds = []
    for line in (BASE / "feeds.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            feeds.append(line)
    return feeds


def clean_text(raw, limit=280):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def categorize(text):
    low = text.lower()
    for name, words in CATEGORIES:
        if any(w in low for w in words):
            return name
    return FALLBACK_CATEGORY


def score(text):
    low = text.lower()
    s = sum(2 for w in TOP_STORY_WORDS if w in low)
    s += sum(1 for w in EUROPE_WORDS if w in low)
    return s


def collect():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items, seen, failures = [], set(), []

    for url in load_feeds():
        try:
            parsed = feedparser.parse(url, request_headers={
                "User-Agent": "Mozilla/5.0 (CPG-Daily digest bot)"})
            if parsed.bozo and not parsed.entries:
                raise RuntimeError(str(parsed.get("bozo_exception", "no entries")))
            source = clean_text(parsed.feed.get("title", url), 80)
            for e in parsed.entries[:40]:
                when = entry_time(e)
                if when and when < cutoff:
                    continue
                title = clean_text(e.get("title", ""), 200)
                if not title:
                    continue
                key = re.sub(r"[^a-z0-9]", "", title.lower())[:70]
                if key in seen:
                    continue
                seen.add(key)
                summary = clean_text(e.get("summary", e.get("description", "")))
                blob = f"{title} {summary}"
                items.append({
                    "title": title,
                    "link": e.get("link", ""),
                    "summary": summary,
                    "source": source,
                    "time": when.isoformat() if when else None,
                    "category": categorize(blob),
                    "score": score(blob),
                })
            print(f"OK   {url} -> {len(parsed.entries)} entries")
        except Exception as ex:
            failures.append(url)
            print(f"FAIL {url} -> {ex}")

    items.sort(key=lambda x: (-x["score"], x["time"] or ""), reverse=False)
    items.sort(key=lambda x: -x["score"])
    return items, failures


# ----------------------------- page rendering ------------------------------

CSS = """
:root{--ink:#122B22;--paper:#F5F6F2;--card:#FFFFFF;--green:#0E3B2E;
--tag:#FFD84D;--line:#D8DDD4;--muted:#5C6B60;--accent:#C8451F;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);
font:16px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}
a{color:inherit}
.wrap{max-width:880px;margin:0 auto;padding:0 20px 60px}
header{background:var(--green);color:#F3F1E7;padding:34px 0 26px;
border-bottom:6px solid var(--tag)}
header .wrap{padding-bottom:0}
.masthead{font-family:"Arial Black","Segoe UI",sans-serif;
font-size:clamp(26px,5vw,44px);letter-spacing:.02em;line-height:1.05;
text-transform:uppercase}
.datebadge{display:inline-block;background:var(--tag);color:#122B22;
font-weight:700;font-size:14px;padding:4px 12px;margin-top:12px;
transform:rotate(-1.2deg);box-shadow:2px 2px 0 rgba(0,0,0,.25)}
.subline{margin-top:10px;font-size:14px;opacity:.85}
nav{font-size:13px;margin-top:14px}
nav a{color:#F3F1E7;opacity:.9;margin-right:16px}
h2.section{margin:38px 0 14px;font-size:14px;letter-spacing:.14em;
text-transform:uppercase;background:var(--ink);color:var(--tag);
display:inline-block;padding:5px 14px}
.item{background:var(--card);border:1px solid var(--line);
border-left:4px solid var(--green);padding:16px 18px;margin-bottom:12px}
.item.top{border-left-color:var(--accent)}
.item h3{font-size:17px;line-height:1.35;margin-bottom:6px}
.item h3 a{text-decoration:none}
.item h3 a:hover{text-decoration:underline}
.item p{font-size:14px;color:var(--muted);margin-bottom:8px}
.meta{font-size:12px;color:var(--muted);text-transform:uppercase;
letter-spacing:.06em}
.meta b{color:var(--green)}
footer{margin-top:50px;font-size:12px;color:var(--muted);
border-top:1px solid var(--line);padding-top:14px}
.empty{padding:30px;text-align:center;color:var(--muted)}
"""


def render_item(it, top=False):
    t = ""
    if it["time"]:
        t = datetime.fromisoformat(it["time"]).strftime("%H:%M UTC")
    return f"""<div class="item{' top' if top else ''}">
<h3><a href="{html.escape(it['link'])}" target="_blank" rel="noopener">
{html.escape(it['title'])}</a></h3>
<p>{html.escape(it['summary'])}</p>
<div class="meta"><b>{html.escape(it['source'])}</b>{' · ' + t if t else ''}</div>
</div>"""


def render_page(items, date_str, archive_link="archive/index.html"):
    top = [i for i in items if i["score"] >= 4][:5]
    top_keys = {id(i) for i in top}
    body = []

    if top:
        body.append('<h2 class="section">Top Stories</h2>')
        body += [render_item(i, top=True) for i in top]

    for cat, _ in CATEGORIES + [(FALLBACK_CATEGORY, [])]:
        rows = [i for i in items
                if i["category"] == cat and id(i) not in top_keys]
        rows = rows[:MAX_ITEMS_PER_SECTION]
        if rows:
            body.append(f'<h2 class="section">{cat}</h2>')
            body += [render_item(i) for i in rows]

    if not body:
        body = ['<div class="empty">No fresh stories collected in this '
                'window. Check the run log for feed errors.</div>']

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_TITLE} — {date_str}</title><style>{CSS}</style></head><body>
<header><div class="wrap">
<div class="masthead">{SITE_TITLE}</div>
<div class="datebadge">{date_str}</div>
<div class="subline">Auto-collected European consumer-goods headlines —
M&amp;A, launches, retail moves &amp; regulation. Updated every morning.</div>
<nav><a href="{archive_link}">Archive</a></nav>
</div></header>
<div class="wrap">{''.join(body)}
<footer>Generated automatically from public RSS feeds. Headlines and
summaries link to and belong to their original publishers.</footer>
</div></body></html>"""


def render_archive_index(dates):
    links = "".join(
        f'<div class="item"><h3><a href="{d}.html">{d}</a></h3></div>'
        for d in sorted(dates, reverse=True))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_TITLE} — Archive</title><style>{CSS}</style></head><body>
<header><div class="wrap"><div class="masthead">{SITE_TITLE}</div>
<div class="datebadge">Archive</div>
<nav><a href="../index.html">Back to today</a></nav></div></header>
<div class="wrap">{links or '<div class="empty">No editions yet.</div>'}
</div></body></html>"""


# ----------------------------- main ----------------------------------------

def main():
    items, failures = collect()
    today = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    (DOCS / "archive").mkdir(parents=True, exist_ok=True)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)

    page = render_page(items, today)
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    (DOCS / "archive" / f"{stamp}.html").write_text(
        render_page(items, today, archive_link="index.html"),
        encoding="utf-8")

    dates = [p.stem for p in (DOCS / "archive").glob("*.html")
             if p.stem != "index"]
    (DOCS / "archive" / "index.html").write_text(
        render_archive_index(dates), encoding="utf-8")

    (DOCS / "data" / f"{stamp}.json").write_text(
        json.dumps({"date": stamp, "items": items, "failed_feeds": failures},
                   indent=1), encoding="utf-8")

    print(f"\nDone: {len(items)} items, {len(failures)} feed(s) failed.")


if __name__ == "__main__":
    main()
