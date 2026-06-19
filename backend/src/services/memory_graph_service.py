"""Lightweight user memory graph backed by MySQL."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..database.models import MemoryEdge, MemoryNode
from ..utils.logger import logger


ALLOWED_NODE_TYPES = {
    "user", "project", "preference", "concept", "tool", "framework",
    "database", "language", "task", "domain", "instruction",
}

ALLOWED_RELATIONS = {
    "prefers", "dislikes", "works_on", "uses", "cares_about",
    "asked_about", "is_building", "wants", "knows", "related_to",
    "has_instruction",
}

SENSITIVE_PATTERNS = [
    r"\bpassword\b", r"\bpasswd\b", r"\bsecret\b", r"\btoken\b",
    r"\bapi[_-]?key\b", r"\bcredential", r"身份证", r"银行卡",
]


@dataclass
class NodePayload:
    type: str
    name: str
    properties: dict[str, Any]
    confidence: float


@dataclass
class EdgePayload:
    source: NodePayload
    relation: str
    target: NodePayload
    properties: dict[str, Any]
    confidence: float


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_relation(value: str) -> str:
    value = value.strip().lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", value)


def _clamp_confidence(value: Any, default: float = 0.7) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def _contains_sensitive_text(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def _json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"edges": []}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"edges": []}


class MemoryGraphService:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    def build_context(self, db: Session, user_id: int, query: str, limit: int = 8) -> str:
        """Return a compact system-context block from active graph memories."""
        edges = self._rank_edges(db, user_id, query, limit)
        if not edges:
            return ""

        for edge in edges:
            edge.last_used_at = datetime.utcnow()
        db.commit()

        lines = []
        for edge in edges:
            source = edge.source_node.name
            target = edge.target_node.name
            relation = edge.relation.replace("_", " ")
            lines.append(f"- {source} {relation} {target}.")
        return "[用户长期记忆图谱]\n" + "\n".join(lines)

    async def extract_and_store(
        self,
        db: Session,
        user_id: int,
        user_message: str,
        assistant_message: str,
        source_message_id: int | None = None,
    ) -> int:
        """Extract durable triples from one exchange and upsert them."""
        if not self.llm:
            return 0
        if _contains_sensitive_text(user_message) or _contains_sensitive_text(assistant_message):
            return 0

        prompt = self._build_extraction_prompt(user_message, assistant_message)
        try:
            raw = await self.llm.raw_chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1200,
            )
        except Exception as exc:
            logger.warning(f"Memory graph extraction failed: {exc}")
            return 0

        payload = _json_from_text(raw)
        edges = self._parse_edges(payload)
        if not edges:
            edges = self._heuristic_edges(user_message)
        stored = 0
        for edge in edges[:12]:
            if self._upsert_edge(db, user_id, edge, source_message_id):
                stored += 1
        if stored:
            db.commit()
        return stored

    def list_graph(self, db: Session, user_id: int) -> dict[str, list[dict[str, Any]]]:
        nodes = (
            db.query(MemoryNode)
            .filter(MemoryNode.user_id == user_id, MemoryNode.is_active.is_(True))
            .order_by(MemoryNode.updated_at.desc())
            .all()
        )
        edges = (
            db.query(MemoryEdge)
            .options(joinedload(MemoryEdge.source_node), joinedload(MemoryEdge.target_node))
            .filter(MemoryEdge.user_id == user_id, MemoryEdge.is_active.is_(True))
            .order_by(MemoryEdge.updated_at.desc())
            .all()
        )
        return {
            "nodes": [self._node_to_dict(n) for n in nodes],
            "edges": [self._edge_to_dict(e) for e in edges],
        }

    def add_edge(
        self,
        db: Session,
        user_id: int,
        source_type: str,
        source_name: str,
        relation: str,
        target_type: str,
        target_name: str,
        confidence: float = 0.9,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        source = self._parse_node({
            "type": source_type,
            "name": source_name,
            "confidence": confidence,
        })
        target = self._parse_node({
            "type": target_type,
            "name": target_name,
            "confidence": confidence,
        })
        if not source or not target:
            return None
        normalized_relation = _normalize_relation(relation)
        if normalized_relation not in ALLOWED_RELATIONS:
            normalized_relation = "related_to"
        payload = EdgePayload(
            source=source,
            relation=normalized_relation,
            target=target,
            properties=properties or {},
            confidence=_clamp_confidence(confidence, default=0.9),
        )
        self._upsert_edge(db, user_id, payload, source_message_id=None)
        db.commit()
        edge = (
            db.query(MemoryEdge)
            .options(joinedload(MemoryEdge.source_node), joinedload(MemoryEdge.target_node))
            .filter(
                MemoryEdge.user_id == user_id,
                MemoryEdge.source_node.has(
                    MemoryNode.normalized_name == _normalize_name(source_name),
                ),
                MemoryEdge.relation == normalized_relation,
                MemoryEdge.target_node.has(
                    MemoryNode.normalized_name == _normalize_name(target_name),
                ),
            )
            .first()
        )
        return self._edge_to_dict(edge) if edge else None

    def delete_edge(self, db: Session, user_id: int, edge_id: int) -> bool:
        edge = (
            db.query(MemoryEdge)
            .filter(MemoryEdge.id == edge_id, MemoryEdge.user_id == user_id)
            .first()
        )
        if not edge:
            return False
        edge.is_active = False
        db.commit()
        return True

    def delete_node(self, db: Session, user_id: int, node_id: int) -> bool:
        node = (
            db.query(MemoryNode)
            .filter(MemoryNode.id == node_id, MemoryNode.user_id == user_id)
            .first()
        )
        if not node:
            return False
        node.is_active = False
        db.query(MemoryEdge).filter(
            MemoryEdge.user_id == user_id,
            or_(MemoryEdge.source_node_id == node_id, MemoryEdge.target_node_id == node_id),
        ).update({"is_active": False}, synchronize_session=False)
        db.commit()
        return True

    def clear_user_graph(self, db: Session, user_id: int) -> None:
        db.query(MemoryEdge).filter(MemoryEdge.user_id == user_id).update(
            {"is_active": False}, synchronize_session=False,
        )
        db.query(MemoryNode).filter(MemoryNode.user_id == user_id).update(
            {"is_active": False}, synchronize_session=False,
        )
        db.commit()

    def _rank_edges(self, db: Session, user_id: int, query: str, limit: int) -> list[MemoryEdge]:
        edges = (
            db.query(MemoryEdge)
            .options(joinedload(MemoryEdge.source_node), joinedload(MemoryEdge.target_node))
            .filter(MemoryEdge.user_id == user_id, MemoryEdge.is_active.is_(True))
            .order_by(MemoryEdge.updated_at.desc())
            .limit(120)
            .all()
        )
        if not edges:
            return []

        terms = {t for t in re.split(r"\W+", query.lower()) if len(t) >= 2}

        def score(edge: MemoryEdge) -> tuple[float, datetime]:
            text = " ".join([
                edge.source_node.name,
                edge.relation,
                edge.target_node.name,
                json.dumps(edge.properties or {}, ensure_ascii=False),
            ]).lower()
            overlap = sum(1 for term in terms if term in text)
            memory_boost = 2 if edge.relation in {"prefers", "has_instruction", "works_on"} else 0
            return (overlap + memory_boost + float(edge.confidence or 0), edge.updated_at)

        ranked = sorted(edges, key=score, reverse=True)
        return ranked[:limit]

    def _upsert_node(self, db: Session, user_id: int, payload: NodePayload) -> MemoryNode:
        normalized = _normalize_name(payload.name)
        node = (
            db.query(MemoryNode)
            .filter(
                MemoryNode.user_id == user_id,
                MemoryNode.type == payload.type,
                MemoryNode.normalized_name == normalized,
            )
            .first()
        )
        if node:
            node.name = payload.name.strip()
            node.properties = {**(node.properties or {}), **payload.properties}
            node.confidence = max(float(node.confidence or 0), payload.confidence)
            node.is_active = True
            return node

        node = MemoryNode(
            user_id=user_id,
            type=payload.type,
            name=payload.name.strip(),
            normalized_name=normalized,
            properties=payload.properties,
            confidence=payload.confidence,
            is_active=True,
        )
        db.add(node)
        db.flush()
        return node

    def _upsert_edge(
        self,
        db: Session,
        user_id: int,
        payload: EdgePayload,
        source_message_id: int | None,
    ) -> bool:
        source = self._upsert_node(db, user_id, payload.source)
        target = self._upsert_node(db, user_id, payload.target)
        edge = (
            db.query(MemoryEdge)
            .filter(
                MemoryEdge.user_id == user_id,
                MemoryEdge.source_node_id == source.id,
                MemoryEdge.relation == payload.relation,
                MemoryEdge.target_node_id == target.id,
            )
            .first()
        )
        if edge:
            edge.properties = {**(edge.properties or {}), **payload.properties}
            edge.confidence = max(float(edge.confidence or 0), payload.confidence)
            edge.source_message_id = source_message_id or edge.source_message_id
            edge.is_active = True
            return True

        db.add(MemoryEdge(
            user_id=user_id,
            source_node_id=source.id,
            relation=payload.relation,
            target_node_id=target.id,
            properties=payload.properties,
            confidence=payload.confidence,
            source_message_id=source_message_id,
            is_active=True,
        ))
        return True

    def _parse_edges(self, payload: dict[str, Any]) -> list[EdgePayload]:
        parsed = []
        for item in payload.get("edges", []):
            try:
                relation = _normalize_relation(item.get("relation", "related_to"))
                if relation not in ALLOWED_RELATIONS:
                    relation = "related_to"
                source = self._parse_node(item.get("source") or {})
                target = self._parse_node(item.get("target") or {})
                if not source or not target:
                    continue
                text = f"{source.name} {relation} {target.name}"
                if _contains_sensitive_text(text):
                    continue
                parsed.append(EdgePayload(
                    source=source,
                    relation=relation,
                    target=target,
                    properties=item.get("properties") if isinstance(item.get("properties"), dict) else {},
                    confidence=_clamp_confidence(item.get("confidence")),
                ))
            except (TypeError, AttributeError):
                continue
        return parsed

    def _heuristic_edges(self, user_message: str) -> list[EdgePayload]:
        text = user_message.strip()
        if not text or _contains_sensitive_text(text):
            return []

        lowered = text.lower()
        explicit_memory = any(marker in text for marker in ("记住", "请记住", "以后", "偏好", "希望"))
        if not explicit_memory:
            return []

        user = NodePayload(type="user", name="User", properties={}, confidence=0.95)
        edges: list[EdgePayload] = []

        if "中文" in text:
            edges.append(EdgePayload(
                source=user,
                relation="prefers",
                target=NodePayload(type="language", name="中文回答", properties={}, confidence=0.95),
                properties={"source": "heuristic"},
                confidence=0.95,
            ))

        if "代码审查" in text or "code review" in lowered:
            target_name = "代码审查优先指出高风险问题和可执行修复建议"
            edges.append(EdgePayload(
                source=user,
                relation="has_instruction",
                target=NodePayload(type="instruction", name=target_name, properties={}, confidence=0.9),
                properties={"source": "heuristic"},
                confidence=0.9,
            ))

        if edges:
            return edges

        cleaned = re.sub(r"^(请)?记住[:：]?", "", text).strip()
        cleaned = cleaned[:120]
        if cleaned:
            edges.append(EdgePayload(
                source=user,
                relation="has_instruction" if "以后" in text or "希望" in text else "prefers",
                target=NodePayload(type="instruction", name=cleaned, properties={}, confidence=0.75),
                properties={"source": "heuristic"},
                confidence=0.75,
            ))
        return edges

    def _parse_node(self, data: dict[str, Any]) -> NodePayload | None:
        name = str(data.get("name", "")).strip()
        if not name or len(name) > 255 or _contains_sensitive_text(name):
            return None
        node_type = str(data.get("type", "concept")).strip().lower()
        if node_type not in ALLOWED_NODE_TYPES:
            node_type = "concept"
        properties = data.get("properties") if isinstance(data.get("properties"), dict) else {}
        return NodePayload(
            type=node_type,
            name=name,
            properties=properties,
            confidence=_clamp_confidence(data.get("confidence")),
        )

    def _build_extraction_prompt(self, user_message: str, assistant_message: str) -> str:
        return f"""Extract durable user memory graph triples from this exchange.

Store only stable user preferences, durable project facts, explicit instructions, recurring interests, or tool/technology choices.
Do not store passwords, tokens, API keys, credentials, personal identifiers, private contact details, or one-off temporary details.
Return strict JSON only, with this shape:
{{
  "edges": [
    {{
      "source": {{"type": "user|project|preference|concept|tool|framework|database|language|task|domain|instruction", "name": "...", "confidence": 0.0}},
      "relation": "prefers|dislikes|works_on|uses|cares_about|asked_about|is_building|wants|knows|related_to|has_instruction",
      "target": {{"type": "...", "name": "...", "confidence": 0.0}},
      "confidence": 0.0,
      "properties": {{}}
    }}
  ]
}}
If nothing should be stored, return {{"edges":[]}}.

User message:
{user_message[:3000]}

Assistant message:
{assistant_message[:3000]}
"""

    @staticmethod
    def _node_to_dict(node: MemoryNode) -> dict[str, Any]:
        return {
            "id": node.id,
            "type": node.type,
            "name": node.name,
            "properties": node.properties or {},
            "confidence": node.confidence,
            "created_at": node.created_at.isoformat() if node.created_at else None,
            "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        }

    @staticmethod
    def _edge_to_dict(edge: MemoryEdge) -> dict[str, Any]:
        return {
            "id": edge.id,
            "source": MemoryGraphService._node_to_dict(edge.source_node),
            "relation": edge.relation,
            "target": MemoryGraphService._node_to_dict(edge.target_node),
            "properties": edge.properties or {},
            "confidence": edge.confidence,
            "source_message_id": edge.source_message_id,
            "created_at": edge.created_at.isoformat() if edge.created_at else None,
            "updated_at": edge.updated_at.isoformat() if edge.updated_at else None,
            "last_used_at": edge.last_used_at.isoformat() if edge.last_used_at else None,
        }
