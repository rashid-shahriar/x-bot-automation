from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import errors as genai_errors

from x_bot.image_fetcher import fetch_rss_titles

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
    "Serverless is no longer experimental — it's the default.",
    "The best code is the code you don't have to maintain.",
    "Every developer should learn SQL properly at least once.",
]

# --- Prompts ---

_TEXT_PROMPT = """You are @rashid_js_dev — a real software developer who tweets raw, unfiltered thoughts about tech. You sound like a developer venting to friends, not writing content.

Here are examples of YOUR voice (study the tone, rhythm, and specificity):
- "Angular micro-frontends: 10% coding, 90% fighting Module Federation and dependency hell."
- "Every 5 years, devs rediscover that managing a Postgres HA cluster with Patroni and pgBouncer is a full-time job, then they crawl back to RDS."
- "The mass adoption of RAG in prod is going to create the same mess as microservices did — everyone bolts it on, nobody understands the retrieval layer, debugging becomes archaeology."
- "Shipped my first solo product 3 years ago. 12 users. Still the proudest I've ever been of code."
- "Docker Compose in prod is a rite of passage. You do it once, get burned, then finally learn Kubernetes. Or give up and use Railway."

Today's trending tech headlines:
{topics}

Write ONE tweet inspired by these headlines. Pick a format that fits naturally:
- A brutally honest observation about a tool/trend
- A "here's what actually happens" reality check
- A dev war story (short, specific, funny or painful)
- A pattern you've noticed in the industry
- A controversial but defensible opinion
- Something that would make a developer screenshot and share

CRITICAL RULES:
- Sound like a tired, smart developer — not a LinkedIn influencer
- Be SPECIFIC (name real tools, frameworks, versions, error messages)
- Short, punchy sentences. No fluff. No filler. Think bar conversation, not blog post.
- If you use a hashtag, max 1, and only if it genuinely helps discovery
- 80-200 characters is the sweet spot. NEVER exceed 280.
- NEVER start with "Unpopular opinion:" or any other cliché opener formula
- NO: "game-changer", "revolutionize", "leverage", "In today's world", "Let's dive in", "hot take:", "friendly reminder:"
- Do NOT summarize news. React to it like a human who just read the headline.

Output ONLY the tweet text. Nothing else."""

_PHOTO_PROMPT = """You are @rashid_js_dev — a developer who posts sharp, visual content on X. Your photo tweets feel effortless: a short thought paired with a beautiful image.

Today's trending tech topics:
{topics}

Write ONE punchy caption (1 line, max 150 chars) that:
- Captures a developer mood or moment (late night coding, deploy anxiety, clean code satisfaction)
- Is short enough that the IMAGE does the heavy lifting
- Feels like a text you'd send a dev friend, not a tweet you "crafted"
- NO hashtags, NO links

Examples of good photo captions:
- "3 AM. CI is green. I'm afraid to touch anything."
- "This is what 'just a quick refactor' looks like 6 hours later."
- "The calm before the deploy."

Also give a 2-4 word Pexels search query for a photo that matches the MOOD (not literal) — e.g. "dark office monitors", "calm sunrise desk", "messy cables closeup".

Output EXACTLY:
TWEET: <caption>
QUERY: <pexels query>"""

_PROMO_PROMPT = """You are @rashid_js_dev. You sometimes mention tools you actually use — but only when it fits what you're already talking about. It should read like a side comment, not a recommendation.

Today's trending tech headlines:
{topics}

Work in a mention of ONE of these (pick whichever ties in naturally):

1. Doran Pay (https://doranpay.com) — invoicing tool, PayPal/Stripe, free plan
2. SupaBackup (https://www.supabackup.com) — auto Supabase backups to Google Drive, free tier

Write ONE tweet where the product mention feels like an afterthought in a larger point. Like:
- "After my third client 'forgot' to pay, I just set up doranpay.com and stopped chasing. Should've done it months ago."
- "Supabase is great until you accidentally drop a table in prod. supabackup.com exists for a reason."

Rules:
- The tweet should work even WITHOUT the product mention — the observation is the hook
- Include the URL naturally (not "check out")
- 100-220 characters. Never exceed 280.
- NO: "check out", "you should try", "game-changer", "highly recommend"

Output ONLY the tweet text. Nothing else."""

# 12-slot cycle: 5 text, 5 photo, 2 promo
_CYCLE = [
    "text", "photo", "text",
    "text", "promo", "text",
    "photo", "text", "text",
    "text", "promo", "photo",
]


class GeminiContentSource:
    def __init__(self, gemini_api_key: str) -> None:
        self._client = genai.Client(api_key=gemini_api_key)
        self._count = 0

    def next_post(self) -> PostResult:
        self._count += 1
        kind = _CYCLE[(self._count - 1) % len(_CYCLE)]

        titles = fetch_rss_titles(_RSS_FEEDS)
        topics = "\n".join(f"- {t}" for t in titles) if titles else "\n".join(f"- {t}" for t in random.sample(_FALLBACK_TOPICS, 4))

        if kind == "photo":
            raw = self._generate(
                _PHOTO_PROMPT.format(topics=topics)
            )
            return self._parse_photo(raw)

        prompt = _PROMO_PROMPT if kind == "promo" else _TEXT_PROMPT
        raw = self._generate(prompt.format(topics=topics))
        text = raw.strip('"').strip("'")
        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0]
        logger.info("Generated %s tweet (%d chars): %s", kind, len(text), text)
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
