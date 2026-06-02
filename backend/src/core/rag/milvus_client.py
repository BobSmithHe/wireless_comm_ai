"""
Shared MilvusClient wrapper — single connection per URI+db for all collections.
"""
from __future__ import annotations

from pymilvus import MilvusClient

_clients: dict[str, MilvusClient] = {}


def get_milvus_client(uri: str, token: str = "", db_name: str = "") -> MilvusClient:
    """Get or create a MilvusClient for a given URI + db_name."""
    key = f"{uri}:{db_name}:{token}"
    if key not in _clients:
        kwargs: dict = {"uri": uri}
        if token:
            kwargs["token"] = token
        if db_name:
            kwargs["db_name"] = db_name
        _clients[key] = MilvusClient(**kwargs)
    return _clients[key]
