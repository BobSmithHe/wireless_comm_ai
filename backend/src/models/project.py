from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProjectInfo:
    id: int
    user_id: int
    name: str
    description: str = ""
    code_files: list = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
