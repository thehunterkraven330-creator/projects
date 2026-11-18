import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from .catalog import ProductRead


class StoryCreate(BaseModel):
    media_url: str = Field(max_length=500)  # the view_url from /uploads/presigned-url, after the file was uploaded
    media_type: str  # "image" or "video"
    caption: str | None = Field(default=None, max_length=200)
    product_id: uuid.UUID | None = None
    audience: str = "everyone"  # "everyone" or "followers"
    kind: str = "post"  # "post", "live" (event_at = go-live time) or "sale" (event_at = sale end, product_id required)
    event_at: datetime | None = None
    sale_percent: int | None = Field(default=None, ge=1, le=99)  # a flash sale: the discount while it runs


class StoryAuthor(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None


class StoryRead(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    media_url: str
    media_type: str
    caption: str | None = None
    product: ProductRead | None = None
    bought: bool = False  # the author really bought the tagged product on Lumin
    audience: str
    kind: str = "post"
    event_at: datetime | None = None
    created_at: datetime
    expires_at: datetime
    seen: bool = False
    views_count: int | None = None  # only the author is told
    held: bool = False  # only the author is told: reported and hidden from others for now
    my_reaction: str | None = None
    reactions_count: int | None = None  # only the author is told


class StoryGroup(BaseModel):
    author: StoryAuthor
    stories: list[StoryRead]
    has_unseen: bool
    is_me: bool = False


class StoryViewer(BaseModel):
    user: StoryAuthor
    viewed_at: datetime
    reaction: str | None = None


class StoryReact(BaseModel):
    emoji: str | None = None  # None takes the reaction back


class StoryRing(BaseModel):
    user_id: uuid.UUID
    has_unseen: bool
