from __future__ import annotations

import base64
import logging

import requests
from requests_oauthlib import OAuth1

logger = logging.getLogger("x-bot")

_TWEET_URL = "https://api.x.com/2/tweets"
_MEDIA_UPLOAD_URL = "https://upload.x.com/1.1/media/upload.json"


class XClient:
    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
    ) -> None:
        self._oauth = OAuth1(
            consumer_key, consumer_secret, access_token, access_token_secret
        )

    def post_text(self, text: str) -> str:
        if len(text) > 280:
            raise ValueError("Post exceeds 280 characters.")
        resp = requests.post(
            _TWEET_URL, json={"text": text}, auth=self._oauth, timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]["id"]

    def post_with_image(self, text: str, image_bytes: bytes) -> str:
        if len(text) > 280:
            raise ValueError("Post exceeds 280 characters.")
        # Upload image via v1.1 simple upload (base64)
        upload_resp = requests.post(
            _MEDIA_UPLOAD_URL,
            data={
                "media_data": base64.b64encode(image_bytes).decode(),
                "media_category": "tweet_image",
            },
            auth=self._oauth,
            timeout=30,
        )
        upload_resp.raise_for_status()
        media_id = upload_resp.json()["media_id_string"]
        logger.info("Uploaded media: %s", media_id)
        # Post tweet with media via v2
        resp = requests.post(
            _TWEET_URL,
            json={"text": text, "media": {"media_ids": [media_id]}},
            auth=self._oauth,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"]["id"]
