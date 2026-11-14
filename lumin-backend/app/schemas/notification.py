import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    body: str
    read: bool
    type: NotificationType | None = None
    target_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    actor_avatar_url: str | None = None
    audience: str | None = None
    created_at: datetime
