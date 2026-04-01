"""
HTTP request layer — mirrors Nitter's apiutils.nim.

Handles:
- Building correct URLs for OAuth (api.x.com) vs cookie (x.com/i/api) sessions
- Generating request headers (OAuth1 HMAC-SHA1 or cookie-based)
- Reading x-rate-limit-* response headers back into session state
- Retry logic on rate limit errors
"""
from __future__ import annotations

import hashlib
import hmac
import math
import time
import urllib.parse
import uuid
from typing import Any, Optional

import httpx

from .sessions import Session, SessionKind, SessionPool

# ── Constants from consts.nim ────────────────────────────────────────────────

CONSUMER_KEY = "3nVuSoBZnx6U4vzUxf5w"
CONSUMER_SECRET = "Bcs59EFbbsdF6Sl9Ng71smgStWEGwXXKSjYvPVt7qys"
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
BEARER_TOKEN2 = (
    "AAAAAAAAAAAAAAAAAAAAAFXzAwAAAAAAMHCxpeSDG1gLNLghVe8d74hl6k4"
    "%3DRUMF4xAQLsbeBhTSRrCiQpJtxoGWeyHrDb5te2jpGskWDFW82F"
)

GRAPH_BASE_OAUTH = "https://api.x.com/graphql/"
GRAPH_BASE_COOKIE = "https://x.com/i/api/graphql/"
REST_BASE = "https://x.com/i/api/1.1/"

RL_REMAINING = "x-rate-limit-remaining"
RL_RESET = "x-rate-limit-reset"
RL_LIMIT = "x-rate-limit-limit"


# ── OAuth 1.0a signing ───────────────────────────────────────────────────────

def _percent_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def _oauth1_header(url: str, oauth_token: str, oauth_token_secret: str) -> str:
    """Generate an OAuth 1.0a Authorization header (HMAC-SHA1)."""
    timestamp = str(int(math.floor(time.time())))
    nonce = "0"

    params = {
        "oauth_consumer_key": CONSUMER_KEY,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": oauth_token,
        "oauth_version": "1.0",
    }

    # Signature base string
    encoded_url = url.replace(",", "%2C").replace("+", "%20")
    param_str = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(params.items())
    )
    base = f"GET&{_percent_encode(encoded_url)}&{_percent_encode(param_str)}"
    signing_key = f"{_percent_encode(CONSUMER_SECRET)}&{_percent_encode(oauth_token_secret)}"

    sig = hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    import base64
    params["oauth_signature"] = _percent_encode(base64.b64encode(sig).decode())

    header = "OAuth " + ", ".join(
        f'{k}="{v}"' for k, v in sorted(params.items())
    )
    return header


# ── Header generation ────────────────────────────────────────────────────────

def _build_headers(session: Session, url: str) -> dict[str, str]:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "connection": "keep-alive",
        "content-type": "application/json",
        "origin": "https://x.com",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
    }

    if session.kind == SessionKind.oauth:
        headers["authorization"] = f"Bearer {BEARER_TOKEN}"
        headers["authorization"] = _oauth1_header(url, session.oauth_token, session.oauth_secret)
    else:
        headers["authorization"] = f"Bearer {BEARER_TOKEN}"
        headers["x-twitter-auth-type"] = "OAuth2Session"
        headers["x-csrf-token"] = session.ct0
        headers["cookie"] = f"auth_token={session.auth_token}; ct0={session.ct0}"
        headers["sec-fetch-dest"] = "empty"
        headers["sec-fetch-mode"] = "cors"
        headers["sec-fetch-site"] = "same-site"

    return headers


# ── URL builder ──────────────────────────────────────────────────────────────

def build_url(endpoint: str, params: dict[str, str], session: Session) -> str:
    """Build the full request URL depending on session kind."""
    if endpoint.startswith("1.1/"):
        base = REST_BASE + endpoint[4:]
    elif session.kind == SessionKind.oauth:
        base = GRAPH_BASE_OAUTH + endpoint
    else:
        base = GRAPH_BASE_COOKIE + endpoint

    if params:
        base += "?" + urllib.parse.urlencode(params)
    return base


# ── Core fetch ───────────────────────────────────────────────────────────────

class TwitterHTTP:
    """Low-level HTTP client with session management and retry logic."""

    def __init__(
        self,
        pool: SessionPool,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        self.pool = pool
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def fetch(self, endpoint: str, params: dict[str, str]) -> Any:
        """
        Fetch a Twitter API endpoint, returning parsed JSON.
        Retries up to max_retries times on rate limit errors.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            session = self.pool.get(endpoint)
            url = build_url(endpoint, params, session)
            headers = _build_headers(session, url)

            try:
                resp = self._client.get(url, headers=headers)

                # Update rate limit state from response headers
                if RL_REMAINING in resp.headers:
                    session.set_rate_limit(
                        endpoint,
                        remaining=int(resp.headers[RL_REMAINING]),
                        reset=int(resp.headers[RL_RESET]),
                        limit=int(resp.headers[RL_LIMIT]),
                    )

                if resp.status_code == 429:
                    session.mark_limited(endpoint)
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    continue

                if resp.status_code == 401:
                    self.pool.invalidate(session)
                    raise PermissionError("Session invalidated (401 Unauthorized)")

                resp.raise_for_status()
                data = resp.json()

                # Twitter embeds errors in 200 responses too
                if "errors" in data and not _has_useful_data(data):
                    codes = [e.get("code") for e in data["errors"]]
                    raise TwitterError(f"Twitter API errors: {data['errors']}", codes=codes)

                return data

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                print(f"[http] network error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
            finally:
                self.pool.release(session)

        raise RuntimeError(
            f"All {self.max_retries} attempts failed for {endpoint}"
        ) from last_error

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TwitterHTTP":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def _has_useful_data(data: dict) -> bool:
    """Check if a response with errors still has usable data."""
    return bool(data.get("data"))


class TwitterError(Exception):
    def __init__(self, message: str, codes: list[int] | None = None) -> None:
        super().__init__(message)
        self.codes = codes or []
