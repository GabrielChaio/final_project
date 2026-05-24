import json
import hashlib
import secrets
from pathlib import Path

ACCOUNT_FILE = Path(__file__).resolve().parent / "account.json"
_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # A-Z + 2-9，排除易混淆字元 0 O 1 I L

def generate_recovery_key() -> str:
    segments = ["".join(secrets.choice(_CHARS) for _ in range(4)) for _ in range(4)]
    return "-".join(segments)

def hash_key(key: str) -> str:
    """將 Recovery Key 正規化後計算 SHA-256。"""
    return hashlib.sha256(key.strip().upper().encode()).hexdigest()

def load() -> dict | None:
    """讀取本機帳號，不存在或損毀回傳 None。"""
    try:
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "player_id" in data and "recovery_key" in data:
            return data
        return None
    except Exception:
        return None

def save(player_id: str, color: str, recovery_key: str) -> dict:
    data = {"player_id": player_id, "color": color, "recovery_key": recovery_key}
    with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
