"""
Unit tests for the parser and session loader.
Uses static JSON fixtures — no network calls.
"""
import json
from datetime import datetime, timezone

import pytest

from twitterclient.models import MediaKind, VerifiedType
from twitterclient.parser import (
    parse_graph_tweet,
    parse_graph_user,
    parse_search,
    parse_timeline,
    parse_single_tweet,
)
from twitterclient.sessions import SessionPool, _parse_session


# ── Session parsing ───────────────────────────────────────────────────────────

class TestSessionParsing:
    def test_oauth_session(self):
        raw = json.dumps({
            "oauth_token": "12345-abcdefgh",
            "oauth_token_secret": "secretxyz",
            "username": "alice",
        })
        s = _parse_session(raw)
        assert s is not None
        assert s.kind.value == "oauth"
        assert s.id == 12345
        assert s.username == "alice"
        assert s.oauth_token == "12345-abcdefgh"
        assert s.oauth_secret == "secretxyz"

    def test_cookie_session(self):
        raw = json.dumps({
            "kind": "cookie",
            "id": "99999",
            "username": "bob",
            "auth_token": "tok123",
            "ct0": "csrf456",
        })
        s = _parse_session(raw)
        assert s is not None
        assert s.kind.value == "cookie"
        assert s.id == 99999
        assert s.auth_token == "tok123"
        assert s.ct0 == "csrf456"

    def test_invalid_json_returns_none(self):
        assert _parse_session("not json{{") is None

    def test_unknown_kind_raises(self):
        raw = json.dumps({"kind": "magic"})
        with pytest.raises(ValueError, match="Unknown session kind"):
            _parse_session(raw)


# ── User parsing ──────────────────────────────────────────────────────────────

USER_LEGACY = {
    "id_str": "1234",
    "screen_name": "testuser",
    "name": "Test User",
    "location": "Earth",
    "description": "Just a test account",
    "profile_image_url_https": "https://pbs.twimg.com/profile_images/1/photo_normal.jpg",
    "profile_banner_url": "https://pbs.twimg.com/profile_banners/1/banner.jpg",
    "friends_count": 100,
    "followers_count": 500,
    "statuses_count": 1234,
    "favourites_count": 9999,
    "media_count": 42,
    "is_blue_verified": True,
    "created_at": "Mon Jan 01 00:00:00 +0000 2020",
}

USER_GRAPH = {
    "rest_id": "1234",
    "legacy": USER_LEGACY,
}


class TestUserParsing:
    def test_basic_user(self):
        user = parse_graph_user(USER_GRAPH)
        assert user is not None
        assert user.id == "1234"
        assert user.username == "testuser"
        assert user.fullname == "Test User"
        assert user.followers == 500
        assert user.verified_type == VerifiedType.blue
        assert user.profile_pic.endswith("photo.jpg")  # _normal stripped
        assert user.join_date == datetime(2020, 1, 1, tzinfo=timezone.utc)

    def test_missing_user_returns_none(self):
        assert parse_graph_user({}) is None
        assert parse_graph_user(None) is None


# ── Tweet parsing ─────────────────────────────────────────────────────────────

def _make_tweet_js(
    rest_id="999",
    text="Hello world",
    created_at="Mon Jan 01 12:00:00 +0000 2024",
    **kwargs,
) -> dict:
    return {
        "rest_id": rest_id,
        "__typename": "Tweet",
        "legacy": {
            "id_str": rest_id,
            "full_text": text,
            "created_at": created_at,
            "reply_count": 1,
            "retweet_count": 2,
            "favorite_count": 10,
            **kwargs,
        },
        "core": {"user_results": {"result": USER_GRAPH}},
        "views": {"count": "42"},
    }


class TestTweetParsing:
    def test_basic_tweet(self):
        js = _make_tweet_js()
        tweet = parse_graph_tweet(js)
        assert tweet is not None
        assert tweet.id == 999
        assert tweet.text == "Hello world"
        assert tweet.stats.likes == 10
        assert tweet.stats.retweets == 2
        assert tweet.stats.views == 42
        assert tweet.user.username == "testuser"
        assert tweet.time == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert tweet.url == "https://x.com/testuser/status/999"

    def test_ad_is_skipped(self):
        js = _make_tweet_js()
        js["content_disclosure"] = {
            "advertising_disclosure": {"is_paid_promotion": True}
        }
        assert parse_graph_tweet(js) is None

    def test_unavailable_tweet(self):
        js = {"__typename": "TweetUnavailable"}
        assert parse_graph_tweet(js) is None

    def test_tombstone(self):
        js = {"__typename": "TweetTombstone"}
        assert parse_graph_tweet(js) is None

    def test_with_visibility_wrapper(self):
        inner = _make_tweet_js(rest_id="777", text="Wrapped tweet")
        js = {"__typename": "TweetWithVisibilityResults", "tweet": inner}
        tweet = parse_graph_tweet(js)
        assert tweet is not None
        assert tweet.id == 777

    def test_photo_media(self):
        js = _make_tweet_js()
        js["legacy"]["extended_entities"] = {
            "media": [{
                "type": "photo",
                "media_url_https": "https://pbs.twimg.com/media/photo.jpg",
                "ext_alt_text": "A photo",
            }]
        }
        tweet = parse_graph_tweet(js)
        assert len(tweet.media) == 1
        assert tweet.media[0].kind == MediaKind.photo
        assert tweet.media[0].photo.alt_text == "A photo"
        assert len(tweet.photos()) == 1

    def test_video_media(self):
        js = _make_tweet_js()
        js["legacy"]["extended_entities"] = {
            "media": [{
                "type": "video",
                "media_url_https": "https://pbs.twimg.com/thumb.jpg",
                "video_info": {
                    "duration_millis": 15000,
                    "variants": [
                        {"content_type": "video/mp4", "url": "https://video.twimg.com/vid.mp4", "bit_rate": 2176000},
                        {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/vid.m3u8", "bit_rate": 0},
                    ],
                },
                "ext_media_availability": {"status": "Available"},
            }]
        }
        tweet = parse_graph_tweet(js)
        assert len(tweet.videos()) == 1
        video = tweet.videos()[0]
        assert video.duration_ms == 15000
        assert video.available is True
        best = video.best_variant()
        assert best is not None
        assert best.bitrate == 2176000

    def test_reply_info(self):
        js = _make_tweet_js(in_reply_to_screen_name="someone")
        tweet = parse_graph_tweet(js)
        assert "someone" in tweet.reply_to

    def test_quote_tweet(self):
        quoted = _make_tweet_js(rest_id="111", text="Original tweet")
        outer = _make_tweet_js(rest_id="222", text="My quote")
        outer["quoted_status_result"] = {"result": quoted}
        tweet = parse_graph_tweet(outer)
        assert tweet.quote is not None
        assert tweet.quote.id == 111
        assert tweet.quote.text == "Original tweet"

    def test_poll(self):
        js = _make_tweet_js()
        js["card"] = {
            "legacy": {
                "name": "poll2choice_text_only",
                "binding_values": [
                    {"key": "choice1_label", "value": {"string_value": "Yes"}},
                    {"key": "choice1_count", "value": {"string_value": "80"}},
                    {"key": "choice2_label", "value": {"string_value": "No"}},
                    {"key": "choice2_count", "value": {"string_value": "20"}},
                    {"key": "end_datetime_utc", "value": {"string_value": ""}},
                ],
            }
        }
        tweet = parse_graph_tweet(js)
        assert tweet.poll is not None
        assert tweet.poll.options == ["Yes", "No"]
        assert tweet.poll.votes == 100
        assert tweet.poll.leader == 0


# ── Timeline parsing ──────────────────────────────────────────────────────────

def _make_timeline_response(tweets: list[dict], next_cursor: str = "") -> dict:
    entries = []
    for i, t in enumerate(tweets):
        entries.append({
            "entryId": f"tweet-{t['rest_id']}",
            "content": {
                "itemContent": {
                    "tweet_results": {"result": t}
                }
            }
        })
    if next_cursor:
        entries.append({
            "entryId": "cursor-bottom-1",
            "content": {"value": next_cursor}
        })
    return {
        "data": {
            "user": {
                "result": {
                    "timeline": {
                        "timeline": {
                            "instructions": [{
                                "type": "TimelineAddEntries",
                                "entries": entries,
                            }]
                        }
                    }
                }
            }
        }
    }


class TestTimelineParsing:
    def test_parses_tweets(self):
        tweets_js = [_make_tweet_js(rest_id=str(i), text=f"Tweet {i}") for i in range(3)]
        js = _make_timeline_response(tweets_js)
        tl = parse_timeline(js)
        assert len(tl.tweets) == 3
        assert tl.tweets[0].text == "Tweet 0"

    def test_cursor_extracted(self):
        tweets_js = [_make_tweet_js(rest_id="1")]
        js = _make_timeline_response(tweets_js, next_cursor="abc123")
        tl = parse_timeline(js)
        assert tl.next_cursor == "abc123"

    def test_empty_timeline(self):
        js = _make_timeline_response([])
        tl = parse_timeline(js)
        assert tl.tweets == []
        assert tl.next_cursor == ""
