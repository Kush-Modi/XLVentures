import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

def cache_get(key: str):
    val = r.get(key)
    return json.loads(val) if val else None

def cache_set(key: str, value, ttl: int = 300):
    r.setex(key, ttl, json.dumps(value))

def cache_delete(key: str):
    r.delete(key)

# HITL session bridge
def set_hitl_pending(session_id: str, payload: dict, ttl: int = 600):
    r.setex(f"hitl:{session_id}", ttl, json.dumps(payload))

def get_hitl_pending(session_id: str):
    val = r.get(f"hitl:{session_id}")
    return json.loads(val) if val else None

def resolve_hitl(session_id: str, decision: str):
    r.setex(f"hitl:{session_id}:decision", 300, decision)

def get_hitl_decision(session_id: str):
    return r.get(f"hitl:{session_id}:decision")

def log_session(session_id: str, message: str):
    """Log a message for a specific session to Redis."""
    r.rpush(f"logs:{session_id}", message)
    r.expire(f"logs:{session_id}", 600) # Expire logs after 10 minutes

def get_session_logs(session_id: str):
    """Retrieve all logged messages for a session."""
    return r.lrange(f"logs:{session_id}", 0, -1)