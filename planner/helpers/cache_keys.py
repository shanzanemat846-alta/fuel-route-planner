import hashlib


def make_cache_key(prefix: str, *parts) -> str:
    # hashed so the key stays short and safe for any cache backend
    raw = "|".join(str(p).strip().lower() for p in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"
