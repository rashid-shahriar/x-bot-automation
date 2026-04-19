from __future__ import annotations

import logging
import random

import feedparser
import requests

logger = logging.getLogger("x-bot")

_PEXELS_URL = "https://api.pexels.com/v1/search"


def fetch_pexels_image(query: str, api_key: str) -> bytes:
    """Search Pexels and return image bytes. Free for commercial use."""
    resp = requests.get(
        _PEXELS_URL,
        params={"query": query, "per_page": 5, "orientation": "landscape"},
        headers={"Authorization": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    if not photos:
        raise RuntimeError(f"No Pexels results for query={query!r}")
    photo = random.choice(photos)
    img = requests.get(photo["src"]["large"], timeout=15)
    img.raise_for_status()
    logger.info("Fetched Pexels image query=%r", query)
    return img.content


def fetch_rss_titles(feeds: list[str], max_per_feed: int = 4) -> list[str]:
    """Return a shuffled list of headline titles from RSS feeds."""
    titles: list[str] = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            titles += [e.title for e in feed.entries[:max_per_feed] if e.get("title")]
        except Exception:
            logger.warning("Failed to fetch RSS feed: %s", url)
    random.shuffle(titles)
    return titles[:8]
