# twitterclient

Fetch tweets as typed Python dataclass objects. Authenticates using the same `sessions.jsonl` format as [Nitter](https://github.com/zedeus/nitter) — no official API key needed, no PyPI.

## Install

```bash
pip install git+https://github.com/dhiraje1990/twitterclient.git
```

Pin to a tag or commit:

```bash
pip install git+https://github.com/you/twitterclient.git@v0.1.0
pip install git+https://github.com/you/twitterclient.git@abc1234
```

Only one dependency: [`httpx`](https://www.python-httpx.org/).

---

## Sessions file

Create a `sessions.jsonl` with one Twitter account per line.

**OAuth** (recommended):
```json
{"oauth_token": "12345-abcdef", "oauth_token_secret": "your_secret", "username": "alice"}
```

**Cookie-based**:
```json
{"kind": "cookie", "id": "12345", "username": "alice", "auth_token": "your_token", "ct0": "your_csrf"}
```

Mix both types freely. The client load-balances across all sessions and backs off rate-limited ones automatically.

---

## CLI

```bash
# Fetch a single tweet
twitterclient tweet 1234567890

# Look up a user
twitterclient user python

# Timeline
twitterclient timeline python
twitterclient timeline python --limit 50 --replies

# Search
twitterclient search "python programming"
twitterclient search "climate -filter:retweets" --limit 50 --product Top

# Twitter list
twitterclient list 56789012
twitterclient list 56789012 --info        # show list metadata

# JSON output (pipe-friendly)
twitterclient --json tweet 1234567890 | jq .text
twitterclient --json timeline python | jq '[.[] | {id, text, likes: .stats.likes}]'

# Custom sessions file
twitterclient --sessions /path/to/sessions.jsonl timeline python
```

Run without installing:
```bash
python -m twitterclient tweet 1234567890
```

---

## Python API

```python
from twitterclient import TwitterClient

with TwitterClient("sessions.jsonl") as client:

    # Single tweet
    tweet = client.get_tweet("1234567890")
    print(tweet.text)
    print(tweet.stats.likes, tweet.stats.retweets, tweet.stats.views)
    print(tweet.url)                        # https://x.com/user/status/id

    # User
    user = client.get_user("python")
    print(user.fullname, user.followers, user.verified_type)

    # Timeline — one page
    tl = client.get_timeline("python", count=20)
    for tweet in tl.tweets:
        print(tweet.time, tweet.text[:80])
    page2 = client.get_timeline("python", cursor=tl.next_cursor)

    # Timeline — auto-paginate
    for tweet in client.iter_timeline("python", max_tweets=100):
        print(tweet.id, tweet.text[:60])

    # Search
    for tweet in client.iter_search("machine learning", max_tweets=200):
        process(tweet)

    # Twitter list
    tl = client.get_list_timeline("56789012")
    for tweet in tl.tweets:
        print(tweet.text)
```

---

## Data model

```python
@dataclass
class Tweet:
    id: int
    user: User
    text: str
    time: datetime
    stats: TweetStats        # .replies .retweets .likes .views
    media: list[Media]
    poll: Optional[Poll]
    retweet: Optional[Tweet]
    quote: Optional[Tweet]
    reply_to: list[str]      # @handles this is replying to
    pinned: bool
    available: bool
    url: str                 # property

    def photos() -> list[Photo]
    def videos() -> list[Video]
    def gifs()   -> list[Gif]

@dataclass
class Video:
    variants: list[VideoVariant]
    def best_variant() -> Optional[VideoVariant]   # highest-bitrate MP4

@dataclass
class Poll:
    options: list[str]
    values:  list[int]
    votes:   int
    leader:  int    # index of winning option
    status:  str    # "2h remaining" or "Final results"

@dataclass
class Timeline:
    tweets:          list[Tweet]
    next_cursor:     str   # pass to next call to paginate
    previous_cursor: str
```

---

## Tests

```bash
git clone https://github.com/you/twitterclient.git
cd twitterclient
pip install -e ".[dev]"
pytest
```

All tests run without network access.
