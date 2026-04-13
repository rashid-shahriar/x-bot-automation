from __future__ import annotations

import logging
import random
import time

import feedparser
from google import genai
from google.genai import errors as genai_errors

logger = logging.getLogger("x-bot")

_RSS_FEEDS = [
    "https://hnrss.org/frontpage",           # Hacker News front page
    "https://dev.to/feed/tag/programming",   # DEV.to programming
    "https://dev.to/feed/tag/ai",            # DEV.to AI
    "https://dev.to/feed/tag/webdev",        # DEV.to webdev
    "https://dev.to/feed/tag/devops",        # DEV.to devops
]

_PROMPT_TEMPLATE = """You are a senior software engineer who tweets casually about tech. Your tweets get high engagement because they're opinionated, specific, and feel like something a real developer would say — not a content creator.

Today's trending tech headlines for inspiration:
{trending_topics}

Write ONE tweet inspired by these topics. Use one of these high-engagement formats (pick randomly):
- A hot take: "Unpopular opinion: [specific dev opinion]"
- A hard truth: "[something developers avoid admitting] and we all know it."
- A practical insight: "One thing I wish I knew earlier: [specific tip]"
- A pattern observation: "Every [X] years, developers rediscover [Y] and call it new."
- A short story opener: "Just spent 3 hours debugging [X]. Turned out to be [Y]. I hate this job."
- A provocative question that makes devs think

Rules:
- Write like a human developer, NOT a marketing bot or content creator
- Be specific — use real tech names (Python, Docker, Supabase, React, etc.)
- NO motivational fluff, NO "In today's fast-paced world", NO "Let's dive in"
- NO phrases: "game-changer", "revolutionize", "It's important to note", "leverage"
- Max 1 hashtag, only if it adds value. NEVER truncate hashtag words.
- Under 260 characters total
- Make it something a developer would actually retweet

Output ONLY the tweet text, nothing else."""

_PROMO_PROMPT_TEMPLATE = """You are a senior software engineer who tweets honestly about tools you use. You occasionally mention products you like — but only when it genuinely fits the conversation.

Today's trending tech headlines:
{trending_topics}

Naturally work in a mention of ONE of these products:

1. Doran Pay (https://doranpay.com) — Invoicing for freelancers/businesses. Create, send, track invoices. PayPal/Stripe built-in. Free plan. Great if you're tired of chasing payments.

2. SupaBackup (https://www.supabackup.com) — Auto-backups for your Supabase database to Google Drive. 30-second setup, free tier. The kind of thing you set up AFTER losing data once.

Pick whichever fits the trending topics. Write ONE tweet that:
- Sounds like a personal recommendation from a developer who actually uses it
- Ties naturally into the trending topic (e.g. if AI is trending → tie to automation/backups)
- Includes the product URL
- Feels like "I use this and it solved X problem" — not an ad
- Max 1 hashtag, FULL word only, only if it adds value
- Under 260 characters total
- NO "check out", "you should try", "game-changer", "revolutionize"

Good example style: "Lost a Supabase DB once. Never again. SupaBackup sends it to Drive automatically — 30 sec setup, free tier. supabackup.com"

Output ONLY the tweet text, nothing else."""

_PROMO_EVERY_N = 4  # every 4th post is a product promo

_FALLBACK_TOPICS = [
    "The pace of AI advancements in 2026 has been staggering.",
    "Rust is taking over systems programming from C++.",
    "Prompt engineering is now a core skill for every developer.",
    "Open-source LLMs are closing the gap with proprietary models.",
    "TypeScript adoption keeps growing in large codebases.",
    "Serverless is no longer experimental — it's the default.",
    "The best code is the code you don't have to maintain.",
    "Every developer should learn SQL properly at least once.",
]


class GeminiContentSource:
    def __init__(self, gemini_api_key: str) -> None:
        self._genai_client = genai.Client(api_key=gemini_api_key)
        self._post_count = 0

    def _fetch_trending_topics(self) -> list[str]:
        titles: list[str] = []
        for url in _RSS_FEEDS:
            try:
                feed = feedparser.parse(url)
                titles += [e.title for e in feed.entries[:4] if e.get("title")]
            except Exception:
                logger.warning("Failed to fetch RSS feed: %s", url)
        if not titles:
            return []
        random.shuffle(titles)
        return titles[:6]

    def next_post(self) -> str:
        self._post_count += 1
        is_promo = self._post_count % _PROMO_EVERY_N == 0

        topics = self._fetch_trending_topics()
        if not topics:
            logger.warning("All RSS feeds failed, using fallback topics.")
            topics = random.sample(_FALLBACK_TOPICS, 4)

        bullet_list = "\n".join(f"- {t}" for t in topics)
        prompt = (
            _PROMO_PROMPT_TEMPLATE.format(trending_topics=bullet_list)
            if is_promo
            else _PROMPT_TEMPLATE.format(trending_topics=bullet_list)
        )

        response = self._generate_with_retry(prompt)
        text = response.text.strip().strip('"').strip("'")

        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0]

        kind = "promo" if is_promo else "regular"
        logger.info("Generated %s tweet (%d chars): %s", kind, len(text), text)
        return text

    def _generate_with_retry(self, prompt: str, max_retries: int = 4):
        delay = 20
        for attempt in range(max_retries):
            try:
                return self._genai_client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=prompt,
                )
            except (genai_errors.ClientError, genai_errors.ServerError) as exc:
                retryable = (
                    isinstance(exc, genai_errors.ServerError)
                    or (isinstance(exc, genai_errors.ClientError) and exc.status_code == 429)
                )
                if retryable and attempt < max_retries - 1:
                    logger.warning("Gemini unavailable, retrying in %ds (attempt %d/%d)...", delay, attempt + 1, max_retries)
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise
