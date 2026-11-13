"""MongoDB：有 MONGO_URI 就連 MongoDB（本機或 Atlas），沒有就暫存在記憶體（方便本機測試）

Collections
  players       玩家（以暱稱為單位）與累積戰績        每局結束時更新
  rooms         每個房間從建立到結束的紀錄            建房、開始、結束
  game_records  每局結果、事件日誌、AI 講評           遊戲結束先存，AI 講評好了再補上
  knowledge     防災知識庫（AI 講評的 RAG 素材）       啟動時若是空的就從 data/knowledge.json 匯入
  users         帳號（帳號名＝遊戲暱稱）、密碼雜湊、好友碼、好友名單

遊戲中的即時狀態（位置、水位）只放在伺服器記憶體，不會每幀寫入資料庫。
"""
import datetime
import json
import os
import random
import uuid

LEVEL_ID = "level_1"
KNOWLEDGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "knowledge.json")

_db = None
_mem = {"players": {}, "rooms": {}, "game_records": {}, "users": {}}     # 沒有資料庫時的備案
_status = {"mode": "memory", "error": None}


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def _load_knowledge_file():
    with open(KNOWLEDGE_FILE, encoding="utf-8") as f:
        return json.load(f)


_knowledge_local = _load_knowledge_file()


def connect(uri=None, client=None):
    """連線並建立索引。client 參數是給測試用的（例如 mongomock）"""
    global _db
    uri = uri or os.getenv("MONGO_URI")
    if not uri and client is None:
        print("[db] 沒有設定 MONGO_URI，資料暫存在記憶體（重開就會消失）")
        return
    try:
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(uri, serverSelectionTimeoutMS=4000)
            client.admin.command("ping")
        _db = client[os.getenv("MONGO_DB", "flood_rush")]
        _db.players.create_index("name", unique=True)
        _db.game_records.create_index([("level_id", 1), ("score", -1)])
        _db.game_records.create_index("played_at")
        _db.rooms.create_index([("code", 1), ("created_at", -1)])
        _db.knowledge.create_index("tags")
        _db.users.create_index("name", unique=True)
        _db.users.create_index("friend_code", unique=True)
        _db.game_records.create_index("players.account")
        in_db = sorted((d.get("topic"), d.get("content")) for d in _db.knowledge.find({}, {"topic": 1, "content": 1}))
        in_file = sorted((d.get("topic"), d.get("content")) for d in _knowledge_local)
        if in_db != in_file:                      # 知識檔有新增或修改就重新匯入
            seed_knowledge()
        _status.update(mode="mongodb", error=None)
        print(f"[db] 已連線 MongoDB（資料庫 {_db.name}）")
    except Exception as e:
        _db = None
        _status.update(mode="memory", error=str(e)[:200])
        print("[db] MongoDB 連線失敗，改用記憶體暫存：", e)


def seed_knowledge():
    """把 data/knowledge.json 重新匯入 knowledge collection"""
    if _db is None:
        return 0
    docs = [{**d, "created_at": now()} for d in _load_knowledge_file()]
    _db.knowledge.delete_many({})
    _db.knowledge.insert_many(docs)
    print(f"[db] 已匯入 {len(docs)} 筆防災知識")
    return len(docs)


def _oid(s):
    from bson import ObjectId
    try:
        return ObjectId(s)
    except Exception:
        return None


def _clean(doc):
    """把 ObjectId、時間轉成前端看得懂的格式"""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k == "_id":
            out["id"] = str(v)
        elif isinstance(v, datetime.datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def status():
    info = dict(_status)
    if _db is not None:
        try:
            info["counts"] = {c: _db[c].estimated_document_count()
                              for c in ("players", "rooms", "game_records", "knowledge")}
        except Exception as e:
            info["error"] = str(e)[:200]
    else:
        info["counts"] = {**{c: len(v) for c, v in _mem.items()}, "knowledge": len(_knowledge_local)}
    return info


# ── rooms ──────────────────────────────────────────────────
def room_open(code, host_name):
    doc = {"code": code, "host": host_name, "status": "waiting", "players": [host_name],
           "games": 0, "created_at": now()}
    if _db is not None:
        try:
            return str(_db.rooms.insert_one(doc).inserted_id)
        except Exception as e:
            print("[db] rooms 寫入失敗：", e)
    rid = uuid.uuid4().hex
    _mem["rooms"][rid] = doc
    return rid


def room_update(room_id, status=None, players=None, record_id=None):
    """狀態：waiting → playing → finished（每局結束）→ closed（大家都離開）"""
    if not room_id:
        return
    sets = {"updated_at": now()}
    if status:
        sets["status"] = status
    if players is not None:
        sets["players"] = players
    inc = {"games": 1} if status == "playing" else {}
    push = {"record_ids": record_id} if record_id else {}
    if _db is not None:
        try:
            upd = {"$set": sets}
            if inc:
                upd["$inc"] = inc
            if push:
                upd["$push"] = push
            _db.rooms.update_one({"_id": _oid(room_id)}, upd)
            return
        except Exception as e:
            print("[db] rooms 更新失敗：", e)
    doc = _mem["rooms"].get(room_id)
    if doc:
        doc.update(sets)
        doc["games"] += inc.get("games", 0)
        if record_id:
            doc.setdefault("record_ids", []).append(record_id)


# ── game_records ───────────────────────────────────────────
def save_record(room_code, result, events):
    """遊戲結束馬上存（AI 講評稍後用 update_report 補上），回傳紀錄 id"""
    doc = {"room_code": room_code, "level_id": LEVEL_ID,
           "result": "win" if result["win"] else "lose",
           "score": result["coins"], "stars": result["stars"], "hearts": result["hearts"],
           "fixed": result["fixed"], "failed": result["failed"], "by_type": result["by_type"],
           "scenario": result["scenario"], "scenario_by": result.get("scenario_by", "rule"),
           "disaster": result.get("disaster", "typhoon"), "disaster_name": result.get("disaster_name", "颱風淹水"),
           "water": result["water"], "duration_sec": result["duration"],
           "players": [{"name": p["name"], "account": p.get("account"), "fixed": p["fixed"], "items": p["items"],
                        "title": p["title"]}
                       for p in result["players"]],
           "team": "、".join(p["name"] for p in result["players"]),
           "events": events,
           "ai_report": None, "ai_by": None, "tips": [],
           "played_at": now()}
    if _db is not None:
        try:
            return str(_db.game_records.insert_one(doc).inserted_id)
        except Exception as e:
            print("[db] game_records 寫入失敗：", e)
    rid = uuid.uuid4().hex
    _mem["game_records"][rid] = {**doc, "_id": rid}
    return rid


def update_report(record_id, report, by, tips):
    sets = {"ai_report": report, "ai_by": by, "tips": tips}
    if _db is not None:
        try:
            _db.game_records.update_one({"_id": _oid(record_id)}, {"$set": sets})
            return
        except Exception as e:
            print("[db] 講評寫入失敗：", e)
    if record_id in _mem["game_records"]:
        _mem["game_records"][record_id].update(sets)


def get_record(record_id):
    if _db is not None:
        oid = _oid(record_id)
        return _clean(_db.game_records.find_one({"_id": oid})) if oid else None
    return _clean(_mem["game_records"].get(record_id))


def recent_records(limit=10):
    fields = {"events": 0, "tips": 0}
    if _db is not None:
        try:
            return [_clean(d) for d in _db.game_records.find({}, fields).sort("played_at", -1).limit(limit)]
        except Exception as e:
            print("[db] 查詢失敗：", e)
    rows = sorted(_mem["game_records"].values(), key=lambda r: r["played_at"], reverse=True)[:limit]
    return [_clean({k: v for k, v in r.items() if k not in fields}) for r in rows]


def leaderboard(limit=10):
    """排行榜：用 aggregate 依分數排序，只取需要的欄位"""
    if _db is not None:
        try:
            pipeline = [
                {"$match": {"level_id": LEVEL_ID}},
                {"$sort": {"score": -1, "played_at": 1}},
                {"$limit": limit},
                {"$project": {"_id": 0, "id": {"$toString": "$_id"}, "team": 1, "score": 1,
                              "stars": 1, "fixed": 1, "result": 1}},
            ]
            return list(_db.game_records.aggregate(pipeline))
        except Exception as e:
            print("[db] 查詢失敗：", e)
    rows = sorted(_mem["game_records"].values(), key=lambda r: -r["score"])[:limit]
    return [{"id": r["_id"], **{k: r[k] for k in ("team", "score", "stars", "fixed", "result")}} for r in rows]


def incident_stats():
    """全部玩家累積：每種災情處理成功／失敗幾次（aggregate + $unwind）"""
    if _db is not None:
        try:
            pipeline = [
                {"$unwind": "$events"},
                {"$match": {"events.kind": "incident"}},
                {"$group": {"_id": {"type": "$events.type", "result": "$events.result"}, "n": {"$sum": 1}}},
            ]
            rows = list(_db.game_records.aggregate(pipeline))
        except Exception as e:
            print("[db] 查詢失敗：", e)
            rows = []
    else:
        counts = {}
        for r in _mem["game_records"].values():
            for e in r["events"]:
                if e.get("kind") == "incident":
                    key = (e["type"], e["result"])
                    counts[key] = counts.get(key, 0) + 1
        rows = [{"_id": {"type": t, "result": res}, "n": n} for (t, res), n in counts.items()]
    out = {}
    for r in rows:
        out.setdefault(r["_id"]["type"], {"fixed": 0, "failed": 0, "active": 0})[r["_id"]["result"]] = r["n"]
    return out


# ── players ────────────────────────────────────────────────
def update_players(result):
    for p in result["players"]:
        if p.get("account"):                 # 登入的人：戰績記在帳號底下，和訪客的同名紀錄分開
            update_account_stats(p["account"], p, result)
            continue
        name = p["name"]
        inc = {"games": 1, "wins": 1 if result["win"] else 0, "fixed": p["fixed"], "items": p["items"]}
        if _db is not None:
            try:
                _db.players.update_one(
                    {"name": name},
                    {"$inc": inc, "$max": {"best_score": result["coins"], "best_stars": result["stars"]},
                     "$set": {"last_title": p["title"], "last_played": now()},
                     "$setOnInsert": {"created_at": now()}},
                    upsert=True)
                continue
            except Exception as e:
                print("[db] players 更新失敗：", e)
        doc = _mem["players"].setdefault(name, {"name": name, "games": 0, "wins": 0, "fixed": 0, "items": 0,
                                                "best_score": 0, "best_stars": 0, "created_at": now()})
        for k, v in inc.items():
            doc[k] += v
        doc["best_score"] = max(doc["best_score"], result["coins"])
        doc["best_stars"] = max(doc["best_stars"], result["stars"])
        doc.update(last_title=p["title"], last_played=now())


def mark_tutorial(name):
    """玩家完成新手教學（players.tutorial_done = true）"""
    if not name:
        return
    if _db is not None:
        try:
            _db.players.update_one({"name": name}, {"$set": {"tutorial_done": True, "tutorial_at": now()},
                                                     "$setOnInsert": {"created_at": now(), "games": 0, "wins": 0,
                                                                      "fixed": 0, "items": 0}}, upsert=True)
            return
        except Exception as e:
            print("[db] 教學紀錄寫入失敗：", e)
    doc = _mem["players"].setdefault(name, {"name": name, "games": 0, "wins": 0, "fixed": 0, "items": 0,
                                            "best_score": 0, "best_stars": 0, "created_at": now()})
    doc["tutorial_done"] = True


def get_player(name):
    if _db is not None:
        return _clean(_db.players.find_one({"name": name}))
    doc = _mem["players"].get(name)
    return _clean(dict(doc)) if doc else None


# ── knowledge（簡化版 RAG：用 tags 關鍵字檢索）─────────────────
def find_knowledge(tags, limit=2):
    """依 tags 的順序，每個 tag 挑一筆還沒選過的知識；同一 tag 有多筆時隨機挑，每局講評才不會都一樣"""
    if _db is not None:
        try:
            pool = list(_db.knowledge.find({"tags": {"$in": list(tags)}}, {"_id": 0, "created_at": 0}))
        except Exception as e:
            print("[db] 知識庫查詢失敗，改用本機檔案：", e)
            pool = None
    else:
        pool = None
    if pool is None:
        pool = [d for d in _knowledge_local if set(d["tags"]) & set(tags)]
    picked = []
    for tag in tags:
        options = [d for d in pool if tag in d["tags"] and d not in picked]
        if options:
            picked.append(random.choice(options))
        if len(picked) >= limit:
            break
    return picked


def all_knowledge(tag=None):
    query = {"tags": tag} if tag else {}
    if _db is not None:
        try:
            return list(_db.knowledge.find(query, {"_id": 0, "created_at": 0}))
        except Exception as e:
            print("[db] 知識庫查詢失敗：", e)
    return [d for d in _knowledge_local if not tag or tag in d["tags"]]


if __name__ == "__main__":
    # python db.py seed   → 重新匯入知識庫到 MongoDB
    import sys

    from dotenv import load_dotenv
    load_dotenv()
    connect()
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        print("匯入筆數：", seed_knowledge() if _db is not None else "沒有連上 MongoDB")
    print(status())


# ── users：簡單帳號（帳號名就是遊戲暱稱）＋好友 ─────────────────────
# 密碼只存雜湊（werkzeug），不存明碼。好友用 6 碼「好友碼」互加，加了就是雙向好友。
FRIEND_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_friend_code():
    while True:
        code = "".join(random.choice(FRIEND_CODE_CHARS) for _ in range(6))
        if not find_user(friend_code=code):
            return code


def find_user(name=None, friend_code=None):
    """依帳號名或好友碼找帳號（回傳含密碼雜湊的原始資料，只給後端用）"""
    q = {"name": name} if name else {"friend_code": friend_code}
    if _db is not None:
        return _db.users.find_one(q)
    for u in _mem["users"].values():
        if all(u.get(k) == v for k, v in q.items()):
            return u
    return None


def create_user(name, password_hash):
    """建立帳號；帳號名已被用走回傳 None"""
    if find_user(name=name):
        return None
    doc = {"name": name, "password_hash": password_hash, "friend_code": _new_friend_code(),
           "friends": [], "created_at": now()}
    if _db is not None:
        try:
            _db.users.insert_one(doc)
        except Exception as e:            # unique index 擋下同時註冊
            print("[db] users 寫入失敗：", e)
            return None
    else:
        _mem["users"][name] = doc
    return doc


def add_friend(name, other):
    """雙向加好友"""
    if _db is not None:
        _db.users.update_one({"name": name}, {"$addToSet": {"friends": other}})
        _db.users.update_one({"name": other}, {"$addToSet": {"friends": name}})
        return
    for a, b in ((name, other), (other, name)):
        u = _mem["users"].get(a)
        if u is not None and b not in u["friends"]:
            u["friends"].append(b)


def remove_friend(name, other):
    if _db is not None:
        _db.users.update_one({"name": name}, {"$pull": {"friends": other}})
        _db.users.update_one({"name": other}, {"$pull": {"friends": name}})
        return
    for a, b in ((name, other), (other, name)):
        u = _mem["users"].get(a)
        if u is not None and b in u["friends"]:
            u["friends"].remove(b)


EMPTY_STATS = {"games": 0, "wins": 0, "fixed": 0, "items": 0, "best_score": 0, "best_stars": 0}


def update_account_stats(name, p, result):
    """帳號的累積戰績存在 users.stats（只算登入後玩的局）"""
    inc = {"stats.games": 1, "stats.wins": 1 if result["win"] else 0, "stats.fixed": p["fixed"], "stats.items": p["items"]}
    if _db is not None:
        try:
            _db.users.update_one({"name": name}, {"$inc": inc, "$max": {"stats.best_score": result["coins"],
                                                                     "stats.best_stars": result["stars"]}})
            return
        except Exception as e:
            print("[db] 帳號戰績更新失敗：", e)
    u = _mem["users"].get(name)
    if u is None:
        return
    st = u.setdefault("stats", dict(EMPTY_STATS))
    for k, v in inc.items():
        st[k.split(".")[1]] += v
    st["best_score"] = max(st["best_score"], result["coins"])
    st["best_stars"] = max(st["best_stars"], result["stars"])


def account_stats(name):
    u = find_user(name=name) or {}
    return {**EMPTY_STATS, **(u.get("stats") or {})}


def account_records(name, limit=10):
    """帳號最近玩過的局（只找登入狀態下玩的：game_records.players.account）"""
    fields = {"events": 0}
    if _db is not None:
        try:
            rows = _db.game_records.find({"players.account": name}, fields).sort("played_at", -1).limit(limit)
            return [_clean(r) for r in rows]
        except Exception as e:
            print("[db] 個人紀錄查詢失敗：", e)
    rows = [r for r in _mem["game_records"].values() if any(p.get("account") == name for p in r["players"])]
    rows.sort(key=lambda r: r["played_at"], reverse=True)
    return [_clean({k: v for k, v in r.items() if k != "events"}) for r in rows[:limit]]


# ── 防災基金與防災建設（局間用金幣買，開局每人帶一樣）────────────────
# 登入的人存在 users（帳號），訪客存在 players（暱稱）；欄位：fund 防災基金、owned 已蓋好的建設
def _wallet_target(name, account):
    return ("users", account) if account else ("players", name)


def _wallet_doc(coll, key):
    """取得錢包；第一次用時給一筆起始基金"""
    import disasters
    if _db is not None:
        try:
            c = _db[coll]
            c.update_one({"name": key, "fund": {"$exists": False}},
                         {"$set": {"fund": disasters.START_FUND, "owned": []}}, upsert=(coll == "players"))
            return c.find_one({"name": key}, {"fund": 1, "owned": 1}) or {}
        except Exception as e:
            print("[db] 防災基金讀取失敗：", e)
    store = _mem[coll]
    doc = store.get(key)
    if doc is None:
        if coll == "users":
            return {}
        doc = store[key] = {"name": key, "games": 0, "wins": 0, "fixed": 0, "items": 0,
                            "best_score": 0, "best_stars": 0, "created_at": now()}
    doc.setdefault("fund", disasters.START_FUND)
    doc.setdefault("owned", [])
    return doc


def get_wallet(name, account=None):
    coll, key = _wallet_target(name, account)
    doc = _wallet_doc(coll, key)
    return {"fund": int(doc.get("fund", 0)), "owned": list(doc.get("owned", []))}


def add_fund(name, account, amount):
    if amount <= 0:
        return
    coll, key = _wallet_target(name, account)
    _wallet_doc(coll, key)
    if _db is not None:
        try:
            _db[coll].update_one({"name": key}, {"$inc": {"fund": int(amount)}})
            return
        except Exception as e:
            print("[db] 防災基金更新失敗：", e)
    doc = _mem[coll].get(key)
    if doc is not None:
        doc["fund"] = doc.get("fund", 0) + int(amount)


def buy_facility(name, account, item, price):
    """買防災建設：錢夠、還沒買過才成功（資料庫用條件更新，按兩下也不會扣兩次錢）"""
    coll, key = _wallet_target(name, account)
    doc = _wallet_doc(coll, key)
    if item in doc.get("owned", []):
        return False, "已經蓋好了"
    if doc.get("fund", 0) < price:
        return False, "防災基金不夠"
    if _db is not None:
        try:
            r = _db[coll].update_one({"name": key, "fund": {"$gte": price}, "owned": {"$ne": item}},
                                     {"$inc": {"fund": -price}, "$addToSet": {"owned": item}})
            return (True, "") if r.modified_count else (False, "防災基金不夠")
        except Exception as e:
            print("[db] 購買失敗：", e)
            return False, "暫時無法購買，請再試一次"
    doc["fund"] -= price
    doc["owned"].append(item)
    return True, ""
