from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserProfile:
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime
