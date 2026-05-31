from dataclasses import dataclass
from datetime import datetime


@dataclass
class KnowledgeItem:
    id: int
    title: str
    content: str
    source_type: str = "markdown"
    category: str = ""
    created_at: datetime | None = None


@dataclass
class SearchResult:
    content: str
    score: float
    source: str
    chunk_index: int = 0
