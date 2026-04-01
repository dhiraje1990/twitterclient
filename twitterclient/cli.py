"""
CLI for twitterclient.

Install from GitHub:
    pip install git+https://github.com/you/twitterclient.git

Then use:
    twitterclient tweet 1234567890
    twitterclient timeline python
    twitterclient search "python programming"
    twitterclient list 56789012

Or run as a module:
    python -m twitterclient tweet 1234567890
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import TwitterClient
from .models import MediaKind, Tweet, User, Timeline, TwitterList


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_user(user: User) -> str:
    verified = f" [{user.verified_type.value}]" if user.verified_type.value != "None" else ""
    return (
        f"{user.fullname}{verified} @{user.username}\n"
        f"  {user.bio}\n"
        f"  📍 {user.location}  🔗 {user.website}\n"
        f"  Followers: {_fmt_number(user.followers)}  "
        f"Following: {_fmt_number(user.following)}  "
        f"Tweets: {_fmt_number(user.tweet_count)}\n"
        f"  Joined: {user.join_date.strftime('%b %Y') if user.join_date else 'unknown'}"
    )


def _fmt_tweet(tweet: Tweet, indent: str = "") -> str:
    lines = []
    time_str = tweet.time.strftime("%Y-%m-%d %H:%M") if tweet.time else ""
    lines.append(
        f"{indent}@{tweet.user.username} · {time_str}"
        + (" 📌" if tweet.pinned else "")
    )

    if tweet.retweet:
        lines.append(f"{indent}  🔁 RT @{tweet.retweet.user.username}: {tweet.retweet.text[:120]}")
    else:
        for line in tweet.text.splitlines():
            lines.append(f"{indent}  {line}")

    if tweet.media:
        kinds = []
        if tweet.photos():
            kinds.append(f"🖼  {len(tweet.photos())} photo(s)")
        if tweet.videos():
            kinds.append(f"🎥 {len(tweet.videos())} video(s)")
        if tweet.gifs():
            kinds.append(f"🎞  {len(tweet.gifs())} GIF(s)")
        lines.append(f"{indent}  {' · '.join(kinds)}")

    if tweet.poll:
        p = tweet.poll
        for i, (opt, val) in enumerate(zip(p.options, p.values)):
            bar = "█" * int(20 * val / max(p.votes, 1))
            winner = " ◀" if i == p.leader else ""
            lines.append(f"{indent}  {opt}: {bar} {val}{winner}")
        lines.append(f"{indent}  {p.votes} votes · {p.status}")

    if tweet.quote:
        lines.append(f"{indent}  ┌ @{tweet.quote.user.username}: {tweet.quote.text[:100]}")

    stats = tweet.stats
    lines.append(
        f"{indent}  💬 {_fmt_number(stats.replies)}  "
        f"🔁 {_fmt_number(stats.retweets)}  "
        f"❤️  {_fmt_number(stats.likes)}  "
        f"👁  {_fmt_number(stats.views)}  "
        f"🔗 {tweet.url}"
    )
    return "\n".join(lines)


def _fmt_list(tl: TwitterList) -> str:
    return (
        f"{tl.name} (ID: {tl.id})\n"
        f"  @{tl.username} · {_fmt_number(tl.members)} members\n"
        f"  {tl.description}"
    )


def _output_json(obj) -> None:
    """Print an object as JSON. Handles dataclasses recursively."""
    import dataclasses
    from datetime import datetime

    def default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "value"):   # enums
            return o.value
        raise TypeError(type(o))

    print(json.dumps(obj if isinstance(obj, (list, dict)) else
                     __import__("dataclasses").asdict(obj),
                     default=default, indent=2))


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_tweet(client: TwitterClient, args: argparse.Namespace) -> int:
    tweet = client.get_tweet(args.id)
    if not tweet:
        print(f"Tweet {args.id} not found or unavailable.", file=sys.stderr)
        return 1
    if args.json:
        _output_json(tweet)
    else:
        print(_fmt_tweet(tweet))
    return 0


def cmd_user(client: TwitterClient, args: argparse.Namespace) -> int:
    user = client.get_user(args.username)
    if not user:
        print(f"User @{args.username} not found.", file=sys.stderr)
        return 1
    if args.json:
        _output_json(user)
    else:
        print(_fmt_user(user))
    return 0


def cmd_timeline(client: TwitterClient, args: argparse.Namespace) -> int:
    tweets = list(client.iter_timeline(
        args.username,
        max_tweets=args.limit,
        include_replies=args.replies,
    ))
    if not tweets:
        print(f"No tweets found for @{args.username}.", file=sys.stderr)
        return 1
    if args.json:
        _output_json(tweets)
    else:
        sep = "\n" + "─" * 60 + "\n"
        print(sep.join(_fmt_tweet(t) for t in tweets))
    return 0


def cmd_search(client: TwitterClient, args: argparse.Namespace) -> int:
    tweets = list(client.iter_search(
        args.query,
        max_tweets=args.limit,
        product=args.product,
    ))
    if not tweets:
        print("No results found.", file=sys.stderr)
        return 1
    if args.json:
        _output_json(tweets)
    else:
        sep = "\n" + "─" * 60 + "\n"
        print(sep.join(_fmt_tweet(t) for t in tweets))
    return 0


def cmd_list(client: TwitterClient, args: argparse.Namespace) -> int:
    if args.info:
        lst = client.get_list(args.id)
        if not lst:
            print(f"List {args.id} not found.", file=sys.stderr)
            return 1
        if args.json:
            _output_json(lst)
        else:
            print(_fmt_list(lst))
        return 0

    tweets = list(client.iter_search(  # reuse pagination helper
        args.id, max_tweets=args.limit
    )) if False else list(  # use proper list timeline
        t for t in _iter_list(client, args.id, args.limit)
    )
    if not tweets:
        print(f"No tweets in list {args.id}.", file=sys.stderr)
        return 1
    if args.json:
        _output_json(tweets)
    else:
        sep = "\n" + "─" * 60 + "\n"
        print(sep.join(_fmt_tweet(t) for t in tweets))
    return 0


def _iter_list(client: TwitterClient, list_id: str, max_tweets: int):
    cursor = ""
    collected = 0
    while collected < max_tweets:
        tl = client.get_list_timeline(list_id, cursor=cursor)
        if not tl.tweets:
            break
        for t in tl.tweets:
            if collected >= max_tweets:
                return
            yield t
            collected += 1
        if not tl.next_cursor:
            break
        cursor = tl.next_cursor


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twitterclient",
        description="Fetch tweets as text or JSON. Authenticates via sessions.jsonl.",
    )
    parser.add_argument(
        "--sessions", "-s",
        default="sessions.jsonl",
        metavar="FILE",
        help="Path to sessions.jsonl (default: ./sessions.jsonl)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON instead of formatted text",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # tweet
    p_tweet = sub.add_parser("tweet", help="Fetch a single tweet by ID")
    p_tweet.add_argument("id", help="Tweet ID")

    # user
    p_user = sub.add_parser("user", help="Look up a user profile")
    p_user.add_argument("username", help="Twitter handle (@ optional)")

    # timeline
    p_tl = sub.add_parser("timeline", help="Fetch a user's tweet timeline")
    p_tl.add_argument("username", help="Twitter handle (@ optional)")
    p_tl.add_argument("--limit", "-n", type=int, default=20, metavar="N",
                      help="Max tweets to fetch (default: 20)")
    p_tl.add_argument("--replies", "-r", action="store_true",
                      help="Include replies")

    # search
    p_search = sub.add_parser("search", help="Search for tweets")
    p_search.add_argument("query", help='Search query, e.g. "python -filter:retweets"')
    p_search.add_argument("--limit", "-n", type=int, default=20, metavar="N",
                          help="Max results (default: 20)")
    p_search.add_argument("--product", "-p", default="Latest",
                          choices=["Latest", "Top", "Photos", "Videos"],
                          help="Result type (default: Latest)")

    # list
    p_list = sub.add_parser("list", help="Fetch tweets from a Twitter list")
    p_list.add_argument("id", help="List ID (numeric)")
    p_list.add_argument("--limit", "-n", type=int, default=20, metavar="N",
                        help="Max tweets (default: 20)")
    p_list.add_argument("--info", action="store_true",
                        help="Show list metadata instead of tweets")

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    sessions_path = Path(args.sessions)
    if not sessions_path.exists():
        print(
            f"Error: sessions file not found: {sessions_path}\n"
            "Create a sessions.jsonl file — see README for format.",
            file=sys.stderr,
        )
        sys.exit(1)

    dispatch = {
        "tweet":    cmd_tweet,
        "user":     cmd_user,
        "timeline": cmd_timeline,
        "search":   cmd_search,
        "list":     cmd_list,
    }

    try:
        with TwitterClient(sessions_path) as client:
            sys.exit(dispatch[args.command](client, args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
