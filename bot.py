from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger

from x_bot.config import load_settings
from x_bot.gemini_content import GeminiContentSource
from x_bot.x_client import XClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("x-bot")


def schedule_daily_posts(
    scheduler: BlockingScheduler,
    posts_per_day: int,
    post_fn,
    immediate: bool = False,
) -> None:
    interval_minutes = 24 * 60 // posts_per_day
    now = datetime.now(scheduler.timezone)

    start_index = 1 if immediate else 0
    for i in range(start_index, posts_per_day):
        run_time = now + timedelta(minutes=i * interval_minutes)
        scheduler.add_job(
            post_fn,
            trigger=DateTrigger(run_date=run_time),
            id=f"post-once-{i}",
            replace_existing=True,
        )
        logger.info("Scheduled post %d/%d at %s", i + 1, posts_per_day, run_time.strftime("%H:%M"))

    scheduler.add_job(
        lambda: schedule_daily_posts(scheduler, posts_per_day, post_fn),
        trigger=DateTrigger(run_date=now + timedelta(days=1)),
        id="refresh-schedule",
        replace_existing=True,
    )


def main() -> None:
    settings = load_settings()

    x_client = XClient(
        consumer_key=settings.consumer_key,
        consumer_secret=settings.consumer_secret,
        bearer_token=settings.bearer_token,
        access_token=settings.access_token,
        access_token_secret=settings.access_token_secret,
    )

    content_source = GeminiContentSource(
        gemini_api_key=settings.gemini_api_key,
    )

    scheduler = BlockingScheduler(timezone=settings.timezone)

    def post_job() -> None:
        text = content_source.next_post()
        tweet_id = x_client.post_text(text)
        logger.info("Posted tweet %s", tweet_id)

    logger.info("Posting first tweet immediately...")
    try:
        post_job()
    except Exception:
        logger.exception("Initial post failed")

    schedule_daily_posts(scheduler, settings.posts_per_day, post_job, immediate=True)

    logger.info("Bot started — %d posts/day, timezone=%s", settings.posts_per_day, settings.timezone)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
