from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import errors as genai_errors

from x_bot.image_fetcher import fetch_rss_entries, fetch_rss_titles

logger = logging.getLogger("x-bot")


@dataclass
class PostResult:
    text: str
    pexels_query: Optional[str] = None


_RSS_FEEDS = [
    "https://hnrss.org/frontpage",
    "https://dev.to/feed/tag/programming",
    "https://dev.to/feed/tag/ai",
    "https://dev.to/feed/tag/webdev",
    "https://dev.to/feed/tag/devops",
]

_FALLBACK_TOPICS = [
    "The pace of AI advancements in 2026 has been staggering.",
    "Rust is taking over systems programming from C++.",
    "Prompt engineering is now a core skill for every developer.",
    "Open-source LLMs are closing the gap with proprietary models.",
    "TypeScript adoption keeps growing in large codebases.",
    "Serverless is no longer experimental -- it's the default.",
    "The best code is the code you don't have to maintain.",
    "Every developer should learn SQL properly at least once.",
]

# --- Prompts ---

_NEWS_PROMPT = """You are @rashid_js_dev on X -- a developer who shares breaking tech news with quick, sharp reactions.

Here is a real trending headline:
Title: {headline}
Link: {link}

Create ONE engaging tweet that:
- Starts with a relevant emoji (fire, rocket, eyes, brain, warning, etc.)
- Shares the news headline in a natural, conversational way (don't just copy-paste the title)
- Adds a SHORT developer reaction (1 sentence max) -- your honest take, surprise, or hot opinion
- Includes the article link at the end
- Uses 1-2 emojis total (start + optionally one more)

Examples of the style:
- "🔥 OpenAI just open-sourced their tokenizer. About time. This is going to break half the custom BPE implementations out there. https://link.com"
- "👀 Vercel acquired a database company. Next.js is slowly becoming an entire cloud platform. https://link.com"
- "🚀 Rust just hit #2 on TIOBE. C++ devs sweating. https://link.com"
- "🧠 Google DeepMind says AGI is 3 years away. Again. https://link.com"
- "⚠️ Major npm supply chain attack -- 50+ packages compromised. Check your lockfiles. https://link.com"

Rules:
- Keep it under 250 chars (leave room for the link)
- Sound like a real dev sharing news, not a news bot
- The reaction should feel genuine -- surprise, skepticism, excitement, or dry humor
- NO: "game-changer", "revolutionary", "breaking:", "BREAKING:"
- NO hashtags

Output ONLY the tweet text with the link. Nothing else."""

_PHOTO_PROMPT = """You are @rashid_js_dev -- a developer who posts sharp, visual content on X.

Today's trending tech topics:
{topics}

Write ONE punchy caption (1 line, max 150 chars) that:
- Starts with a relevant emoji
- Captures a developer mood or moment (late night coding, deploy anxiety, clean code satisfaction)
- Is short enough that the IMAGE does the heavy lifting
- Feels like a text you'd send a dev friend
- NO hashtags, NO links

Examples:
- "😴 3 AM. CI is green. I'm afraid to touch anything."
- "🔥 This is what 'just a quick refactor' looks like 6 hours later."
- "🫡 The calm before the deploy."
- "💀 Production logs at 2 AM hit different."

Also give a 2-4 word Pexels search query for a photo that matches the MOOD (not literal).

Output EXACTLY:
TWEET: <caption>
QUERY: <pexels query>"""

_PROMO_PROMPT = """You are @rashid_js_dev. You sometimes mention tools you actually use -- but only when it fits naturally.

Today's trending tech headlines:
{topics}

Work in a mention of ONE of these (pick whichever ties in naturally):

1. Doran Pay (https://doranpay.com) -- invoicing tool, PayPal/Stripe, free plan
2. SupaBackup (https://www.supabackup.com) -- auto Supabase backups to Google Drive, free tier

Write ONE tweet where:
- Start with a relevant emoji
- The product mention feels like an afterthought in a larger point
- The tweet works even WITHOUT the product mention
- Include the URL naturally

Examples:
- "💸 After my third client 'forgot' to pay, I just set up doranpay.com and stopped chasing. Should've done it months ago."
- "💀 Supabase is great until you accidentally drop a table in prod. supabackup.com exists for a reason."
- "🧾 Freelancing tip nobody tells you: automate invoicing on day 1. I use doranpay.com -- free plan, takes 2 minutes."

Rules:
- 100-220 characters. Never exceed 280.
- Use 1-2 emojis
- NO: "check out", "you should try", "game-changer", "highly recommend"

Output ONLY the tweet text. Nothing else."""

# 12-slot cycle: 8 news, 2 photo, 2 promo
_CYCLE = [
    "news", "news", "photo",
    "news", "promo", "news",
    "news", "photo", "news",
    "promo", "news", "news",
]


class GeminiContentSource:
    def __init__(self, gemini_api_key: str) -> None:
        self._client = genai.Client(api_key=gemini_api_key)
        self._count = 0
        self._used_links: set[str] = set()

    def next_post(self) -> PostResult:
        self._count += 1
        kind = _CYCLE[(self._count - 1) % len(_CYCLE)]

        if kind == "news":
            return self._make_news_post()

        # For photo/promo we still need topic headlines as context
        titles = fetch_rss_titles(_RSS_FEEDS)
        topics = "\n".join(f"- {t}" for t in titles) if titles else "\n".join(f"- {t}" for t in random.sample(_FALLBACK_TOPICS, 4))

        if kind == "photo":
            raw = self._generate(_PHOTO_PROMPT.format(topics=topics))
            return self._parse_photo(raw)

        # promo
        raw = self._generate(_PROMO_PROMPT.format(topics=topics))
        text = raw.strip('"').strip("'")
        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0]
        logger.info("Generated promo tweet (%d chars): %s", len(text), text)
        return PostResult(text=text)

    def _make_news_post(self) -> PostResult:
        entries = fetch_rss_entries(_RSS_FEEDS)
        # Pick a headline we haven't used recently
        fresh = [e for e in entries if e.link not in self._used_links]
        if not fresh:
            self._used_links.clear()
            fresh = entries
        if not fresh:
            # Fallback if RSS is totally down
            topic = random.choice(_FALLBACK_TOPICS)
            return PostResult(text=f"🔥 {topic}")

        entry = fresh[0]
        self._used_links.add(entry.link)

        raw = self._generate(
            _NEWS_PROMPT.format(headline=entry.title, link=entry.link)
        )
        text = raw.strip('"').strip("'")
        # Ensure the link is in the tweet
        if entry.link not in text:
            space_left = 280 - len(text) - 1
            if space_left >= len(entry.link):
                text = f"{text} {entry.link}"
        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0]
        logger.info("Generated news tweet (%d chars): %s", len(text), text)
        return PostResult(text=text)

    def _parse_photo(self, raw: str) -> PostResult:
        text = query = ""
        for line in raw.splitlines():
            if line.startswith("TWEET:"):
                text = line[6:].strip().strip('"').strip("'")
            elif line.startswith("QUERY:"):
                query = line[6:].strip()
        if not text:
            text = raw.strip('"').strip("'")
        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0]
        logger.info("Generated photo tweet (%d chars) query=%r: %s", len(text), query, text)
        return PostResult(text=text, pexels_query=query or None)

    def _generate(self, prompt: str) -> str:
        delay = 20
        for attempt in range(4):
            try:
                resp = self._client.models.generate_content(
                    model="gemini-flash-latest", contents=prompt,
                )
                return resp.text.strip()
            except (genai_errors.ClientError, genai_errors.ServerError) as exc:
                retryable = isinstance(exc, genai_errors.ServerError) or (
                    isinstance(exc, genai_errors.ClientError) and exc.status_code == 429
                )
                if retryable and attempt < 3:
                    logger.warning("Gemini retry in %ds (%d/4)", delay, attempt + 1)
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise
