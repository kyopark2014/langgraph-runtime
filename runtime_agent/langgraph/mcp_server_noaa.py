#!/usr/bin/env python3
"""
MCP server for NOAA weather/climate news with energy-impact tagging.

RSS fetch + energy classification logic lives in this file (aligned with the
noaa-energy-news skill behavior). No subprocess or skills/ script imports.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import requests
from mcp.server.fastmcp import FastMCP


logging.basicConfig(
    level=logging.INFO,
    format="%(filename)s:%(lineno)d | %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("mcp-server-noaa")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

FEEDS = {
    "noaa": {
        "name": "NOAA Main News",
        "url": "https://www.noaa.gov/rss.xml",
        "category": "general",
    },
    "highlights": {
        "name": "NOAA Climate.gov Highlights",
        "url": "https://www.climate.gov/feeds/news-features/highlights.rss",
        "category": "climate",
    },
    "climate": {
        "name": "NOAA Climate & Life",
        "url": "https://www.climate.gov/feeds/news-features/climateand.rss",
        "category": "climate",
    },
    "enso": {
        "name": "NOAA ENSO Blog",
        "url": "https://www.climate.gov/feeds/news-features/enso.rss",
        "category": "climate",
    },
    "billion-dollar": {
        "name": "NOAA Billion-Dollar Disasters",
        "url": "https://www.climate.gov/feeds/news-features/beyond-the-data.rss",
        "category": "disaster",
    },
    "understanding": {
        "name": "NOAA Understanding Climate",
        "url": "https://www.climate.gov/feeds/news-features/understandingclimate.rss",
        "category": "climate",
    },
}

ENERGY_IMPACT_RULES = {
    "electricity_demand": {
        "keywords": [
            "heat wave", "cold snap", "polar vortex", "extreme cold", "extreme heat",
            "temperature record", "heat dome", "winter storm", "power demand",
            "electricity demand", "peak load", "grid stress", "blackout", "brownout",
            "record high temperature", "record low temperature", "cooling degree",
            "heating degree", "AC demand", "air conditioning",
        ],
        "label": "⚡ 전력 수요 변화",
        "description": "극단적 기온 이벤트로 인한 냉난방 전력 수요 급증/감소",
    },
    "renewable_energy": {
        "keywords": [
            "solar radiation", "cloud cover", "wind speed", "wind pattern",
            "wind energy", "solar energy", "renewable energy", "offshore wind",
            "drought", "precipitation", "hydropower", "water level", "snowpack",
            "sea ice", "arctic amplification", "jet stream", "atmospheric river",
        ],
        "label": "🌱 재생에너지 영향",
        "description": "태양광·풍력·수력 발전량에 영향을 주는 기후 요인",
    },
    "fossil_fuel": {
        "keywords": [
            "hurricane", "tropical storm", "flooding", "flood", "storm surge",
            "pipeline", "refinery", "natural gas", "oil production", "Gulf of Mexico",
            "offshore platform", "energy infrastructure", "power plant", "coal",
        ],
        "label": "🛢️ 화석연료 인프라",
        "description": "허리케인·홍수 등으로 인한 발전소·파이프라인 운영 영향",
    },
    "wildfire_energy": {
        "keywords": [
            "wildfire", "fire weather", "red flag warning", "fire season",
            "smoke", "air quality", "power line", "utility", "PSPS",
            "Public Safety Power Shutoff", "transmission line",
        ],
        "label": "🔥 산불·전력망 영향",
        "description": "산불 리스크로 인한 전력망 가동 중단·예방 차단 영향",
    },
    "climate_long_term": {
        "keywords": [
            "global warming", "climate change", "sea level rise", "permafrost",
            "carbon", "CO2", "greenhouse gas", "emission", "temperature trend",
            "decarbonization", "net zero", "ENSO", "El Nino", "La Nina",
            "Arctic", "glacier", "ice sheet", "ocean warming",
        ],
        "label": "🌍 장기 기후 리스크",
        "description": "기후변화로 인한 에너지 시스템 장기 전환 압력",
    },
    "severe_weather_grid": {
        "keywords": [
            "tornado", "severe thunderstorm", "hail", "ice storm", "derecho",
            "outage", "power outage", "damage", "infrastructure damage",
            "flooding", "storm", "blizzard", "nor'easter",
        ],
        "label": "🌪️ 기상재해·전력망",
        "description": "극단적 기상 현상으로 인한 전력 공급 차질",
    },
}

FEED_CHOICES = frozenset(list(FEEDS.keys()) + ["all"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _sanitize_feed(feed: str) -> str:
    f = (feed or "all").lower().strip()
    return f if f in FEED_CHOICES else "all"


def _norm_keyword(keyword: str | None) -> str | None:
    if keyword is None:
        return None
    s = str(keyword).strip()
    return s if s else None


def classify_energy_impact(title: str, description: str) -> list[dict[str, Any]]:
    text = (title + " " + description).lower()
    impacts: list[dict[str, Any]] = []
    for key, rule in ENERGY_IMPACT_RULES.items():
        matched = [kw for kw in rule["keywords"] if kw.lower() in text]
        if matched:
            impacts.append(
                {
                    "category": key,
                    "label": rule["label"],
                    "description": rule["description"],
                    "matched_keywords": matched[:5],
                }
            )
    return impacts


def fetch_feed(feed_key: str, limit: int = 5, keyword: str | None = None) -> list[dict[str, Any]]:
    feed_info = FEEDS[feed_key]
    try:
        resp = requests.get(feed_info["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return [{"error": f"Failed to fetch {feed_info['name']}: {e}"}]

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        return [{"error": f"XML parse error for {feed_info['name']}: {e}"}]

    channel = root.find("channel")
    if channel is None:
        return [{"error": f"No channel element in {feed_info['name']}"}]

    articles: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = re.sub(r"<[^>]+>", " ", item.findtext("description", "")).strip()

        if keyword:
            combined = (title + " " + description).lower()
            if keyword.lower() not in combined:
                continue

        impacts = classify_energy_impact(title, description)

        articles.append(
            {
                "feed": feed_info["name"],
                "feed_category": feed_info["category"],
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "description": description[:300] + ("..." if len(description) > 300 else ""),
                "energy_impacts": impacts,
                "has_energy_relevance": len(impacts) > 0,
            }
        )

        if len(articles) >= limit:
            break

    return articles


def fetch_all(limit_per_feed: int = 5, keyword: str | None = None) -> dict[str, Any]:
    all_articles: list[dict[str, Any]] = []
    fetch_errors: list[str] = []

    for feed_key in FEEDS:
        results = fetch_feed(feed_key, limit=limit_per_feed, keyword=keyword)
        for r in results:
            if "error" in r:
                fetch_errors.append(str(r["error"]))
            else:
                all_articles.append(r)

    all_articles.sort(key=lambda x: (not x["has_energy_relevance"], x.get("pub_date", "")))

    return {
        "fetched_at": _utc_now_iso(),
        "total_articles": len(all_articles),
        "energy_relevant_count": sum(1 for a in all_articles if a["has_energy_relevance"]),
        "articles": all_articles,
        "errors": fetch_errors,
    }


def format_energy_news_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    fetched = result.get("fetched_at", "")
    total = result.get("total_articles", 0)
    energy_count = result.get("energy_relevant_count", 0)
    lines.append("## 🌦️ NOAA 날씨·기후 뉴스 — 에너지 영향 요약")
    lines.append(f"**조회 시각**: {fetched}  |  **에너지 관련 기사**: {energy_count}건 / 전체 {total}건")

    errors = result.get("errors") or []
    if errors:
        lines.append("\n**경고(피드 수집 오류)**:")
        for err in errors[:8]:
            lines.append(f"- {err}")
        if len(errors) > 8:
            lines.append(f"- ... 외 {len(errors) - 8}건")

    articles = result.get("articles") or []
    idx = 0
    for a in articles:
        if "error" in a:
            lines.append("")
            lines.append(f"- ⚠️ {a['error']}")
            continue
        idx += 1
        title = a.get("title", "")
        link = a.get("link", "")
        pub = a.get("pub_date", "")
        feed_name = a.get("feed", "")
        desc = a.get("description", "")
        impacts = a.get("energy_impacts") or []

        lines.append("")
        lines.append("---")
        lines.append(f"### {idx}. [{title}]({link})")
        lines.append(f"📅 {pub} | 📡 {feed_name}")
        lines.append(f"**요약**: {desc}")
        if impacts:
            parts = []
            for im in impacts:
                lbl = im.get("label", "")
                kws = ", ".join(im.get("matched_keywords", [])[:3])
                parts.append(f"{lbl}" + (f" ({kws})" if kws else ""))
            lines.append("**에너지 영향**: " + " | ".join(parts))
        else:
            lines.append("**에너지 영향**: (키워드 매칭 없음)")

    if idx == 0 and not any("error" in x for x in articles if isinstance(x, dict)):
        lines.append("")
        lines.append("표시할 기사가 없습니다.")

    return "\n".join(lines).strip()


def run_noaa_energy_news(
    feed: str = "all",
    limit: int = 5,
    keyword: str | None = None,
    output_format: str = "text",
) -> str:
    feed = _sanitize_feed(feed)
    limit = _sanitize_int(limit, default=5, min_value=1, max_value=50)
    keyword = _norm_keyword(keyword)
    output_format = "json" if str(output_format).lower() == "json" else "text"

    if feed == "all":
        result = fetch_all(limit_per_feed=limit, keyword=keyword)
    else:
        articles = fetch_feed(feed, limit=limit, keyword=keyword)
        result = {
            "fetched_at": _utc_now_iso(),
            "total_articles": len(articles),
            "energy_relevant_count": sum(1 for a in articles if a.get("has_energy_relevance")),
            "articles": articles,
            "errors": [],
        }

    if output_format == "json":
        return json.dumps(result, ensure_ascii=False, indent=2)
    return format_energy_news_text(result)


mcp = FastMCP(
    name="noaa-energy-news",
    instructions=(
        "미국 NOAA(noaa.gov) 및 NOAA Climate.gov RSS에서 날씨·기후 뉴스를 가져오고, "
        "키워드 규칙으로 전력·에너지 관련성(energy_impacts, has_energy_relevance)을 태깅합니다. "
        "feed는 all 또는 개별 피드(noaa, highlights, climate, enso, billion-dollar, understanding), "
        "limit은 피드당 최대 기사 수입니다."
    ),
)


@mcp.tool()
def get_noaa_energy_news(
    feed: str = "all",
    limit: int = 5,
    keyword: str | None = None,
    output_format: str = "text",
) -> str:
    """
    NOAA·Climate.gov RSS에서 기사를 수집하고 에너지 영향 태그를 붙입니다 (noaa-energy-news 스킬과 동일 로직).

    Args:
        feed: 'all' 또는 'noaa' | 'highlights' | 'climate' | 'enso' | 'billion-dollar' | 'understanding'
        limit: 피드당 최대 기사 수 (1~50, 기본 5)
        keyword: 제목·본문에 포함된 키워드로 필터 (선택)
        output_format: 'text' (마크다운 요약) 또는 'json' (원시 구조화 결과)
    """
    logger.info(
        "get_noaa_energy_news --> feed=%s, limit=%s, keyword=%s, format=%s",
        feed,
        limit,
        keyword,
        output_format,
    )
    return run_noaa_energy_news(feed, limit, keyword, output_format)


@mcp.tool()
def get_noaa_weather_news(
    days: int = 7,
    max_articles: int = 10,
    pages: int = 2,
    output_format: str = "text",
) -> str:
    """
    (하위 호환) 예전 NOAA MCP 도구 이름. `get_noaa_energy_news` 사용을 권장합니다.
    days·pages는 RSS 모델상 사용하지 않으며 무시됩니다. limit은 max_articles와 동일하게 적용됩니다.
    """
    _ = (days, pages)
    lim = _sanitize_int(max_articles, default=10, min_value=1, max_value=50)
    logger.info(
        "get_noaa_weather_news (legacy) --> max_articles as limit=%s, format=%s",
        lim,
        output_format,
    )
    return run_noaa_energy_news("all", lim, None, output_format)


if __name__ == "__main__":
    mcp.run(transport="stdio")
