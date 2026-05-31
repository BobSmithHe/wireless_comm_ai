from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryItem:
    id: int
    user_id: int
    layer: int
    content: str
    score: float = 0.0
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None
