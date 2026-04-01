"""
JSON parser — mirrors Nitter's parser.nim and parserutils.nim.

Converts raw Twitter GraphQL JSON into Python dataclass objects.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .models import (
    Gif,
    Media,
    MediaKind,
    Photo,
    Poll,
    Tweet,
    TweetStats,
    Timeline,
    TwitterList,
    User,
    VerifiedType,
    Video,
    VideoType,
    VideoVariant,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get(d: Any, *keys: str, default: Any = None) -> Any:
    """Safe nested dict access."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def _parse_time_twitter(s: str) -> Optional[datetime]:
    """Parse Twitter's 'Mon Jan 01 00:00:00 +0000 2024' format."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_time_ms(ms: int | str | None) -> Optional[datetime]:
    """Parse a millisecond unix timestamp."""
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _parse_time_iso(s: str) -> Optional[datetime]:
    """Parse ISO 8601 format like '2024-01-01T00:00:00Z'."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _strip_twimg(url: str) -> str:
    """Nitter strips pbs.twimg.com prefix from image URLs; we keep full URLs."""
    return url


def _get_tweet_id(entry_id: str) -> int:
    """Extract numeric tweet ID from an entryId string like 'tweet-12345'."""
    try:
        start = entry_id.rfind("-")
        return int(entry_id[start + 1:])
    except (ValueError, IndexError):
        return 0


# ── User parsing ─────────────────────────────────────────────────────────────

def _parse_verified_type(legacy: dict) -> VerifiedType:
    if legacy.get("is_blue_verified"):
        return VerifiedType.blue
    vt = legacy.get("verified_type", "")
    if vt:
        try:
            return VerifiedType(vt)
        except ValueError:
            pass
    return VerifiedType.none


def _parse_user_legacy(legacy: dict, rest_id: str = "") -> User:
    """Parse a user from a 'legacy' block — mirrors parseUser()."""
    if not legacy:
        return None

    return User(
        id=rest_id or legacy.get("id_str", ""),
        username=legacy.get("screen_name", ""),
        fullname=legacy.get("name", ""),
        location=legacy.get("location", ""),
        bio=legacy.get("description", ""),
        profile_pic=legacy.get("profile_image_url_https", "").replace("_normal", ""),
        banner=legacy.get("profile_banner_url", ""),
        following=legacy.get("friends_count", 0),
        followers=legacy.get("followers_count", 0),
        tweet_count=legacy.get("statuses_count", 0),
        likes=legacy.get("favourites_count", 0),
        media_count=legacy.get("media_count", 0),
        verified_type=_parse_verified_type(legacy),
        protected=legacy.get("protected", False),
        join_date=_parse_time_twitter(legacy.get("created_at", "")),
    )


def parse_graph_user(js: dict) -> Optional[User]:
    """Parse a user from GraphQL result — mirrors parseGraphUser()."""
    if not js:
        return None

    # Try various paths Twitter uses
    user = (
        _get(js, "user_result", "result")
        or _get(js, "user_results", "result")
        or js
    )

    if not isinstance(user, dict):
        return None

    legacy = user.get("legacy", {})
    rest_id = user.get("rest_id", "")
    result = _parse_user_legacy(legacy, rest_id)

    if result and not result.verified_type != VerifiedType.none:
        if user.get("is_blue_verified"):
            result.verified_type = VerifiedType.blue

    # Fallback for newer API shapes
    if result and not result.username:
        core = user.get("core", {})
        result.username = core.get("screen_name", "")
        result.fullname = core.get("name", "")
        avatar = _get(user, "avatar", "image_url", default="")
        result.profile_pic = avatar.replace("_normal", "")

    return result


# ── Media parsing ─────────────────────────────────────────────────────────────

def _parse_video_variants(variants: list[dict]) -> list[VideoVariant]:
    result = []
    for v in variants:
        url = v.get("url", "")
        ct_str = v.get("content_type", "video/mp4")
        try:
            ct = VideoType(ct_str)
        except ValueError:
            ct = VideoType.mp4
        result.append(VideoVariant(
            url=url,
            content_type=ct,
            bitrate=v.get("bit_rate", v.get("bitrate", 0)),
        ))
    return result


def _parse_media_entities(legacy: dict) -> list[Media]:
    """Parse extended_entities media — mirrors parseLegacyMediaEntities()."""
    result = []
    for m in _get(legacy, "extended_entities", "media", default=[]):
        kind = m.get("type", "photo")
        if kind == "photo":
            result.append(Media(
                kind=MediaKind.photo,
                photo=Photo(
                    url=m.get("media_url_https", ""),
                    alt_text=m.get("ext_alt_text", "") or "",
                ),
            ))
        elif kind == "video":
            variants = _parse_video_variants(_get(m, "video_info", "variants", default=[]))
            result.append(Media(
                kind=MediaKind.video,
                video=Video(
                    url=m.get("media_url_https", ""),
                    thumb=m.get("media_url_https", ""),
                    duration_ms=_get(m, "video_info", "duration_millis", default=0),
                    available=_get(m, "ext_media_availability", "status", default="Available").lower() == "available",
                    title=m.get("ext_alt_text", "") or "",
                    variants=variants,
                ),
            ))
        elif kind == "animated_gif":
            gif_variants = _get(m, "video_info", "variants", default=[])
            gif_url = gif_variants[0].get("url", "") if gif_variants else ""
            result.append(Media(
                kind=MediaKind.gif,
                gif=Gif(
                    url=gif_url,
                    thumb=m.get("media_url_https", ""),
                    alt_text=m.get("ext_alt_text", "") or "",
                ),
            ))
    return result


def _parse_poll(card_name: str, binding_values: dict) -> Optional[Poll]:
    """Parse a poll card — mirrors parsePoll()."""
    if "poll" not in card_name:
        return None
    try:
        num_choices = int(card_name[4])
    except (ValueError, IndexError):
        return None

    options, values = [], []
    for i in range(1, num_choices + 1):
        label = _get(binding_values, f"choice{i}_label", "string_value", default="")
        count_str = _get(binding_values, f"choice{i}_count", "string_value", default="0")
        options.append(label)
        values.append(int(count_str) if count_str.isdigit() else 0)

    end_str = _get(binding_values, "end_datetime_utc", "string_value", default="")
    end_time = _parse_time_iso(end_str)
    now = datetime.now(tz=timezone.utc)
    if end_time and end_time > now:
        diff = end_time - now
        total_seconds = int(diff.total_seconds())
        hours, rem = divmod(total_seconds, 3600)
        minutes = rem // 60
        status = f"{hours}h {minutes}m remaining"
    else:
        status = "Final results"

    leader = values.index(max(values)) if values else 0
    return Poll(
        options=options,
        values=values,
        votes=sum(values),
        leader=leader,
        status=status,
    )


def _clean_text(text: str, legacy: dict) -> str:
    """Remove trailing t.co media URLs from tweet text."""
    for m in _get(legacy, "entities", "media", default=[]):
        url = m.get("url", "")
        if url and text.endswith(url):
            text = text[: -len(url)].rstrip()
    return text


# ── Tweet parsing ─────────────────────────────────────────────────────────────

def _parse_tweet_stats(legacy: dict, views: dict) -> TweetStats:
    return TweetStats(
        replies=legacy.get("reply_count", 0),
        retweets=legacy.get("retweet_count", 0),
        likes=legacy.get("favorite_count", 0),
        views=int(views.get("count", "0") or "0") if isinstance(views, dict) else 0,
    )


def parse_graph_tweet(js: dict) -> Optional[Tweet]:
    """
    Parse a tweet from a GraphQL result node — mirrors parseGraphTweet().
    Returns None for ads, unavailable tweets, and tombstones.
    """
    if not js or not isinstance(js, dict):
        return None

    typename = js.get("__typename", js.get("type", ""))

    if typename == "TweetUnavailable":
        return None
    if typename == "TweetTombstone":
        return None
    if typename == "TweetWithVisibilityResults":
        return parse_graph_tweet(js.get("tweet", {}))

    # Must have at minimum a rest_id
    rest_id = js.get("rest_id", "")
    if not rest_id and "legacy" not in js:
        return None

    legacy = js.get("legacy", {})
    if not legacy:
        return None

    # Skip ads
    is_ad = _get(js, "content_disclosure", "advertising_disclosure", "is_paid_promotion", default=False)
    if is_ad:
        return None

    # Parse core fields
    text = legacy.get("full_text", legacy.get("text", ""))
    text = _clean_text(text, legacy)

    created_at = legacy.get("created_at", "")
    tweet_time = _parse_time_twitter(created_at)

    stats = _parse_tweet_stats(legacy, js.get("views", {}))
    media = _parse_media_entities(legacy)

    # Reply info
    reply_to = []
    in_reply_to = legacy.get("in_reply_to_screen_name", "")
    if in_reply_to:
        reply_to.append(in_reply_to)

    # Poll
    poll: Optional[Poll] = None
    card_js = js.get("card") or js.get("tweet_card") or {}
    card_legacy = card_js.get("legacy", {}) if card_js else {}
    if card_legacy:
        card_name = card_legacy.get("name", "")
        bv_raw = card_legacy.get("binding_values", [])
        # binding_values can be an array of {key, value} or a dict
        if isinstance(bv_raw, list):
            bv = {item["key"]: item["value"] for item in bv_raw if "key" in item}
        else:
            bv = bv_raw
        if "poll" in card_name:
            poll = _parse_poll(card_name, bv)

    # Retweet
    retweet: Optional[Tweet] = None
    rt_status = legacy.get("retweeted_status_result", {})
    if rt_status and rt_status.get("result"):
        retweet = parse_graph_tweet(rt_status["result"])

    # Quote tweet
    quote: Optional[Tweet] = None
    for quote_key in ("quoted_status_result", "quotedPostResults"):
        qr = js.get(quote_key, {})
        if qr and qr.get("result"):
            quote = parse_graph_tweet(qr["result"])
            break

    # User
    user = parse_graph_user(js.get("core", {}))
    if not user:
        return None

    try:
        tweet_id = int(rest_id) if rest_id else int(legacy.get("id_str", 0))
    except ValueError:
        tweet_id = 0

    return Tweet(
        id=tweet_id,
        user=user,
        text=text,
        time=tweet_time,
        stats=stats,
        media=media,
        poll=poll,
        retweet=retweet,
        quote=quote,
        reply_to=reply_to,
        thread_id=int(legacy.get("conversation_id_str", 0) or 0),
        pinned=False,
        available=True,
        is_ad=False,
        note=_get(js, "note_tweet", "note_tweet_results", "result", "text", default=""),
    )


# ── Timeline parsing ──────────────────────────────────────────────────────────

def _extract_tweets_from_entry(entry: dict) -> list[Tweet]:
    """mirrors extractTweetsFromEntry()"""
    tweets = []

    # Direct tweet result
    for path in (
        ("content", "itemContent", "tweet_results", "result"),
        ("content", "content", "tweet_results", "result"),
        ("content", "content", "tweetResult", "result"),
    ):
        node = entry
        for k in path:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        if node:
            t = parse_graph_tweet(node)
            if t:
                return [t]

    # Items inside a module entry
    for item in _get(entry, "content", "items", default=[]):
        for path in (
            ("item", "itemContent", "tweet_results", "result"),
            ("item", "content", "tweet_results", "result"),
        ):
            node = item
            for k in path:
                node = node.get(k, {}) if isinstance(node, dict) else {}
            if node:
                t = parse_graph_tweet(node)
                if t:
                    tweets.append(t)

    return tweets


def parse_timeline(js: dict, after: str = "") -> Timeline:
    """
    Parse a GraphQL timeline response into a Timeline object.
    mirrors parseGraphTimeline().
    """
    tweets: list[Tweet] = []
    next_cursor = ""
    prev_cursor = ""

    instructions = (
        _get(js, "data", "user", "result", "timeline", "timeline", "instructions")
        or _get(js, "data", "user_result", "result", "timeline_response", "timeline", "instructions")
        or _get(js, "data", "list", "timeline_response", "timeline", "instructions")
        or []
    )

    for instruction in instructions:
        typename = instruction.get("__typename", instruction.get("type", ""))

        # Module items (e.g. media grid)
        module_items = instruction.get("moduleItems")
        if module_items:
            for item in module_items:
                for path in (
                    ("item", "itemContent", "tweet_results", "result"),
                    ("item", "content", "tweet_results", "result"),
                ):
                    node = item
                    for k in path:
                        node = node.get(k, {}) if isinstance(node, dict) else {}
                    if node:
                        t = parse_graph_tweet(node)
                        if t:
                            tweets.append(t)
            continue

        for entry in instruction.get("entries", []):
            entry_id = entry.get("entryId", entry.get("entry_id", ""))
            if not entry_id:
                continue

            if entry_id.startswith("tweet") or entry_id.startswith("profile-grid"):
                for t in _extract_tweets_from_entry(entry):
                    tweets.append(t)

            elif "cursor-bottom" in entry_id:
                next_cursor = (
                    _get(entry, "content", "value")
                    or _get(entry, "content", "content", "value")
                    or ""
                )
            elif "cursor-top" in entry_id:
                prev_cursor = _get(entry, "content", "value", default="")

    return Timeline(tweets=tweets, next_cursor=next_cursor, previous_cursor=prev_cursor)


def parse_search(js: dict, after: str = "") -> Timeline:
    """
    Parse a search timeline — mirrors parseGraphSearch().
    """
    tweets: list[Tweet] = []
    next_cursor = ""

    instructions = (
        _get(js, "data", "search", "timeline_response", "timeline", "instructions")
        or _get(js, "data", "search_by_raw_query", "search_timeline", "timeline", "instructions")
        or []
    )

    for instruction in instructions:
        typename = instruction.get("__typename", instruction.get("type", ""))
        if typename in ("TimelineAddEntries", ""):
            for entry in instruction.get("entries", []):
                entry_id = entry.get("entryId", "")
                if entry_id.startswith("tweet"):
                    for path in (
                        ("content", "itemContent", "tweet_results", "result"),
                        ("content", "content", "tweet_results", "result"),
                    ):
                        node = entry
                        for k in path:
                            node = node.get(k, {}) if isinstance(node, dict) else {}
                        if node:
                            t = parse_graph_tweet(node)
                            if t:
                                tweets.append(t)
                                break
                elif "cursor-bottom" in entry_id:
                    next_cursor = _get(entry, "content", "value", default="")

        elif typename == "TimelineReplaceEntry":
            replaced = instruction.get("entry_id_to_replace", "")
            if "cursor-bottom" in replaced:
                next_cursor = _get(instruction, "entry", "content", "value", default="")

    return Timeline(tweets=tweets, next_cursor=next_cursor)


def parse_list(js: dict) -> Optional[TwitterList]:
    """Parse a Twitter list from GraphQL — mirrors parseGraphList()."""
    list_data = (
        _get(js, "data", "user_by_screen_name", "list")
        or _get(js, "data", "list")
    )
    if not list_data:
        return None
    return TwitterList(
        id=list_data.get("id_str", ""),
        name=list_data.get("name", ""),
        username=_get(list_data, "user_results", "result", "legacy", "screen_name", default=""),
        user_id=_get(list_data, "user_results", "result", "rest_id", default=""),
        description=list_data.get("description", ""),
        members=list_data.get("member_count", 0),
        banner=_get(list_data, "custom_banner_media", "media_info", "original_img_url", default=""),
    )

def parse_user_result(js: dict) -> Optional[User]:
    node = (
        _get(js, "data", "user", "result")                  # UserByScreenName
        or _get(js, "data", "user_result", "result")
        or _get(js, "data", "user_results", "result")
    )
    if not node:
        return None
    return parse_graph_user(node)

def parse_single_tweet(js: dict) -> Optional[Tweet]:
    """Parse a single tweet from TweetResultByRestId endpoint."""
    # New endpoint shape: data.tweetResult.result
    node = (
        _get(js, "data", "tweetResult", "result")
        or _get(js, "data", "tweet_result", "result")
    )
    if node:
        return parse_graph_tweet(node)
    return None


def parse_conversation_tweet(js: dict, tweet_id: str) -> Optional[Tweet]:
    """
    Parse a single tweet from the ConversationTimeline endpoint.
    Walks instructions looking for the entry matching tweet_id.
    """
    instructions = (
        _get(js, "data", "timelineResponse", "instructions")
        or _get(js, "data", "timeline_response", "instructions")
        or _get(js, "data", "threaded_conversation_with_injections_v2", "instructions")
        or []
    )

    for instruction in instructions:
        for entry in instruction.get("entries", []):
            entry_id = entry.get("entryId", "")
            if not entry_id.endswith(tweet_id):
                continue
            for path in (
                ("content", "itemContent", "tweet_results", "result"),
                ("content", "content", "tweet_results", "result"),
                ("content", "content", "tweetResult", "result"),
            ):
                node = entry
                for k in path:
                    node = node.get(k, {}) if isinstance(node, dict) else {}
                if node:
                    return parse_graph_tweet(node)

    # Fallback: return first parseable tweet in the response
    for instruction in instructions:
        for entry in instruction.get("entries", []):
            if not entry.get("entryId", "").startswith("tweet-"):
                continue
            for path in (
                ("content", "itemContent", "tweet_results", "result"),
                ("content", "content", "tweet_results", "result"),
            ):
                node = entry
                for k in path:
                    node = node.get(k, {}) if isinstance(node, dict) else {}
                if node:
                    t = parse_graph_tweet(node)
                    if t:
                        return t
    return None