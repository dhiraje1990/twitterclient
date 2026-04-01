"""
Dataclass models mirroring Nitter's type system (types.nim).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VerifiedType(str, Enum):
    none = "None"
    blue = "Blue"
    business = "Business"
    government = "Government"


class VideoType(str, Enum):
    m3u8 = "application/x-mpegURL"
    mp4 = "video/mp4"
    vmap = "video/vmap"


class MediaKind(str, Enum):
    photo = "photo"
    video = "video"
    gif = "gif"


@dataclass
class User:
    id: str
    username: str
    fullname: str
    location: str = ""
    website: str = ""
    bio: str = ""
    profile_pic: str = ""
    banner: str = ""
    following: int = 0
    followers: int = 0
    tweet_count: int = 0
    likes: int = 0
    media_count: int = 0
    verified_type: VerifiedType = VerifiedType.none
    protected: bool = False
    suspended: bool = False
    join_date: Optional[datetime] = None


@dataclass
class VideoVariant:
    url: str
    content_type: VideoType = VideoType.mp4
    bitrate: int = 0


@dataclass
class Video:
    url: str
    thumb: str = ""
    duration_ms: int = 0
    available: bool = True
    reason: str = ""
    title: str = ""
    description: str = ""
    variants: list[VideoVariant] = field(default_factory=list)

    def best_variant(self) -> Optional[VideoVariant]:
        """Return the highest-bitrate MP4 variant."""
        mp4s = [v for v in self.variants if v.content_type == VideoType.mp4]
        return max(mp4s, key=lambda v: v.bitrate, default=None)


@dataclass
class Photo:
    url: str
    alt_text: str = ""


@dataclass
class Gif:
    url: str
    thumb: str = ""
    alt_text: str = ""


@dataclass
class Media:
    kind: MediaKind
    photo: Optional[Photo] = None
    video: Optional[Video] = None
    gif: Optional[Gif] = None


@dataclass
class Poll:
    options: list[str] = field(default_factory=list)
    values: list[int] = field(default_factory=list)
    votes: int = 0
    leader: int = 0          # index of the winning option
    status: str = ""          # time remaining or "Final results"


@dataclass
class TweetStats:
    replies: int = 0
    retweets: int = 0
    likes: int = 0
    views: int = 0


@dataclass
class Tweet:
    id: int
    user: User
    text: str
    time: datetime
    stats: TweetStats = field(default_factory=TweetStats)
    media: list[Media] = field(default_factory=list)
    poll: Optional[Poll] = None
    retweet: Optional[Tweet] = None
    quote: Optional[Tweet] = None
    reply_to: list[str] = field(default_factory=list)   # list of @handles
    thread_id: int = 0
    pinned: bool = False
    available: bool = True
    tombstone: str = ""
    is_ad: bool = False
    note: str = ""            # long-form note tweet body

    @property
    def url(self) -> str:
        return f"https://x.com/{self.user.username}/status/{self.id}"

    def photos(self) -> list[Photo]:
        return [m.photo for m in self.media if m.kind == MediaKind.photo and m.photo]

    def videos(self) -> list[Video]:
        return [m.video for m in self.media if m.kind == MediaKind.video and m.video]

    def gifs(self) -> list[Gif]:
        return [m.gif for m in self.media if m.kind == MediaKind.gif and m.gif]


@dataclass
class Timeline:
    tweets: list[Tweet]
    next_cursor: str = ""
    previous_cursor: str = ""


@dataclass
class TwitterList:
    id: str
    name: str
    username: str
    user_id: str
    description: str = ""
    members: int = 0
    banner: str = ""
