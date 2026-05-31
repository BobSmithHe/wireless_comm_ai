from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime | None = None


@dataclass
class ConversationInfo:
    id: int
    user_id: int
    title: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
