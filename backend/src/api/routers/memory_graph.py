from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.config import get_db
from ...services.memory_graph_service import MemoryGraphService
from ..deps import get_current_user, get_memory_graph_service


router = APIRouter(prefix="/api/memory-graph", tags=["memory-graph"])


class MemoryEdgeCreateRequest(BaseModel):
    source_type: str = Field(default="user", max_length=50)
    source_name: str = Field(max_length=255)
    relation: str = Field(max_length=80)
    target_type: str = Field(default="concept", max_length=50)
    target_name: str = Field(max_length=255)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def list_memory_graph(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    memory_graph: MemoryGraphService = Depends(get_memory_graph_service),
):
    return memory_graph.list_graph(db, user.id)


@router.post("/edges")
def add_memory_edge(
    req: MemoryEdgeCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    memory_graph: MemoryGraphService = Depends(get_memory_graph_service),
):
    edge = memory_graph.add_edge(
        db=db,
        user_id=user.id,
        source_type=req.source_type,
        source_name=req.source_name,
        relation=req.relation,
        target_type=req.target_type,
        target_name=req.target_name,
        confidence=req.confidence,
        properties=req.properties,
    )
    if not edge:
        raise HTTPException(400, "Invalid memory edge")
    return edge


@router.delete("/edges/{edge_id}")
def delete_memory_edge(
    edge_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    memory_graph: MemoryGraphService = Depends(get_memory_graph_service),
):
    if not memory_graph.delete_edge(db, user.id, edge_id):
        raise HTTPException(404, "Memory edge not found")
    return {"status": "deleted", "edge_id": edge_id}


@router.delete("/nodes/{node_id}")
def delete_memory_node(
    node_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    memory_graph: MemoryGraphService = Depends(get_memory_graph_service),
):
    if not memory_graph.delete_node(db, user.id, node_id):
        raise HTTPException(404, "Memory node not found")
    return {"status": "deleted", "node_id": node_id}


@router.delete("")
def clear_memory_graph(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    memory_graph: MemoryGraphService = Depends(get_memory_graph_service),
):
    memory_graph.clear_user_graph(db, user.id)
    return {"status": "cleared"}
