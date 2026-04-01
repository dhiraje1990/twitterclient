"""
twitterclient — fetch tweets as typed Python dataclass objects.

Authenticates using the same sessions.jsonl format as Nitter.

Quick start:
    from twitterclient import TwitterClient

    with TwitterClient("sessions.jsonl") as client:
        tweet = client.get_tweet("1234567890")
        print(tweet.text, tweet.stats.likes)

        for t in client.iter_timeline("python", max_tweets=50):
            print(t.time, t.text[:80])
"""
from .client import TwitterClient
from .models import (
    Gif,
    Media,
    MediaKind,
    Photo,
    Poll,
    Timeline,
    Tweet,
    TweetStats,
    TwitterList,
    User,
    VerifiedType,
    Video,
    VideoType,
    VideoVariant,
)

__all__ = [
    "TwitterClient",
    "Tweet",
    "TweetStats",
    "User",
    "Timeline",
    "TwitterList",
    "Media",
    "MediaKind",
    "Photo",
    "Video",
    "VideoVariant",
    "VideoType",
    "Gif",
    "Poll",
    "VerifiedType",
]

__version__ = "0.1.0"
