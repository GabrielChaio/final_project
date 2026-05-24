import requests
from datetime import datetime

FIREBASE_URL = "https://minesweeper-game-e53e6-default-rtdb.asia-southeast1.firebasedatabase.app"
_TIMEOUT = 6

def _url(path: str) -> str:
    return f"{FIREBASE_URL}/{path}.json"

# ── 基礎 REST 操作 ────────────────────────────────────────────────────────────

def _get_raw(path: str):
    """回傳 (ok: bool, data).
    ok=True  → data 為 JSON 內容（路徑不存在時為 None）。
    ok=False → data 為 HTTP 狀態碼整數（伺服器有回應）或 None（網路異常）。
    """
    try:
        r = requests.get(_url(path), timeout=_TIMEOUT)
        if r.status_code == 200:
            return True, r.json()
        return False, r.status_code
    except Exception:
        return False, None

def _put(path: str, data) -> bool:
    try:
        r = requests.put(_url(path), json=data, timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False

def _post(path: str, data) -> str | None:
    """POST（Firebase push），回傳新節點 key 或 None。"""
    try:
        r = requests.post(_url(path), json=data, timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("name")
        return None
    except Exception:
        return None

def _delete(path: str) -> bool:
    try:
        r = requests.delete(_url(path), timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False

def is_online() -> bool:
    try:
        r = requests.get(f"{FIREBASE_URL}/.json?shallow=true", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

# ── 帳號操作 ─────────────────────────────────────────────────────────────────

def user_exists(player_id: str) -> bool | None:
    """True = 存在，False = 不存在，None = 網路錯誤。"""
    ok, data = _get_raw(f"users/{player_id}")
    if not ok:
        return None
    return data is not None

def register_user(player_id: str, color: str, recovery_key_hash: str) -> tuple[bool, str | None]:
    """回傳 (成功, 錯誤訊息)。"""
    exists = user_exists(player_id)
    if exists is None:
        return False, "網路錯誤，請稍後再試"
    if exists:
        return False, "此玩家 ID 已被使用"
    ok1 = _put(f"users/{player_id}", {
        "color": color,
        "created_at": datetime.now().isoformat()
    })
    ok2 = _put(f"auth/{player_id}", {
        "recovery_key_hash": recovery_key_hash
    })
    if ok1 and ok2:
        return True, None
    return False, "寫入失敗，請稍後再試"

def verify_login(player_id: str, recovery_key_hash: str) -> tuple[bool, str]:
    """回傳 (成功, color 或錯誤訊息)。"""
    ok, user_data = _get_raw(f"users/{player_id}")
    if not ok:
        return False, "網路錯誤，請稍後再試"
    if user_data is None:
        return False, "找不到此玩家 ID"
    ok, auth_data = _get_raw(f"auth/{player_id}")
    if not ok:
        if auth_data in (401, 403):
            return False, "伺服器拒絕存取（Firebase 安全規則未開放 auth/ 讀取）"
        return False, "網路錯誤，請稍後再試"
    if auth_data is None:
        return False, "找不到驗證資料"
    if auth_data.get("recovery_key_hash", "") == recovery_key_hash:
        color = user_data.get("color", "#000000")
        return True, color
    return False, "Recovery Key 錯誤"

# ── 排行榜 ────────────────────────────────────────────────────────────────────

def upload_score(difficulty: str, player_id: str, player_color: str,
                 time_sec: float, challenge_type: str) -> bool:
    entry = {
        "player_id":     player_id,
        "player_color":  player_color,
        "time_sec":      round(time_sec, 3),
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "challenge_type": challenge_type
    }
    key = _post(f"leaderboard/{difficulty}", entry)
    return key is not None

def get_leaderboard(difficulty: str, challenge_type: str) -> list | None:
    """回傳排序後前 10 筆，空榜為 []，網路錯誤為 None。"""
    try:
        r = requests.get(_url(f"leaderboard/{difficulty}"), timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return []
    entries = [
        v for v in data.values()
        if isinstance(v, dict) and v.get("challenge_type") == challenge_type
    ]
    entries.sort(key=lambda x: (x.get("time_sec", 0), x.get("date", "")))
    return entries[:10]

# ── 遊戲紀錄（Replay） ────────────────────────────────────────────────────────

def upload_replay(player_id: str, replay_data: dict) -> str | None:
    """回傳新節點 key，失敗回傳 None。"""
    return _post(f"records/{player_id}", replay_data)

def get_replay_list(player_id: str) -> list | None:
    """回傳該玩家的所有回放摘要清單，網路錯誤回傳 None。"""
    try:
        r = requests.get(_url(f"records/{player_id}"), timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return []
    result = []
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        meta = val.get("meta", {})
        result.append({
            "record_id":    key,
            "player_id":    meta.get("player_id", "?"),
            "player_color": meta.get("player_color", "#000000"),
            "difficulty":   meta.get("difficulty", "?"),
            "result":       meta.get("result", "?"),
            "time_sec":     meta.get("time_sec", 0),
            "date":         meta.get("date", "")[:10],
            "full_data":    val,
        })
    result.sort(key=lambda x: x.get("date", ""), reverse=True)
    return result

def delete_replay(player_id: str, record_id: str) -> bool:
    return _delete(f"records/{player_id}/{record_id}")
