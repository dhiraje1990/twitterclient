"""
Session pool — loads sessions.jsonl exactly as Nitter does (auth.nim, parser/session.nim).

Each line in sessions.jsonl is one JSON object. Two kinds are supported:

OAuth (default when "kind" is missing or "oauth"):
    {"oauth_token": "12345-abc...", "oauth_token_secret": "xyz...", "username": "alice"}

Cookie:
    {"kind": "cookie", "id": "12345", "username": "alice",
     "auth_token": "abc...", "ct0": "xyz..."}
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SessionKind(str, Enum):
    oauth = "oauth"
    cookie = "cookie"


@dataclass
class RateLimit:
    limit: int = 0
    remaining: int = 0
    reset: int = 0          # unix timestamp


@dataclass
class Session:
    kind: SessionKind
    id: int
    username: str

    # OAuth fields
    oauth_token: str = ""
    oauth_secret: str = ""

    # Cookie fields
    auth_token: str = ""
    ct0: str = ""

    # Runtime state
    pending: int = 0
    limited: bool = False
    limited_at: int = 0
    apis: dict[str, RateLimit] = field(default_factory=dict)

    _HOUR = 3600

    def pretty(self) -> str:
        name = f"{self.id} ({self.username})" if self.username else str(self.id)
        return f"{self.kind.value} {name}"

    def is_limited_for(self, endpoint: str) -> bool:
        if self.limited:
            if (int(time.time()) - self.limited_at) > self._HOUR:
                self.limited = False
            else:
                return True
        rl = self.apis.get(endpoint)
        if rl and rl.remaining <= 10 and rl.reset > int(time.time()):
            return True
        return False

    def is_ready(self, endpoint: str, max_concurrent: int = 2) -> bool:
        return self.pending < max_concurrent and not self.is_limited_for(endpoint)

    def set_rate_limit(self, endpoint: str, remaining: int, reset: int, limit: int) -> None:
        existing = self.apis.get(endpoint)
        if existing:
            if existing.reset >= reset and existing.remaining < remaining:
                return
            if existing.reset == reset and existing.remaining >= remaining:
                self.apis[endpoint].remaining = remaining
                return
        self.apis[endpoint] = RateLimit(limit=limit, remaining=remaining, reset=reset)

    def mark_limited(self, endpoint: str) -> None:
        self.limited = True
        self.limited_at = int(time.time())
        rl = self.apis.get(endpoint)
        remaining = rl.remaining if rl else "?"
        print(f"[sessions] rate limited by api: {endpoint}, reqs left: {remaining}, {self.pretty()}")


def _parse_session(raw: str) -> Optional[Session]:
    """Parse one JSONL line into a Session, mirroring Nitter's parseSession()."""
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None

    kind_str = data.get("kind", "oauth")

    if kind_str == "oauth":
        oauth_token = data.get("oauth_token", "")
        if not oauth_token:
            return None
        # The user ID is the numeric prefix before the first '-'
        user_id = int(oauth_token.split("-")[0])
        return Session(
            kind=SessionKind.oauth,
            id=user_id,
            username=data.get("username", ""),
            oauth_token=oauth_token,
            oauth_secret=data.get("oauth_token_secret", ""),
        )

    if kind_str == "cookie":
        raw_id = data.get("id", "0")
        return Session(
            kind=SessionKind.cookie,
            id=int(raw_id) if raw_id else 0,
            username=data.get("username", ""),
            auth_token=data.get("auth_token", ""),
            ct0=data.get("ct0", ""),
        )

    raise ValueError(f"Unknown session kind: {kind_str}")


class SessionPool:
    """Thread-unsafe session pool (mirrors Nitter's sessionPool seq)."""

    def __init__(self, sessions_path: str | Path, max_concurrent: int = 2) -> None:
        self.max_concurrent = max_concurrent
        self._pool: list[Session] = []
        self._load(Path(sessions_path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Sessions file not found: {path}\n"
                "Create a sessions.jsonl file with one session JSON object per line."
            )
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            session = _parse_session(line)
            if session:
                self._pool.append(session)
        print(f"[sessions] loaded {len(self._pool)} sessions from {path}")

    def get(self, endpoint: str) -> Session:
        """Pick a random ready session, mirroring Nitter's getSession()."""
        if not self._pool:
            raise RuntimeError("Session pool is empty.")

        candidates = [s for s in self._pool if s.is_ready(endpoint, self.max_concurrent)]
        if not candidates:
            raise RuntimeError(
                f"No sessions available for endpoint: {endpoint}\n"
                "All sessions may be rate-limited or busy."
            )

        session = random.choice(candidates)
        session.pending += 1
        return session

    def release(self, session: Session) -> None:
        session.pending = max(0, session.pending - 1)

    def invalidate(self, session: Session) -> None:
        print(f"[sessions] invalidating: {session.pretty()}")
        try:
            self._pool.remove(session)
        except ValueError:
            pass

    def __len__(self) -> int:
        return len(self._pool)
