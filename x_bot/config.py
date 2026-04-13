from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    consumer_key: str
    consumer_secret: str
    bearer_token: str
    access_token: str
    access_token_secret: str
    gemini_api_key: str
    timezone: str
    posts_per_day: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    load_dotenv()

    posts_per_day = int(os.getenv("POSTS_PER_DAY", "10"))
    if posts_per_day < 1 or posts_per_day > 48:
        raise ValueError("POSTS_PER_DAY must be between 1 and 48.")

    return Settings(
        consumer_key=_required("X_CONSUMER_KEY"),
        consumer_secret=_required("X_CONSUMER_SECRET"),
        bearer_token=_required("X_BEARER_TOKEN"),
        access_token=_required("X_ACCESS_TOKEN"),
        access_token_secret=_required("X_ACCESS_TOKEN_SECRET"),
        gemini_api_key=_required("GEMINI_API_KEY"),
        timezone=os.getenv("TIMEZONE", "UTC"),
        posts_per_day=posts_per_day,
    )
