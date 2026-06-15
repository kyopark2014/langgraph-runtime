#!/usr/bin/env python3
"""
NOAA Weather News Fetcher - Energy Impact Focused
Fetches latest weather news from NOAA and ranks by energy demand relevance.

Usage:
    python fetch_noaa_news.py [--days 7] [--max 10] [--pages 2] [--format text|json]
    python fetch_noaa_news.py --days 7 --max 10           # default: 1-week, top-10
"""

import argparse
import html as html_module
import re
import sys
import json
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("[ERROR] requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NOAA_BASE = "https://www.noaa.gov"
NOAA_NEWS_URL = f"{NOAA_BASE}/news-features"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Energy-relevant keywords for scoring
ENERGY_KEYWORDS = [
    "heat wave", "heat advisory", "excessive heat", "record heat", "extreme heat",
    "extreme cold", "arctic blast", "wind chill", "polar vortex", "freeze", "frost",
    "cold snap", "record low", "record high", "temperature",
    "hurricane", "tropical storm", "typhoon", "cyclone",
    "severe storm", "thunderstorm", "derecho",
    "winter storm", "blizzard", "ice storm", "snowstorm", "heavy snow",
    "tornado", "severe weather",
    "drought", "wildfire", "fire weather", "red flag",
    "flood", "flash flood", "coastal flood", "storm surge",
    "outlook", "seasonal forecast", "summer forecast", "winter forecast",
    "above normal temperature", "below normal temperature",
    "warming", "cooling", "climate", "precipitation",
]

HIGH_PRIORITY = {
    "heat wave", "extreme cold", "winter storm", "hurricane", "drought",
    "wildfire", "flood", "severe weather", "tornado", "arctic",
    "temperature", "outlook", "forecast", "climate",
}

WEATHER_FOCUS = {"weather", "climate"}

# Minimum energy score to be included (0 = include all)
MIN_SCORE = 0


# ---------------------------------------------------------------------------
# HTML Fetch
# ---------------------------------------------------------------------------
def fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[ERROR] {url}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_articles(html: str) -> list[dict]:
    """Extract article entries from NOAA news-features HTML."""
    articles = []
    seen_urls: set[str] = set()

    block_re = re.compile(
        r'href="((?:/news(?:-release)?|/stories|/media-release|/news-release)[^"]+)"[^>]*>\s*'
        r'([^<]{10,250}?)\s*</a>'
        r'(?:.{0,1500}?(\w+ \d{1,2},\s*\d{4}))?',
        re.DOTALL,
    )

    for m in block_re.finditer(html):
        url_path = m.group(1)
        raw_title = m.group(2).strip()
        date_raw = m.group(3) or ""

        # Decode HTML entities (e.g. &#039; → ')
        title = html_module.unescape(re.sub(r"\s+", " ", raw_title)).strip()

        if len(title) < 10 or title.lower().startswith("view all"):
            continue

        full_url = NOAA_BASE + url_path
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        pub_date = None
        if date_raw:
            try:
                pub_date = datetime.strptime(date_raw.strip(), "%B %d, %Y").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        if pub_date is None:
            continue

        articles.append({
            "title": title,
            "url": full_url,
            "date": pub_date,
            "date_str": pub_date.strftime("%B %d, %Y"),
            "focus_areas": [],
            "topics": [],
        })

    return articles


def enrich_tags(articles: list[dict], html: str) -> list[dict]:
    """Attach focus-area and topic tags from surrounding HTML context."""
    for article in articles:
        path = article["url"].replace(NOAA_BASE, "")
        idx = html.find(path)
        if idx == -1:
            continue
        snippet = html[idx: idx + 1200]
        article["focus_areas"] = [
            f.replace("-", " ").title()
            for f in re.findall(r"focus-areas?/([a-z-]+)", snippet)
        ]
        article["topics"] = [
            t.replace("-", " ")
            for t in re.findall(r"topic-tags/([a-z0-9-]+)", snippet)
        ]
    return articles


# ---------------------------------------------------------------------------
# Scoring & Impact Summary
# ---------------------------------------------------------------------------
def score(article: dict) -> int:
    text = (article["title"] + " " + " ".join(article["topics"])).lower()
    s = 0
    for kw in ENERGY_KEYWORDS:
        if kw in text:
            s += 10
            if kw in HIGH_PRIORITY:
                s += 5
    for fa in article["focus_areas"]:
        if fa.lower() in WEATHER_FOCUS:
            s += 15
    return min(s, 100)


def energy_impact_summary(article: dict) -> str:
    text = (article["title"] + " " + " ".join(article["topics"])).lower()
    impacts = []
    if any(k in text for k in ["heat", "warm", "hot", "summer", "excessive heat"]):
        impacts.append("냉방 전력 수요 급증")
    if any(k in text for k in ["cold", "freeze", "winter", "snow", "arctic", "polar", "frost"]):
        impacts.append("난방 가스·전력 수요 급증")
    if any(k in text for k in ["hurricane", "tropical", "storm surge", "flood"]):
        impacts.append("전력망 피해·정전 위험")
    if any(k in text for k in ["drought", "wildfire", "fire"]):
        impacts.append("수력발전 감소·냉방 부하 증가")
    if any(k in text for k in ["outlook", "forecast", "seasonal", "precipitation"]):
        impacts.append("에너지 수요 선제 계획 필요")
    if any(k in text for k in ["tornado", "severe", "derecho", "thunderstorm"]):
        impacts.append("송전 인프라 피해 위험")
    if any(k in text for k in ["climate", "temperature", "warming", "cooling"]):
        impacts.append("장기 에너지 소비 패턴 변화")
    return " / ".join(impacts) if impacts else "날씨 변동에 따른 에너지 수요 모니터링 필요"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fetch NOAA weather news relevant to energy demand"
    )
    parser.add_argument("--days",   type=int, default=7,    help="Look-back window in days (default: 7)")
    parser.add_argument("--max",    type=int, default=10,   help="Max articles to return (default: 10)")
    parser.add_argument("--pages",  type=int, default=2,    help="NOAA pages to scan (default: 2)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    all_articles: list[dict] = []

    for page in range(args.pages):
        url = NOAA_NEWS_URL if page == 0 else f"{NOAA_NEWS_URL}?page={page}"
        print(f"[INFO] Fetching page {page + 1}: {url}", file=sys.stderr)
        html = fetch_html(url)
        if not html:
            continue
        parsed = parse_articles(html)
        parsed = enrich_tags(parsed, html)
        all_articles.extend(parsed)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    # Recency filter
    recent = [a for a in unique if a["date"] >= cutoff]
    print(
        f"[INFO] Total scanned={len(unique)}, within {args.days}d={len(recent)}",
        file=sys.stderr,
    )

    # Score, annotate, sort
    for a in recent:
        a["energy_score"] = score(a)
        a["energy_impact"] = energy_impact_summary(a)

    # Sort by energy_score desc, then date desc
    top = sorted(recent, key=lambda x: (x["energy_score"], x["date"]), reverse=True)[: args.max]

    # ---------------------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------------------
    today_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    if args.format == "json":
        out = [
            {
                "rank":         i + 1,
                "title":        a["title"],
                "url":          a["url"],
                "date":         a["date_str"],
                "energy_score": a["energy_score"],
                "energy_impact":a["energy_impact"],
                "focus_areas":  a["focus_areas"],
                "topics":       a["topics"],
            }
            for i, a in enumerate(top)
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*70}")
        print(f"  🌩  NOAA 미국 날씨 뉴스 — 에너지 수요 영향 분석")
        print(f"  📅 기준일: {today_str}  |  조회 기간: {cutoff_str} ~ {today_str}")
        print(f"{'='*70}\n")

        if not top:
            print(f"❌ 최근 {args.days}일 이내 에너지 관련 날씨 뉴스가 없습니다.\n")
            return

        for i, a in enumerate(top, 1):
            filled = a["energy_score"] // 10
            bar = "█" * filled + "░" * (10 - filled)
            print(f"[{i:02d}] 📰 {a['title']}")
            print(f"      📅 {a['date_str']}")
            print(f"      🔗 {a['url']}")
            print(f"      ⚡ 에너지 영향: {a['energy_impact']}")
            print(f"      📊 관련도: [{bar}] {a['energy_score']}/100")
            if a["topics"]:
                print(f"      🏷  {', '.join(a['topics'][:6])}")
            print()

        print(f"─ 총 {len(top)}건 표시 (후보 {len(recent)}건 / 전체 스캔 {len(unique)}건) ─\n")


if __name__ == "__main__":
    main()
