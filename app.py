"""災變大作戰：災難救援隊 — Flask + Flask-SocketIO 入口"""
from dotenv import load_dotenv

load_dotenv()

import os  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402

from flask import Flask, jsonify, render_template, request, session  # noqa: E402
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402
from flask_socketio import SocketIO, emit, join_room, leave_room  # noqa: E402

import ai  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402
from game import GAME_TIME, Room, new_code  # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)       # 登入記住 30 天
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

db.connect()
socketio.start_background_task(llm.warm_up)    # 有 Ollama 的話先把模型載進記憶體

rooms = {}       # 房間代碼 -> Room
sid_room = {}    # 連線 sid -> 房間代碼
sid_user = {}    # 連線 sid -> 登入的帳號名（訪客沒有）
INTRO_SECONDS = 5


app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0       # 改了 js/css 不會被瀏覽器舊快取卡住


@app.context_processor
def asset_helper():
    """asset('js/main.js') → /static/js/main.js?v=檔案修改時間；檔案一改，網址就變，瀏覽器一定會重新下載"""
    def asset(path):
        try:
            v = int(os.path.getmtime(os.path.join(app.static_folder, path)))
        except OSError:
            v = 0
        return f"/static/{path}?v={v}"
    return {"asset": asset}


# ── REST API ───────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/leaderboard")
def api_leaderboard():
    limit = min(50, max(1, request.args.get("limit", 10, type=int)))
    return jsonify(db.leaderboard(limit))


@app.route("/api/records")
def api_records():
    return jsonify(db.recent_records(min(50, request.args.get("limit", 10, type=int))))


@app.route("/api/records/<record_id>")
def api_record(record_id):
    rec = db.get_record(record_id)
    return jsonify(rec) if rec else (jsonify({"error": "找不到這筆紀錄"}), 404)


@app.route("/api/players/<name>")
def api_player(name):
    p = db.get_player(name.strip()[:12])
    # 新玩家也回 200（只是沒有紀錄），瀏覽器主控台才不會一直出現紅字錯誤
    return jsonify(p or {"name": name.strip()[:12], "games": 0, "tutorial_done": False, "new": True})


@app.route("/api/stats")
def api_stats():
    """所有場次累積：每種災情成功／失敗次數"""
    raw = db.incident_stats()
    return jsonify([{"type": k, "name": ai.TYPE_NAMES.get(k, k), **v} for k, v in raw.items()])


@app.route("/api/knowledge")
def api_knowledge():
    return jsonify(db.all_knowledge(request.args.get("tag")))


@app.route("/api/ai/status")
def api_ai_status():
    if request.args.get("refresh"):        # Ollama 晚開的話，打 /api/ai/status?refresh=1 重新偵測
        llm.reset()
    return jsonify(llm.info())


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "rooms": len(rooms), "db": db.status(), "ai": llm.info()["chain"]})


# ── 帳號：註冊／登入（帳號名＝遊戲暱稱），不登入也能用訪客身分玩 ──────────
NAME_RE = re.compile(r"^[\w\u4e00-\u9fff]{2,10}$")      # 中文、英數、底線，2～10 字


def me():
    return session.get("user")


def public_user(u):
    return {"name": u["name"], "friend_code": u["friend_code"]}


def need_login():
    return jsonify({"error": "請先登入"}), 401


@app.route("/api/me")
def api_me():
    u = db.find_user(name=me()) if me() else None
    if me() and not u:                   # 帳號不存在了（例如記憶體模式重開）
        session.pop("user", None)
    return jsonify({"user": public_user(u) if u else None})


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    name, pw = str(data.get("name", "")).strip(), str(data.get("password", ""))
    if not NAME_RE.match(name):
        return jsonify({"error": "帳號要 2～10 個字，只能用中文、英文、數字或底線"}), 400
    if len(pw) < 6:
        return jsonify({"error": "密碼至少 6 個字"}), 400
    u = db.create_user(name, generate_password_hash(pw))
    if not u:
        return jsonify({"error": "這個帳號已經有人用了"}), 409
    session.permanent = True
    session["user"] = name
    return jsonify({"user": public_user(u)})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    u = db.find_user(name=str(data.get("name", "")).strip())
    if not u or not check_password_hash(u["password_hash"], str(data.get("password", ""))):
        return jsonify({"error": "帳號或密碼不對"}), 401
    session.permanent = True
    session["user"] = u["name"]
    return jsonify({"user": public_user(u)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user", None)
    return jsonify({"ok": True})


@app.route("/api/me/records")
def api_my_records():
    if not me():
        return need_login()
    return jsonify({"stats": db.account_stats(me()), "records": db.account_records(me(), 10)})


def online_room(name):
    """好友現在在哪個房間（還沒開始、沒滿才給代碼，可以直接加入）"""
    for sid, user in list(sid_user.items()):
        if user == name:
            room = rooms.get(sid_room.get(sid))
            if room:
                joinable = room.status not in ("playing", "intro") and len(room.players) < 4
                return True, {"code": room.code if joinable else None, "status": room.status}
            return True, None
    return False, None


@app.route("/api/friends")
def api_friends():
    u = db.find_user(name=me()) if me() else None
    if not u:
        return need_login()
    out = []
    for name in u.get("friends", []):
        online, room = online_room(name)
        st = db.account_stats(name)
        out.append({"name": name, "online": online, "room": room,
                    "games": st.get("games", 0), "wins": st.get("wins", 0), "best_score": st.get("best_score", 0),
                    "last_title": st.get("last_title")})
    out.sort(key=lambda f: (not f["online"], f["name"]))
    return jsonify(out)


@app.route("/api/friends", methods=["POST"])
def api_add_friend():
    if not me():
        return need_login()
    code = str((request.get_json(silent=True) or {}).get("code", "")).strip().upper()
    other = db.find_user(friend_code=code)
    if not other:
        return jsonify({"error": "找不到這個好友碼"}), 404
    if other["name"] == me():
        return jsonify({"error": "這是你自己的好友碼喔"}), 400
    db.add_friend(me(), other["name"])
    return jsonify({"ok": True, "name": other["name"]})


@app.route("/api/friends/<name>", methods=["DELETE"])
def api_remove_friend(name):
    if not me():
        return need_login()
    db.remove_friend(me(), name)
    return jsonify({"ok": True})


@app.route("/api/friends/<name>/records")
def api_friend_records(name):
    u = db.find_user(name=me()) if me() else None
    if not u:
        return need_login()
    if name not in u.get("friends", []):
        return jsonify({"error": "你們還不是好友"}), 403
    return jsonify({"stats": db.account_stats(name), "records": db.account_records(name, 10)})


# ── 工具 ───────────────────────────────────────────────────
def current_room():
    return rooms.get(sid_room.get(request.sid))


def send(events, room):
    for event, data, to in events:
        socketio.emit(event, data, to=to or room.code)


def game_loop(room):
    """每秒 10 次：更新水位、災情倒數、按住的工作 → 廣播全房狀態"""
    last = time.time()
    while room.status == "playing":
        socketio.sleep(0.1)
        now = time.time()
        with room.lock:
            events = room.tick(now - last)
            spawn_now = room.due_for_spawn()
            if spawn_now:
                room.director_busy = True
            state = room.snapshot()
        last = now
        send(events, room)
        socketio.emit("state_sync", state, to=room.code)
        if spawn_now:
            socketio.start_background_task(director, room)
        if room.status == "finished" and room.mode == "tutorial":
            for p in list(room.players.values()):        # 走完教學 → 記進資料庫（依暱稱）
                db.mark_tutorial(p["name"])
            room.status = "waiting"                       # 教學結束回到房間
            socketio.emit("room_update", room.lobby_info(), to=room.code)
        elif room.status == "finished" and room.result:   # 全員離線時沒有結果，不寫報告
            socketio.emit("room_update", room.lobby_info(), to=room.code)
            socketio.start_background_task(write_report, room, room.result)


def director(room):
    """AI 災難導演：挑下一個災情。AI 沒回應就用規則版。"""
    with room.lock:
        cands = room.candidates()
        random.shuffle(cands)
        state = {
            "story": (room.scenario or {}).get("story", ""),
            "weights": (room.scenario or {}).get("weights", {}),
            "time_left": round(GAME_TIME - room.elapsed), "phase": room.phase_label(), "hearts": room.hearts,
            "disaster": room.D["name"], "disaster_key": room.disaster, "meter": room.D["meter"],
            "chapter": (f"{room.chapter['title']}：{room.chapter['goal_text']}（還差 {room.chapter['need'] - room.chapter['done']} 件）"
                        if room.chapter and room.chapter["status"] == "active" else "無"),
            "level": round(room.level), "fixed": sum(h["result"] == "fixed" for h in room.history),
            "failed": sum(h["result"] == "failed" for h in room.history),
            "active": "、".join(room.inc_name(i["type"]) for i in room.incidents) or "無",
        }
    picked = ai.direct(state, cands)
    with room.lock:
        room.director_busy = False
        if room.status != "playing" or len(room.incidents) >= room.max_incidents():
            return
        if picked and picked[0] in room.candidates():
            choice, line, by = picked
        else:
            choice, line, by = room.rule_pick(), None, "rule"
        if not choice:
            room.schedule_next()
            return
        ev = room.spawn(choice["type"], choice["x"], choice["y"], line, picked_by=by)
        room.schedule_next()
    send([ev], room)


def write_report(room, result):
    """先把這局存進 MongoDB（AI 慢或失敗也不會掉資料），再生成 AI 講評補上"""
    with room.lock:
        events = [dict(h) for h in room.history]
    record_id = db.save_record(room.code, result, events)
    db.update_players(result)
    db.room_update(getattr(room, "db_id", None), status="finished", record_id=record_id)
    socketio.emit("record_saved", {"record_id": record_id}, to=room.code)
    rep = ai.make_report(result)
    db.update_report(record_id, rep["report"], rep["by"], rep["tips"])
    socketio.emit("report_ready", {**rep, "record_id": record_id}, to=room.code)


SCENARIO_WAIT = 12      # 開始時劇情還沒寫好，最多等幾秒（等不到就用內建劇本）


def prefetch_scenario(room):
    """在背景先請 AI 寫好下一局的劇情（建立房間、每局結束時呼叫），按出發時就不用等"""
    if getattr(room, "prefetching", False) or getattr(room, "prefetched", None):
        return
    room.prefetching = True
    try:
        # 每局隨機一種災難，盡量不和上一局一樣
        room.prefetched = ai.make_scenario(exclude=getattr(room, "last_disaster", None))
    finally:
        room.prefetching = False


def start_round(room):
    """開場：可愛轉場（等劇情）→ 大家看完劇情按「出發」（最多等 45 秒）→ 開始"""
    socketio.emit("intro_loading", {}, to=room.code)
    if not getattr(room, "prefetched", None) and not getattr(room, "prefetching", False):
        socketio.start_background_task(prefetch_scenario, room)
    waited = 0.0
    while waited < SCENARIO_WAIT and not getattr(room, "prefetched", None):
        socketio.sleep(0.3)
        waited += 0.3
    socketio.sleep(max(0, 1.8 - waited))          # 轉場至少播 1.8 秒，不會一閃而過
    scenario = getattr(room, "prefetched", None) or ai.rule_scenario(exclude=getattr(room, "last_disaster", None))
    room.prefetched = None
    room.last_disaster = scenario.get("disaster", "typhoon")
    socketio.start_background_task(prefetch_scenario, room)   # 順便先寫下一局的
    room.ready = set()
    socketio.emit("intro", {"scenario": scenario, "map": room.map_info(scenario.get("disaster"))}, to=room.code)
    waited = 0.0
    while waited < 45 and room.status == "intro" and not (room.players and room.ready >= set(room.players)):
        socketio.sleep(0.3)
        waited += 0.3
    socketio.sleep(0.5)
    with room.lock:
        if room.status != "intro":
            return
        room.start(scenario)
        state = room.snapshot()
        names = [p["name"] for p in room.players.values()]
    db.room_update(getattr(room, "db_id", None), status="playing", players=names)
    socketio.emit("game_start", state, to=room.code)
    socketio.emit("room_update", room.lobby_info(), to=room.code)
    game_loop(room)


# ── WebSocket 事件 ─────────────────────────────────────────
@socketio.on("create_room")
def on_create(data):
    name = player_name(data)
    if name is None:
        return
    code = new_code()
    while code in rooms:
        code = new_code()
    rooms[code] = Room(code, request.sid)
    _enter(code, name)
    host = rooms[code].players.get(request.sid, {}).get("name", "")
    rooms[code].db_id = db.room_open(code, host)
    socketio.start_background_task(prefetch_scenario, rooms[code])


@socketio.on("join_room")
def on_join(data):
    code = str(data.get("code", "")).upper().strip()
    room = rooms.get(code)
    if not room:
        return emit("error_msg", {"message": "找不到這個房間"})
    if room.status in ("playing", "intro"):
        return emit("error_msg", {"message": "遊戲進行中，請等下一局"})
    if len(room.players) >= 4:
        return emit("error_msg", {"message": "房間已滿（最多 4 人）"})
    name = player_name(data)
    if name is not None:
        _enter(code, name)


def player_name(data):
    """登入的人一律用帳號名；訪客如果打了別人已註冊的名字，請他換一個或登入"""
    if sid_user.get(request.sid):
        return sid_user[request.sid]
    name = str((data or {}).get("name", "")).strip()[:10]
    if name and db.find_user(name=name):
        emit("error_msg", {"message": f"「{name}」已經是註冊帳號了，請登入或換一個暱稱"})
        return None
    return name


def _enter(code, name):
    room = rooms[code]
    with room.lock:
        room.add_player(request.sid, name, account=sid_user.get(request.sid))
    sid_room[request.sid] = code
    join_room(code)
    emit("joined", {"you": request.sid, "code": code, "map": room.map_info()})
    socketio.emit("room_update", room.lobby_info(), to=code)


@socketio.on("start_game")
def on_start():
    room = current_room()
    if not room or room.host != request.sid or room.status in ("playing", "intro"):
        return
    room.status = "intro"
    socketio.emit("room_update", room.lobby_info(), to=room.code)
    socketio.start_background_task(start_round, room)


@socketio.on("start_tutorial")
def on_tutorial():
    room = current_room()
    if not room or room.host != request.sid or room.status in ("playing", "intro"):
        return
    with room.lock:
        room.start(None, mode="tutorial")
        state = room.snapshot()
    socketio.emit("intro_map", room.map_info(), to=room.code)
    socketio.emit("game_start", state, to=room.code)
    socketio.emit("room_update", room.lobby_info(), to=room.code)
    socketio.start_background_task(game_loop, room)


@socketio.on("skip_tutorial")
def on_skip():
    room = current_room()
    if room and room.mode == "tutorial" and room.status == "playing":
        with room.lock:
            room.status = "waiting"          # 遊戲迴圈會自己停下
        socketio.emit("tutorial_done", {"completed": False}, to=room.code)
        socketio.emit("room_update", room.lobby_info(), to=room.code)


@socketio.on("intro_ready")
def on_intro_ready():
    room = current_room()
    if room and room.status == "intro":
        room.ready = getattr(room, "ready", set()) | {request.sid}
        socketio.emit("intro_status", {"ready": len(room.ready & set(room.players)), "total": len(room.players)},
                      to=room.code)


@socketio.on("player_move")
def on_move(data):
    room = current_room()
    if room:
        with room.lock:
            room.move(request.sid, data.get("x", 0), data.get("y", 0), data.get("d", 0), data.get("m", False))


@socketio.on("act")
def on_act():
    room = current_room()
    if room:
        with room.lock:
            events = room.act(request.sid)
        send(events, room)


@socketio.on("act_end")
def on_act_end():
    room = current_room()
    if room:
        with room.lock:
            room.act_end(request.sid)


@socketio.on("ping_marker")
def on_ping(data):
    room = current_room()
    if room:
        room.tut_flags.add("ping")
        socketio.emit("ping_marker", {"x": data.get("x"), "y": data.get("y")}, to=room.code)


@socketio.on("leave_room")
def on_leave():
    _leave(request.sid)
    emit("left")


@socketio.on("connect")
def on_connect(*args):
    """連線時記下這條連線是誰（登入後前端會重新連線一次）"""
    if session.get("user"):
        sid_user[request.sid] = session["user"]


@socketio.on("disconnect")
def on_disconnect(*args):
    _leave(request.sid)
    sid_user.pop(request.sid, None)


def _leave(sid):
    code = sid_room.pop(sid, None)
    room = rooms.get(code)
    if not room:
        return
    with room.lock:
        room.remove_player(sid)
    leave_room(code, sid=sid)
    if not room.players:
        room.status = "finished"
        rooms.pop(code, None)
        db.room_update(getattr(room, "db_id", None), status="closed")
    else:
        socketio.emit("room_update", room.lobby_info(), to=code)



if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"災變大作戰啟動：http://localhost:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
