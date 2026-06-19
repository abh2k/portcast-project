from pathlib import Path

from redis import Redis

from app.config import get_settings


def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def load_lua_script(redis_client: Redis, lua_path: str) -> str:
    script = Path(lua_path).read_text(encoding="utf-8")
    return redis_client.script_load(script)
