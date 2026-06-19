from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.base import Base
from src.database.models import User
from src.services.memory_graph_service import MemoryGraphService


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)
    return session()


def test_add_edge_lists_graph_and_builds_context():
    db = _make_db()
    user = User(username="graph_user", email="graph@example.com", password_hash="hash")
    db.add(user)
    db.commit()
    db.refresh(user)

    svc = MemoryGraphService()
    edge = svc.add_edge(
        db=db,
        user_id=user.id,
        source_type="user",
        source_name="User",
        relation="prefers",
        target_type="language",
        target_name="Chinese answers",
    )

    assert edge is not None
    graph = svc.list_graph(db, user.id)
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["relation"] == "prefers"

    context = svc.build_context(db, user.id, "please answer in Chinese")
    assert "[用户长期记忆图谱]" in context
    assert "Chinese answers" in context


def test_add_edge_upserts_duplicate_triple():
    db = _make_db()
    user = User(username="graph_user2", email="graph2@example.com", password_hash="hash")
    db.add(user)
    db.commit()
    db.refresh(user)

    svc = MemoryGraphService()
    for _ in range(2):
        svc.add_edge(
            db=db,
            user_id=user.id,
            source_type="project",
            source_name="wireless_comm_ai",
            relation="uses",
            target_type="framework",
            target_name="FastAPI",
        )

    graph = svc.list_graph(db, user.id)
    assert len(graph["edges"]) == 1
