from __future__ import annotations

import tweepy


class XClient:
    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        bearer_token: str,
        access_token: str,
        access_token_secret: str,
    ) -> None:
        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True,
        )

    def post_text(self, text: str) -> str:
        if len(text) > 280:
            raise ValueError("Post exceeds 280 characters.")

        response = self.client.create_tweet(text=text)
        data = response.data or {}
        tweet_id = data.get("id")
        if not tweet_id:
            raise RuntimeError("Tweet posted but no tweet ID returned.")
        return str(tweet_id)
