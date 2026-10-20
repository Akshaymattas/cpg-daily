#!/usr/bin/env python3
"""
CPG Europe Daily — news collector & page generator.

Reads RSS feeds from feeds.txt, keeps items from the last LOOKBACK_HOURS,
drops stories already published in recent editions, filters/categorizes
for CPG relevance, then writes:
  docs/index.html            -> today's live page (GitHub Pages serves this)
  docs/archive/YYYY-MM-DD.html
  docs/archive/index.html    -> archive listing
  docs/data/YYYY-MM-DD.json  -> raw data (used by the optional emailer)
  docs/search-index.json     -> every edition's stories, for site search

Look & feel lives in docs/assets/style.css and docs/assets/app.js.

No API keys required. Only dependency: feedparser.

  python collect_news.py            # collect today's edition
  python collect_news.py --rebuild  # re-render all pages from docs/data
"""

import calendar
import feedparser
import json
import html
import re
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ----------------------------- settings ------------------------------------

LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "26"))  # small overlap
DEDUP_DAYS = 3            # skip stories that appeared in the last N editions
MAX_ITEMS_PER_SECTION = 12
TOP_STORY_MIN_SCORE = 4
MAX_TOP_STORIES = 5
SITE_TITLE = "CPG Europe Daily"
BASE = Path(__file__).parent
DOCS = BASE / "docs"

# Keywords match whole words only, so "ban" doesn't match "bank" or
# "urban". End a keyword with * to match any word starting with it
# (e.g. "sustainab*" matches sustainable, sustainability).

# Category keyword rules (checked in order; first match wins)
CATEGORIES = [
    ("M&A & Investments", [
        "acquisition", "acquisitions", "acquires", "acquired", "acquire",
        "merger", "merges", "takeover", "buyout", "stake", "invests",
        "investment", "investor*", "funding", "raises", "series a",
        "series b", "venture capital", "divest*", "sells its", "to buy",
        "joint venture", "ipo", "valuation", "private equity", "buys",
        "sells", "sold", "snaps up", "bid", "offer for",
    ]),
    ("Regulatory & Sustainability", [
        "regulation*", "regulator*", "eu commission", "european commission",
        "ban", "bans", "banned", "law", "laws", "legislation", "compliance",
        "recall", "recalls", "recalled", "efsa", "sustainab*", "recycl*",
        "emissions", "carbon", "packaging waste", "deforestation", "eudr",
        "labelling", "labeling", "health claim*", "tariff*", "tax", "taxes",
        "hfss", "net zero",
    ]),
    ("Product & Innovation", [
        "launch", "launches", "launched", "unveils", "debuts", "new range",
        "new product", "introduces", "innovation", "reformulat*", "flavour*",
        "flavor*", "packaging redesign", "limited edition", "rebrand*", "npd",
    ]),
    ("Results & People", [
        "results", "earnings", "revenue*", "sales growth", "sales fall*",
        "sales rise*", "profit*", "loss", "losses", "turnover", "guidance",
        "forecast*", "outlook", "h1", "h2", "q1", "q2", "q3", "q4",
        "half-year", "full-year", "quarter*", "trading update",
        "ceo", "cfo", "coo", "chairman", "chairperson", "chief executive",
        "appoint*", "names", "hires", "steps down", "resigns", "successor",
        "managing director", "job cuts", "cut costs", "cost cuts", "layoffs",
        "redundanc*",
    ]),
    ("Retail & Distribution", [
        "supermarket*", "retailer*", "store", "stores", "grocer*",
        "e-commerce", "ecommerce", "online sales", "distribution", "listing*",
        "shelf", "shelves", "discounter*", "hypermarket*", "convenience",
        "wholesale*", "supply chain", "logistics", "carrefour", "tesco",
        "aldi", "lidl", "sainsbury*", "ahold", "rewe", "edeka", "auchan",
        "mercadona", "asda", "morrisons", "delhaize", "jumbo", "colruyt",
    ]),
]
FALLBACK_CATEGORY = "Other Headlines"

# Words that boost an item into "Top Stories" (+2 each)
TOP_STORY_WORDS = [
    "acquisition", "acquires", "merger", "takeover", "billion", "recall",
    "ceo", "closes", "shuts", "bankrupt*", "insolven*", "strike", "lawsuit",
    "record", "nestle", "nestlé", "unilever", "danone", "p&g", "procter",
    "coca-cola", "pepsico", "mondelez", "heineken", "ab inbev", "l'oreal",
    "l'oréal", "henkel", "carlsberg", "diageo", "ferrero", "lactalis",
    "kraft", "reckitt", "haleon", "beiersdorf", "kenvue",
]

# Billion-scale amounts like "€1.8bn" or "1.8-billion-euro" (+2)
BIG_MONEY = re.compile(r"[€£$]\s?\d[\d.,]*\s?bn\b|\d[\d.,]*[\s-]?billion", re.I)

# Europe relevance signals (+1 each; used to score, not hard-filter —
# most feeds are already EU-focused)
EUROPE_WORDS = [
    "europe", "european", "eu", "uk", "britain", "british", "germany",
    "german", "france", "french", "spain", "spanish", "italy", "italian",
    "netherlands", "dutch", "belgium", "belgian", "poland", "polish",
    "ireland", "irish", "scandinav*", "nordic", "switzerland", "swiss",
    "austria", "portugal", "portuguese", "denmark", "danish", "sweden",
    "swedish", "norway", "finland", "greece", "czech", "romania", "hungary",
]


def keyword_regex(words):
    parts = []
    for w in words:
        tail = r"\w*" if w.endswith("*") else ""
        parts.append(re.escape(w.rstrip("*").lower()) + tail)
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)")


CATEGORY_RES = [(name, keyword_regex(words)) for name, words in CATEGORIES]
TOP_STORY_RE = keyword_regex(TOP_STORY_WORDS)
EUROPE_RE = keyword_regex(EUROPE_WORDS)
SECTION_ORDER = [name for name, _ in CATEGORIES] + [FALLBACK_CATEGORY]

# ----------------------------- collection ----------------------------------

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
                   "CPG-Daily-digest"),
    "Accept": "application/rss+xml, application/atom+xml, "
              "application/xml;q=0.9, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def load_feeds():
    feeds = []
    for line in (BASE / "feeds.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            feeds.append(line)
    return feeds


def fetch_feed(url, attempts=3):
    """Download and parse a feed, retrying transient failures."""
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                parsed = feedparser.parse(resp.read())
            if parsed.entries:
                return parsed
            last = parsed.get("bozo_exception") or "no entries"
        except Exception as ex:
            last = ex
        if n < attempts - 1:
            time.sleep(2 ** (n + 1))
    raise RuntimeError(str(last))


def clean_text(raw, limit=280):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:  # feedparser gives UTC struct_time
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def title_key(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())[:70]


def categorize(text):
    low = text.lower()
    for name, rx in CATEGORY_RES:
        if rx.search(low):
            return name
    return FALLBACK_CATEGORY


def score(text):
    low = text.lower()
    s = 2 * len(set(TOP_STORY_RE.findall(low)))
    s += 2 if BIG_MONEY.search(low) else 0
    s += len(set(EUROPE_RE.findall(low)))
    return s


def classify(item):
    blob = f"{item['title']} {item['summary']}"
    item["category"] = categorize(blob)
    item["score"] = score(blob)
    return item


def sort_items(items):
    # Highest score first; within a score, newest first
    items.sort(key=lambda x: x["time"] or "", reverse=True)
    items.sort(key=lambda x: -x["score"])
    return items


def recent_keys(today_stamp):
    """Links and title keys from the previous DEDUP_DAYS editions."""
    links, titles = set(), set()
    files = sorted(p for p in (DOCS / "data").glob("*.json")
                   if p.stem < today_stamp)[-DEDUP_DAYS:]
    for p in files:
        for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
            if it.get("link"):
                links.add(it["link"])
            titles.add(title_key(it["title"]))
    return links, titles


def collect(today_stamp):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    old_links, seen = recent_keys(today_stamp)
    items, failures, repeats = [], [], 0

    for url in load_feeds():
        try:
            parsed = fetch_feed(url)
            source = clean_text(parsed.feed.get("title", url), 80)
            for e in parsed.entries[:40]:
                when = entry_time(e)
                if when and when < cutoff:
                    continue
                title = clean_text(e.get("title", ""), 200)
                if not title:
                    continue
                key = title_key(title)
                link = e.get("link", "")
                if key in seen or link in old_links:
                    repeats += 1
                    continue
                seen.add(key)
                summary = clean_text(e.get("summary", e.get("description", "")))
                items.append(classify({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": source,
                    "time": when.isoformat() if when else None,
                }))
            print(f"OK   {url} -> {len(parsed.entries)} entries")
        except Exception as ex:
            failures.append(url)
            print(f"FAIL {url} -> {ex}")

    print(f"Skipped {repeats} duplicate/already-published stories.")
    return sort_items(items), failures


# ----------------------------- page rendering ------------------------------

def esc(s):
    return html.escape(s or "", quote=True)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pretty_date(stamp):
    return datetime.strptime(stamp, "%Y-%m-%d").strftime("%A, %d %B %Y")


def split_sections(items):
    top = [i for i in items if i["score"] >= TOP_STORY_MIN_SCORE]
    top = top[:MAX_TOP_STORIES]
    top_ids = {id(i) for i in top}
    sections = []
    for cat in SECTION_ORDER:
        rows = [i for i in items
                if i["category"] == cat and id(i) not in top_ids]
        if rows:
            sections.append((cat, rows[:MAX_ITEMS_PER_SECTION]))
    return top, sections


def render_card(it, top=False):
    when = ""
    if it["time"]:
        t = datetime.fromisoformat(it["time"]).strftime("%H:%M UTC")
        when = f' · <time datetime="{esc(it["time"])}">{t}</time>'
    cat = slug(it["category"])
    text = f"{it['title']} {it['summary']} {it['source']}".lower()
    return f"""<article class="card{' card--top' if top else ''}" data-cat="{cat}" data-text="{esc(text)}">
<span class="pill pill--{cat}">{esc(it['category'])}</span>
<h3><a href="{esc(it['link'])}" target="_blank" rel="noopener">{esc(it['title'])}</a></h3>
<p>{esc(it['summary'])}</p>
<div class="meta"><b>{esc(it['source'])}</b>{when}</div>
</article>"""


FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
           "viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
           "fill='%230E3B2E'/%3E%3Ctext x='16' y='21' font-size='11' "
           "font-family='Arial' font-weight='900' fill='%23FFD84D' "
           "text-anchor='middle'%3ECPG%3C/text%3E%3C/svg%3E")


def page_shell(title, root, body):
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="Daily European consumer-goods news: M&amp;A, launches, retail moves and regulation.">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="icon" href="{FAVICON}">
<script>try{{var t=localStorage.getItem("theme");if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
</head><body data-root="{root}">
{body}
<script src="{root}assets/app.js" defer></script>
</body></html>"""


def header(root, badge, stats="", active="today"):
    def cur(name):
        return ' aria-current="page"' if active == name else ""
    return f"""<header class="masthead"><div class="wrap">
<div class="masthead__top">
<a class="brand" href="{root}index.html">{SITE_TITLE}</a>
<nav class="nav">
<a href="{root}index.html"{cur('today')}>Today</a>
<a href="{root}archive/index.html"{cur('archive')}>Archive</a>
<button class="theme-toggle" type="button" aria-label="Toggle dark mode" title="Toggle dark mode"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
</nav></div>
<div class="datebadge">{esc(badge)}</div>
<p class="subline">European consumer-goods headlines — M&amp;A, launches, retail moves &amp; regulation. Updated every morning.</p>
{f'<p class="stats">{stats}</p>' if stats else ''}
</div></header>"""


def toolbar(chips, scope="edition"):
    chip_html = "".join(
        f'<button type="button" class="chip" data-filter="{key}" '
        f'aria-pressed="{"true" if key == "all" else "false"}">'
        f'{esc(label)}<span class="chip__n">{n}</span></button>'
        for key, label, n in chips)
    if scope == "edition":
        placeholder = "Search this edition…"
        extra = ('<label class="scope"><input type="checkbox" id="scope-all">'
                 ' All editions</label>')
    else:
        placeholder = "Search every edition…"
        extra = ""
    chips_row = (f'<div class="chips" role="toolbar" aria-label="Filter by '
                 f'section">{chip_html}</div>' if chips else "")
    return f"""<div class="toolbar"><div class="wrap">
<div class="searchrow" role="search">
<span class="searchbox"><input id="q" type="search" placeholder="{placeholder}" autocomplete="off" aria-label="Search stories" data-scope="{scope}"><kbd>/</kbd></span>
{extra}
</div>
{chips_row}
</div></div>"""


def render_page(items, stamp, root=""):
    top, sections = split_sections(items)
    shown = len(top) + sum(len(r) for _, r in sections)
    sources = len({i["source"] for i in items})
    stats = (f"<b>{shown}</b> stories from <b>{sources}</b> sources"
             if shown else "")

    chips = [("all", "All", shown)]
    if top:
        chips.append(("top", "Top Stories", len(top)))
    chips += [(slug(cat), cat, len(rows)) for cat, rows in sections]

    body = []
    if top:
        body.append('<section class="section" data-section="top">'
                    '<h2 class="section__title">Top Stories</h2>'
                    '<div class="grid grid--top">'
                    + "".join(render_card(i, top=True) for i in top)
                    + "</div></section>")
    for cat, rows in sections:
        body.append(f'<section class="section" data-section="{slug(cat)}">'
                    f'<h2 class="section__title">{esc(cat)}</h2>'
                    '<div class="grid">'
                    + "".join(render_card(i) for i in rows)
                    + "</div></section>")

    if body:
        body.append('<div class="empty" id="nomatch" hidden>No stories in '
                    'this edition match your search. <button type="button" '
                    'class="linkbtn" id="search-all-btn">Search all editions '
                    '→</button></div>')
    else:
        body = [f'<div class="empty">No fresh stories were collected for '
                f'this edition. Browse the <a href="{root}archive/index.html">'
                f'archive</a> or search past editions above.</div>']

    main = f"""{header(root, pretty_date(stamp), stats)}
{toolbar(chips if shown else [])}
<main class="wrap" id="main">
<div id="results" class="results" hidden></div>
<div id="edition">{''.join(body)}</div>
<footer class="footer">Generated automatically from public RSS feeds.
Headlines and summaries link to and belong to their original publishers.</footer>
</main>
<a href="#" class="totop" aria-label="Back to top">↑</a>"""
    return page_shell(f"{SITE_TITLE} — {pretty_date(stamp)}", root, main)


def render_archive_index(editions):
    """editions: list of (stamp, items), newest first."""
    months = {}
    for stamp, items in editions:
        months.setdefault(stamp[:7], []).append((stamp, items))

    blocks = []
    for month, eds in months.items():
        label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        tiles = []
        for stamp, items in eds:
            d = datetime.strptime(stamp, "%Y-%m-%d")
            lead = items[0]["title"] if items else "No stories collected"
            tiles.append(
                f'<a class="tile{" tile--empty" if not items else ""}" '
                f'href="{stamp}.html"><span class="tile__day">'
                f'{d.strftime("%a")}<b>{d.day}</b></span>'
                f'<span class="tile__body"><span class="tile__count">'
                f'{len(items)} stor{"y" if len(items) == 1 else "ies"}</span><span class="tile__lead">'
                f'{esc(lead)}</span></span></a>')
        blocks.append(f'<section class="section"><h2 class="section__title">'
                      f'{label}</h2><div class="tiles">{"".join(tiles)}'
                      f'</div></section>')

    total = sum(len(i) for _, i in editions)
    stats = f"<b>{len(editions)}</b> editions · <b>{total}</b> stories"
    main = f"""{header("../", "Archive", stats, active="archive")}
{toolbar([], scope="all")}
<main class="wrap" id="main">
<div id="results" class="results" hidden></div>
<div id="edition">{''.join(blocks) or '<div class="empty">No editions yet.</div>'}</div>
<footer class="footer">Generated automatically from public RSS feeds.</footer>
</main>
<a href="#" class="totop" aria-label="Back to top">↑</a>"""
    return page_shell(f"{SITE_TITLE} — Archive", "../", main)


def build_search_index(editions):
    return [{"d": stamp, "t": it["title"], "l": it["link"],
             "s": clean_text(it["summary"], 180), "src": it["source"],
             "c": it["category"]}
            for stamp, items in editions for it in items]


def load_editions():
    """All saved editions, newest first, re-classified with current rules."""
    editions = []
    for p in sorted((DOCS / "data").glob("*.json"), reverse=True):
        data = json.loads(p.read_text(encoding="utf-8"))
        items = sort_items([classify(it) for it in data["items"]])
        editions.append((p.stem, items))
    return editions


def write_site(editions, render_days):
    """Write archive pages for render_days, plus index, archive & search."""
    (DOCS / "archive").mkdir(parents=True, exist_ok=True)
    by_day = dict(editions)
    for stamp in render_days:
        (DOCS / "archive" / f"{stamp}.html").write_text(
            render_page(by_day[stamp], stamp, root="../"), encoding="utf-8")
    if editions:
        latest, items = editions[0]
        (DOCS / "index.html").write_text(
            render_page(items, latest), encoding="utf-8")
    (DOCS / "archive" / "index.html").write_text(
        render_archive_index(editions), encoding="utf-8")
    (DOCS / "search-index.json").write_text(
        json.dumps(build_search_index(editions), ensure_ascii=False,
                   separators=(",", ":")), encoding="utf-8")


# ----------------------------- main ----------------------------------------

def main():
    (DOCS / "data").mkdir(parents=True, exist_ok=True)

    if "--rebuild" in sys.argv:
        editions = load_editions()
        write_site(editions, [s for s, _ in editions])
        print(f"Rebuilt {len(editions)} editions.")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items, failures = collect(stamp)
    (DOCS / "data" / f"{stamp}.json").write_text(
        json.dumps({"date": stamp, "items": items, "failed_feeds": failures},
                   indent=1), encoding="utf-8")

    write_site(load_editions(), [stamp])
    print(f"\nDone: {len(items)} items, {len(failures)} feed(s) failed.")


if __name__ == "__main__":
    main()
