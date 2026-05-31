import json
from .redis_client import get_redis


class CacheManager:
    def __init__(self, prefix: str = "wca"):
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> str | None:
        r = await get_redis()
        return await r.get(self._key(key))

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        r = await get_redis()
        await r.setex(self._key(key), ttl, value)

    async def get_json(self, key: str) -> dict | None:
        val = await self.get(key)
        if val:
            return json.loads(val)
        return None

    async def set_json(self, key: str, value: dict, ttl: int = 3600) -> None:
        await self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    async def delete(self, key: str) -> None:
        r = await get_redis()
        await r.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        r = await get_redis()
        return bool(await r.exists(self._key(key)))
