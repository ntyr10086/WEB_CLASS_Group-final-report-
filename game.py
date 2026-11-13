"""災變大作戰：災難救援隊 — 伺服器端遊戲邏輯（伺服器是權威）

主線像 Overcooked：畫面上方出現「災情單」→ 去拿工具／加工物資 → 到現場治災。
世界座標以像素計，地圖 384 x 256（24 x 16 格，每格 16px），前端放大 3 倍顯示。
"""
import math
import os
import random
import string
import threading
import time

import disasters

W, H, T = 384, 256, 16
WALL_BOTTOM = 64                  # 河堤下緣；水位 0% 時的水線
GAME_TIME = int(os.getenv("GAME_TIME", 180))
REACH = 22                        # 互動距離
PLAYER_R = 5                      # 角色碰撞半徑
START_HEARTS = 5

PLAYER_SKINS = ["NinjaBlue", "NinjaRed", "NinjaGreen", "NinjaYellow"]
RESIDENT_SKINS = ["OldWoman", "OldMan", "Child", "Woman", "Villager"]

ITEMS = {k: v[0] for k, v in disasters.ITEM_INFO.items()}   # 道具名稱（三種災難的道具都在 disasters.py）

# ── 地圖（前端也用這份資料畫畫面，兩邊不會對不上）────────────────
HOUSES = [{"id": f"h{i}", "x": x, "y": 88, "w": 64, "h": 48, "style": i}
          for i, x in enumerate((16, 112, 208, 304))]
STATIONS = [
    # kind, id, 中心 x, y, 碰撞寬, 高, 給什麼
    {"kind": "shelter", "id": "shelter", "x": 32, "y": 214, "w": 48, "h": 36},
    {"kind": "crate", "id": "c_rake", "x": 88, "y": 212, "w": 16, "h": 16, "item": "rake"},
    {"kind": "crate", "id": "c_gloves", "x": 108, "y": 212, "w": 16, "h": 16, "item": "gloves"},
    {"kind": "crate", "id": "c_ring", "x": 128, "y": 212, "w": 16, "h": 16, "item": "ring"},
    {"kind": "crate", "id": "c_axe", "x": 148, "y": 212, "w": 16, "h": 16, "item": "axe"},
    {"kind": "crate", "id": "c_bag", "x": 180, "y": 212, "w": 16, "h": 16, "item": "bag"},
    {"kind": "sand", "id": "sand", "x": 212, "y": 214, "w": 32, "h": 20},
    {"kind": "bench", "id": "bench", "x": 260, "y": 212, "w": 32, "h": 14},
    {"kind": "crate", "id": "c_motor", "x": 304, "y": 212, "w": 16, "h": 16, "item": "motor"},
    {"kind": "crate", "id": "c_hose", "x": 324, "y": 212, "w": 16, "h": 16, "item": "hose"},
    {"kind": "truck", "id": "truck", "x": 360, "y": 210, "w": 32, "h": 22},
]
SHELTER_DOOR = (32, 240)
DECOR_TREES = [(8, 76), (376, 76), (8, 182), (376, 182)]   # 最下排不放樹（會被畫面下緣切掉、擋住招牌）

# 災情可以出現的位置
SPOTS = {
    "breach": [(x, 56) for x in (40, 120, 184, 248, 344)],
    "drain": [(40, 168), (136, 168), (232, 168), (328, 168)],
    "electric": [(h["x"] + 56, 144) for h in HOUSES[:3]],
    "house_flood": [(h["x"] + 32, 140) for h in HOUSES],
    "trapped": [(h["x"] + 12, 142) for h in HOUSES],
    "tree": [(96, 112), (192, 112), (288, 112), (88, 168), (280, 168)],
}

INCIDENTS = {
    # name, 時限, 需要什麼, 怎麼治, 獎勵
    "breach": {"name": "堤防破洞", "time": 42, "need": "sandbag", "how": "tap", "count": 3, "reward": 30},
    "drain": {"name": "排水溝堵塞", "time": 36, "need": "rake", "how": "hold", "work": 2.0, "reward": 20},
    "electric": {"name": "電箱冒火花", "time": 32, "need": "gloves", "how": "hold", "work": 1.6, "reward": 25},
    "house_flood": {"name": "民宅淹水", "time": 48, "need": "pump", "how": "tap", "count": 1, "reward": 35},
    "trapped": {"name": "居民受困", "time": 50, "need": "ring", "how": "tap", "count": 1, "reward": 40},
    "tree": {"name": "大樹倒下", "time": 40, "need": "axe", "how": "hold", "work": 2.0, "reward": 20},
}
TREE_SIZE = {(96, 112): (32, 14), (192, 112): (32, 14), (288, 112): (32, 14), (88, 168): (14, 30), (280, 168): (14, 30)}

FALLBACK_LINES = disasters.DISASTERS["typhoon"]["lines"]   # 各災難的台詞在 disasters.py


# ── 新手教學：一步一步帶過六種災情（條件達成就進下一步）──────────
CRATE = {s["item"]: (s["x"], s["y"]) for s in STATIONS if s["kind"] == "crate"}
TUTORIAL = [
    # speaker（誰在說話）, text, target（箭頭）, done（完成條件）, spawn（這一步出現的災情）
    {"speaker": "鎮長", "text": "新隊員你好！氣象局說今年的颱風會特別兇，我們得趕快練習。先用 WASD 走到發亮的「空袋」箱子", "target": CRATE["bag"], "done": "near"},
    {"speaker": "鎮長", "text": "這些物資都是鎮民平時一起準備的。按一下空白鍵，拿起空袋", "target": CRATE["bag"], "done": "hold:bag"},
    {"speaker": "阿嬤", "text": "以前大家都等颱風來了才搶沙包，根本搶不到！拿著空袋走到沙堆", "target": (212, 214), "done": "near"},
    {"speaker": "阿嬤", "text": "「按住」空白鍵，等頭上的進度條跑滿，空袋就會變成沙包", "target": (212, 214), "done": "hold:sandbag"},
    {"speaker": "小宇", "text": "上面跳出「災情單」了！河堤破了一個洞，快拿沙包過去！", "spawn": ("breach", 120, 56), "target": "incident", "done": "near:incident"},
    {"speaker": "小宇", "text": "按一下空白鍵，把沙包塞進破洞！", "target": "incident", "done": "fixed"},
    {"speaker": "村民", "text": "糟了，排水溝被落葉塞住，水退不掉！災情單上畫的是耙子，去拿「耙子」", "spawn": ("drain", 136, 168), "target": CRATE["rake"], "done": "near"},
    {"speaker": "村民", "text": "按一下空白鍵，拿起耙子", "target": CRATE["rake"], "done": "hold:rake"},
    {"speaker": "村民", "text": "拿著耙子走到積水的排水溝", "target": "incident", "done": "near:incident"},
    {"speaker": "鎮長", "text": "按住空白鍵清淤，等進度條跑滿。現實中颱風前先清水溝，就能少淹很多", "target": "incident", "done": "fixed"},
    {"speaker": "阿嬤", "text": "撈出來的淤泥可不能亂丟喔。走過去按空白鍵撿起來", "target": "trash", "done": "hold:trash"},
    {"speaker": "阿嬤", "text": "送到右下角的垃圾車，按空白鍵倒進去。不然下次又會塞住", "target": (360, 210), "done": "flag:trash"},
    {"speaker": "小宇", "text": "電箱在冒火花！好可怕！", "spawn": ("electric", 168, 144), "target": CRATE["gloves"], "done": "near"},
    {"speaker": "鎮長", "text": "千萬別空手碰，會被電！按空白鍵戴上「絕緣手套」", "target": CRATE["gloves"], "done": "hold:gloves"},
    {"speaker": "鎮長", "text": "戴著手套，走到冒火花的電箱旁", "target": "incident", "done": "near:incident"},
    {"speaker": "鎮長", "text": "按住空白鍵斷電。真實世界也一樣：淹水前先關總電源", "target": "incident", "done": "fixed"},
    {"speaker": "阿嬤", "text": "我家淹水了！要做一台抽水機。先去「馬達」箱子，按空白鍵拿馬達", "spawn": ("house_flood", 48, 140), "target": CRATE["motor"], "done": "hold:motor"},
    {"speaker": "阿嬤", "text": "把馬達拿到工作台，按空白鍵放上去", "target": (260, 212), "done": "bench:motor"},
    {"speaker": "阿嬤", "text": "再去「水管」箱子，按空白鍵拿水管", "target": CRATE["hose"], "done": "hold:hose"},
    {"speaker": "阿嬤", "text": "水管也放上工作台", "target": (260, 212), "done": "bench:2"},
    {"speaker": "鎮長", "text": "空手站在工作台旁，按住空白鍵組裝。這種事一個人做很慢，正式遊戲要分工喔", "target": (260, 212), "done": "bench:pump"},
    {"speaker": "鎮長", "text": "組好了！按一下空白鍵拿起抽水機", "target": (260, 212), "done": "hold:pump"},
    {"speaker": "阿嬤", "text": "快送到我家門口，按空白鍵放下！", "target": "incident", "done": "pumping"},
    {"speaker": "阿嬤", "text": "抽水機會自己抽，等藍色進度條跑完就好。謝謝你呀，年輕人", "target": "incident", "done": "fixed"},
    {"speaker": "小宇", "text": "有人被困在家裡出不來！去「救生圈」箱子拿救生圈", "spawn": ("trapped", 220, 142), "target": CRATE["ring"], "done": "hold:ring"},
    {"speaker": "小宇", "text": "走到受困的居民旁邊，按空白鍵把救生圈交給他", "target": "incident", "done": "following"},
    {"speaker": "鎮長", "text": "他會跟著你。帶他走到左下角的避難所。受困時待在高處等救援，不要自己涉水", "target": (70, 214), "done": "fixed"},
    {"speaker": "村民", "text": "強風把路樹吹倒了，擋住路！去拿「斧頭」", "spawn": ("tree", 192, 112), "target": CRATE["axe"], "done": "hold:axe"},
    {"speaker": "村民", "text": "拿著斧頭走到倒下的大樹旁", "target": "incident", "done": "near:incident"},
    {"speaker": "村民", "text": "按住空白鍵把樹劈開！颱風天記得別站在樹和招牌下面", "target": "incident", "done": "fixed"},
    {"speaker": "小宇", "text": "最後一招！按 Q 會在腳下放求救標記，叫隊友過來幫忙。試試看！", "done": "flag:ping"},
    {"speaker": "鎮長", "text": "訓練完成！記住：颱風會越來越兇，但平時準備好、大家分工，小鎮就撐得住！", "done": "end"},
]


# 每種災情對應的真實防災知識（遊戲中第一次解除該災情時顯示一次，結算時整理成清單）
KNOWLEDGE = disasters.DISASTERS["typhoon"]["knowledge"]   # 各災難的防災知識在 disasters.py


# 遊戲中的劇情片段：把「氣候變遷、平時準備、分工合作」放進遊戲過程
CLIMATE_NEWS = disasters.DISASTERS["typhoon"]["news"]   # 氣象主播的插播（各災難各一組）
BEATS = {
    "first_crate": [("阿嬤", "這些工具是大家平時一起準備的，今天終於派上用場了！"),
                    ("鎮長", "倉庫裡的東西都是去年就備好的，平時準備就是為了今晚！")],
    "teamwork": [("鎮長", "兩個人一起做就是快！這就是鄰里互助的力量。"),
                 ("小宇", "哇，兩個人一起弄超快的！")],
    "relay": [("阿嬤", "東西傳給隊友真聰明，一個人跑不完的。"),
              ("村民", "接力成功！大家分工就是不一樣。")],
    "rescue": [("小宇", "謝謝你們救了我的鄰居！大家互相照顧真好。"),
               ("阿嬤", "人平安最重要，東西壞了還能再買。")],
    "low_hearts": [("鎮長", "撐住！一個人顧不了全鎮，快分頭行動！"),
                   ("阿嬤", "別慌，一個人負責一區，大家一定撐得過去。")],
}
BEAT_GAP = 10          # 兩段劇情之間至少隔幾秒，避免一直講話


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def new_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))


class Room:
    def __init__(self, code, host_sid):
        self.code = code
        self.host = host_sid
        self.status = "waiting"            # waiting → intro → playing → finished
        self.players = {}
        self.lock = threading.Lock()
        self.scenario = None
        self.disaster = "typhoon"
        self.reset_game()

    # ── 房間 ─────────────────────────────────────────────
    def add_player(self, sid, name, account=None):
        used = {p["skin"] for p in self.players.values()}
        skin = next(s for s in PLAYER_SKINS if s not in used) if len(used) < 4 else PLAYER_SKINS[0]
        self.players[sid] = {"id": sid, "name": name[:10] or "玩家", "skin": skin,
                             "account": account}          # 登入的帳號（訪客是 None）
        self._reset_player(self.players[sid], len(self.players) - 1)

    def _reset_player(self, p, i):
        p.update({"x": 172 + 18 * i, "y": 186, "dir": 0, "moving": False, "hold": None,
                  "work": None, "stun_until": 0, "stats": {"fixed": 0, "items": 0}})

    def remove_player(self, sid):
        self.players.pop(sid, None)
        for r in self.residents:
            if r["leader"] == sid:
                r["leader"] = None
        if self.host == sid and self.players:
            self.host = next(iter(self.players))

    def lobby_info(self):
        return {"code": self.code, "host": self.host, "status": self.status,
                "players": [{"id": p["id"], "name": p["name"], "skin": p["skin"]} for p in self.players.values()]}

    def map_info(self, disaster=None):
        d = disasters.get(disaster or self.disaster)
        return {"w": W, "h": H, "houses": HOUSES, "stations": STATIONS, "trees": DECOR_TREES,
                "drains": SPOTS["drain"], "boxes": SPOTS["electric"], "wall_bottom": WALL_BOTTOM,
                "shelter_door": SHELTER_DOOR, "items": {**ITEMS, **d["items"]},
                "incident_names": dict(d["incidents"]),
                "disaster": {"key": disaster or self.disaster, "name": d["name"], "event": d["event"],
                             "meter": d["meter"], "phases": d["phases"], "look": d["look"]},
                "kit": self.kit_info(disaster or self.disaster)}

    def kit_info(self, key):
        k = disasters.kit(key)
        crates = [s for s in STATIONS if s["kind"] == "crate"]
        return {"crates": {s["id"]: k["crates"][i] for i, s in enumerate(crates)},
                "process": k["process"], "bench": k["bench"], "truck": k["truck"],
                "recipes": {t: {kk: r.get(kk) for kk in ("how", "need", "count", "team", "badge", "steps", "card")}
                            for t, r in k["recipes"].items()},
                "item_files": {i: v[1] for i, v in disasters.ITEM_INFO.items()}}

    # ── 這局的災難 ─────────────────────────────────────────
    @property
    def D(self):
        return disasters.get(self.disaster)

    def inc_name(self, kind):
        return self.D["incidents"][kind]

    @property
    def K(self):
        return disasters.kit(self.disaster)

    def R(self, kind):
        """這局災難裡，這種災情要怎麼處理"""
        return self.K["recipes"][kind]

    def crate_item(self, st):
        crates = [s for s in STATIONS if s["kind"] == "crate"]
        return self.K["crates"][crates.index(st)]

    def team_need(self, r):
        return min(r.get("team", 1), max(1, len(self.players)))

    def phase_label(self):
        return self.D["phases"][self.phase()]

    # ── 開局 ─────────────────────────────────────────────
    def reset_game(self):
        self.elapsed = 0.0
        self.level = 0.0
        self.hearts = START_HEARTS
        self.coins = 0
        self.incidents = []
        self.ground = []                    # 地上的物品（可以丟給隊友）
        self.residents = []
        self.bench = {"parts": [], "progress": 0.0}
        self.seq = 0
        self.next_spawn = 1.5
        self.director_busy = False
        self.history = []                   # 這局發生過的災情（給 AI 檢討用）
        self.result = None
        self.tips_shown = set()              # 這局已經顯示過的防災知識
        self.beats_done = set()              # 這局已經講過的劇情片段
        self.last_beat = -BEAT_GAP
        self.news_times = [GAME_TIME * k for k in (0.12, 0.45, 0.78)]
        self.chapter = None                  # 現在這一章的劇情任務
        self.chapters = []                   # 這局每一章的結果（結算時講故事用）
        self.mode = "normal"
        self.tut_step = -1
        self.tut_flags = set()
        self.tut_end_at = None

    def start(self, scenario, mode="normal"):
        self.reset_game()
        self.scenario = scenario
        self.mode = mode
        self.disaster = (scenario or {}).get("disaster", "typhoon") if mode == "normal" else "typhoon"
        for i, p in enumerate(self.players.values()):
            self._reset_player(p, i)
        self.status = "playing"
        if mode == "tutorial":
            self.tut_advance()

    # ── 新手教學 ─────────────────────────────────────────
    def tut_advance(self):
        self.tut_step += 1
        self.tut_flags.discard("fixed")
        step = TUTORIAL[self.tut_step]
        out = []
        if "spawn" in step:
            kind, x, y = step["spawn"]
            out.append(self.spawn(kind, x, y))
            if kind == "breach":
                self.incidents[-1]["need_count"] = 1        # 教學只要一包
        if step["done"] == "end":
            self.tut_end_at = self.elapsed + 4
        return out

    def tut_target(self):
        step = TUTORIAL[self.tut_step]
        t = step.get("target")
        if t == "trash":
            g = next((g for g in self.ground if g["item"] == "trash"), None)
            return (g["x"], g["y"]) if g else None
        if t == "incident":
            if not self.incidents:
                return None
            inc = self.incidents[-1]
            if inc["type"] == "trapped":                       # 受困：指著居民
                r = next((r for r in self.residents if r["id"] == inc.get("resident")), None)
                if r:
                    return (r["x"], r["y"])
            return (inc["x"], inc["y"])
        return t

    def tut_check(self):
        if self.tut_step < 0 or self.tut_step >= len(TUTORIAL):
            return []
        done = TUTORIAL[self.tut_step]["done"]
        ps = list(self.players.values())
        ok = False
        if done == "near":
            tx, ty = TUTORIAL[self.tut_step]["target"]
            ok = any(dist(p["x"], p["y"], tx, ty) < 30 for p in ps)
        elif done == "near:incident":
            t = self.tut_target()
            ok = bool(t) and any(dist(p["x"], p["y"], t[0], t[1]) < 30 for p in ps)
        elif done == "flag:ping":
            ok = "ping" in self.tut_flags
        elif done == "bench:motor":
            ok = "motor" in self.bench["parts"]
        elif done == "pumping":
            ok = any(i["state"] == "pumping" for i in self.incidents) or "fixed" in self.tut_flags
        elif done.startswith("hold:"):
            ok = any(p["hold"] == done[5:] for p in ps)
        elif done == "fixed":
            ok = "fixed" in self.tut_flags
        elif done == "flag:trash":
            ok = "trash" in self.tut_flags
        elif done == "bench:2":
            ok = set(self.bench["parts"]) >= {"motor", "hose"}
        elif done == "bench:pump":
            ok = "pump" in self.bench["parts"] or any(p["hold"] == "pump" for p in ps)
        elif done == "following":
            ok = any(r["state"] == "following" for r in self.residents)
        elif done == "end":
            if self.elapsed >= self.tut_end_at:
                self.status = "finished"
                return [("tutorial_done", {"completed": True}, None)]
        if ok:
            return [("fx", {"type": "step", "x": 0, "y": 0}, None)] + self.tut_advance()
        return []

    def tutorial_info(self):
        if self.mode != "tutorial" or not (0 <= self.tut_step < len(TUTORIAL)):
            return None
        step = TUTORIAL[self.tut_step]
        return {"step": self.tut_step + 1, "total": len(TUTORIAL), "text": step["text"],
                "speaker": step.get("speaker", "鎮長"), "target": self.tut_target()}

    def _id(self, prefix):
        self.seq += 1
        return f"{prefix}{self.seq}"

    # ── 天氣與水位 ─────────────────────────────────────────
    def phase(self):
        third = GAME_TIME / 3
        return "小雨" if self.elapsed < third else "颱風眼" if self.elapsed < third * 2 else "暴雨"

    def water_y(self):
        return WALL_BOTTOM + self.level / 100 * (H - WALL_BOTTOM)

    def rise_rate(self):
        base = {"小雨": 0.10, "颱風眼": 0.03, "暴雨": 0.20}[self.phase()]
        active = [i for i in self.incidents if i["state"] == "active"]
        return base + 0.09 * sum(i["type"] == "breach" for i in active) + 0.05 * sum(i["type"] == "drain" for i in active)

    def max_incidents(self):
        return min(5, 2 + len(self.players))

    def spawn_interval(self):
        return max(5.5, 10 - self.elapsed / 30)

    # ── 災情候選與產生 ───────────────────────────────────
    def candidates(self):
        """目前可以出現的 (類型, 位置)"""
        used = {(i["x"], i["y"]) for i in self.incidents}
        houses_busy = {i["house"] for i in self.incidents if i.get("house")}
        out = []
        for kind, spots in SPOTS.items():
            for (x, y) in spots:
                if (x, y) in used:
                    continue
                house = self._house_at(x, y) if kind in ("house_flood", "trapped", "electric") else None
                if house and house in houses_busy:
                    continue
                if kind == "tree" and any(dist(x, y, p["x"], p["y"]) < 20 for p in self.players.values()):
                    continue
                out.append({"type": kind, "x": x, "y": y})
        return out

    def _house_at(self, x, y):
        for h in HOUSES:
            if h["x"] - 4 <= x <= h["x"] + h["w"] + 4:
                return h["id"]
        return None

    def spawn(self, kind, x, y, line=None, picked_by="rule"):
        """picked_by：這個災情是誰挑的（"ai" 災難導演／"rule" 規則版），會記進歷史紀錄"""
        info, r = INCIDENTS[kind], self.R(kind)
        t = r.get("time", info["time"])
        inc = {"id": self._id("i"), "type": kind, "x": x, "y": y, "state": "active",
               "timer": t, "max_timer": t, "progress": 0.0, "count": 0, "given": [],
               "need": r["need"], "need_count": r.get("count", 1),
               "line": line or random.choice(self.D["lines"][kind]),
               "house": self._house_at(x, y) if kind in ("house_flood", "trapped", "electric") else None}
        if kind == "tree":
            inc["w"], inc["h"] = TREE_SIZE[(x, y)]
        if r["how"] in ("escort", "multi") or kind == "trapped":     # 有居民要帶去避難所／被困在裡面
            res = {"id": self._id("r"), "skin": random.choice(RESIDENT_SKINS), "x": float(x), "y": float(y),
                   "state": "waiting", "leader": None, "incident": inc["id"]}
            self.residents.append(res)
            inc["resident"] = res["id"]
        self.incidents.append(inc)
        self.history.append({"kind": "incident", "type": kind, "result": "active", "t": round(self.elapsed),
                             "picked_by": picked_by})          # kind 給 db.incident_stats() 統計用
        inc["picked_by"] = picked_by
        inc["hist"] = len(self.history) - 1
        return ("incident_new", {"id": inc["id"], "type": kind, "name": self.inc_name(kind), "x": x, "y": y,
                                 "line": inc["line"]}, None)

    def rule_pick(self):
        """沒有 AI 時的災難導演：依劇本權重挑，並偏向大家忽略的區域"""
        cands = self.candidates()
        if not cands:
            return None
        weights = (self.scenario or {}).get("weights", {})
        def score(c):
            w = weights.get(c["type"], 1.0)
            if self.chapter and self.chapter["status"] == "active" and c["type"] in self.chapter["goal"]:
                w *= 2.2                     # 偏向這一章劇情任務需要的災情
            if self.hearts <= 2 and c["type"] in ("breach", "house_flood"):
                w *= 0.5                     # 快撐不住時放水
            return w * random.uniform(0.6, 1.4)
        return max(cands, key=score)

    # ── 碰撞 ───────────────────────────────────────────────
    def solid_rects(self):
        rects = [(h["x"], h["y"], h["w"], h["h"]) for h in HOUSES]
        rects += [(s["x"] - s["w"] / 2, s["y"] - s["h"] / 2, s["w"], s["h"]) for s in STATIONS]
        rects += [(x - 6, y - 4, 12, 8) for x, y in DECOR_TREES]
        rects += [(x - 5, y - 6, 10, 10) for x, y in SPOTS["electric"]]      # 電箱一直都在
        for i in self.incidents:
            if i["type"] == "tree" and i["state"] == "active":
                rects.append((i["x"] - i["w"] / 2, i["y"] - i["h"] / 2, i["w"], i["h"]))
        return rects

    def blocked(self, x, y, pad=PLAYER_R):
        if y < WALL_BOTTOM + pad or x < pad or x > W - pad or y > H - pad:
            return True
        return any(rx - pad < x < rx + rw + pad and ry - pad < y < ry + rh + pad
                   for rx, ry, rw, rh in self.solid_rects())

    def step_toward(self, r, tx, ty, speed, dt, gap):
        d = dist(r["x"], r["y"], tx, ty)
        if d <= gap:
            return
        s = min(speed * dt, d - gap)
        dx, dy = (tx - r["x"]) / d * s, (ty - r["y"]) / d * s
        for mx, my in ((dx, dy), (dx, 0), (0, dy)):
            if not self.blocked(r["x"] + mx, r["y"] + my, 4):
                r["x"] += mx; r["y"] += my
                return

    # ── 每個 tick ─────────────────────────────────────────
    def tick(self, dt):
        out = []
        if self.status != "playing":
            return out
        self.peak_level = max(getattr(self, "peak_level", 0), self.level)
        self.peak_active = max(getattr(self, "peak_active", 0), len(self.incidents))
        prev = self.phase()
        self.elapsed += dt
        tutorial = self.mode == "tutorial"
        if not tutorial:
            self.level = min(100.0, self.level + self.rise_rate() * dt)
        if self.phase() != prev and not tutorial:
            msg = self.D["banners"][self.phase()]
            out.append(("banner", {"message": msg, "kind": "phase"}, None))

        # 災情倒數
        for inc in list(self.incidents):
            if inc["state"] == "pumping":
                inc["progress"] += dt / 6.0
                if inc["progress"] >= 1:
                    out += self.resolve(inc, None)
                continue
            if not tutorial:
                inc["timer"] -= dt          # 教學中不倒數
            if inc["timer"] <= 0:
                out += self.fail(inc)

        # 正在按住做事的玩家
        now = time.time()
        for p in self.players.values():
            w = p["work"]
            if not w:
                continue
            if dist(p["x"], p["y"], w["x"], w["y"]) > REACH + 6:
                p["work"] = None
                continue
            if w["kind"] == "fill":   # 加工站（颱風：裝沙／熱浪：裝水）
                proc = self.K["process"]
                w["progress"] += dt / proc["secs"]
                if w["progress"] >= 1:
                    p["hold"], p["work"] = proc["out"], None
                    out.append(("fx", {"type": "made", "x": p["x"], "y": p["y"] - 12, "item": proc["out"]}, None))
            elif w["kind"] == "assemble":
                bench = self.K["bench"]
                self.bench["progress"] += dt / bench["secs"]
                if self.bench["progress"] >= 1:
                    self.bench = {"parts": [bench["product"]], "progress": 0.0}
                    p["work"] = None
                    out.append(("fx", {"type": "made", "x": 260, "y": 200, "item": bench["product"]}, None))
            elif w["kind"] == "incident":
                inc = next((i for i in self.incidents if i["id"] == w["id"] and i["state"] == "active"), None)
                if not inc:
                    p["work"] = None
                    continue
                r = self.R(inc["type"])
                workers = sum(1 for q in self.players.values() if q["work"] and q["work"].get("id") == inc["id"])
                if workers < self.team_need(r):         # 要兩個人一起按住才會動
                    inc["waiting_team"] = True
                    continue
                inc["waiting_team"] = False
                inc["progress"] += dt / r["work"]       # 多人一起按會更快
                if inc["progress"] >= 1:
                    out += self.resolve(inc, p)
                    for q in self.players.values():
                        if q["work"] and q["work"].get("id") == inc["id"]:
                            q["work"] = None

            # 電箱：沒戴手套靠近會被電
        for inc in self.incidents:
            r = self.R(inc["type"])
            if not r.get("stun") or inc["state"] != "active":
                continue
            for p in self.players.values():
                if p["hold"] != r["need"] and dist(p["x"], p["y"], inc["x"], inc["y"]) < 18 and now > p["stun_until"] + 1.5:
                    p["stun_until"] = now + 1.0
                    p["work"] = None
                    out.append(("stun", {"id": p["id"], "x": p["x"], "y": p["y"]}, None))

        # 居民跟著救生圈的人走
        for r in self.residents:
            if r["state"] != "following":
                continue
            leader = self.players.get(r["leader"])
            if not leader:
                r["state"], r["leader"] = "waiting", None
                continue
            self.step_toward(r, leader["x"], leader["y"], 75, dt, 12)
            if r["x"] <= 86 and r["y"] >= 184:      # 進到避難所周圍（建築本體＋門口一帶）就算安全
                inc = next((i for i in self.incidents if i.get("resident") == r["id"]), None)
                r["state"] = "safe"
                if inc:
                    out += self.resolve(inc, leader)

        if not tutorial:
            out += self.chapter_tick()
            out += self.news_beats()
            # 兩個人以上同時處理同一個災情 → 合作的劇情
            working = [p["work"]["id"] for p in self.players.values() if p["work"] and p["work"].get("id")]
            if len(working) != len(set(working)):
                out += self.beat("teamwork")
        if tutorial:
            out += self.tut_check()
        elif self.elapsed >= GAME_TIME or self.hearts <= 0 or self.level >= 100:
            out.append(("game_over", self.finish(), None))
        return out

    # ── 劇情章節：每個天氣階段一章，角色交代一個任務 ──────────────
    def chapter_spec(self, phase=None):
        return disasters.CHAPTERS.get(self.disaster, disasters.CHAPTERS["typhoon"])[phase or self.phase()]

    def chapter_tick(self):
        out = []
        if self.elapsed < 2.5:                                   # 開局先讓大家看清楚畫面
            return out
        phase = self.phase()
        if self.chapter and self.chapter["phase"] != phase:      # 換階段：上一章沒做完就算失敗
            out += self.close_chapter(False)
        if not self.chapter or self.chapter["phase"] != phase:
            out += self.open_chapter(phase)
        return out

    def open_chapter(self, phase):
        spec = self.chapter_spec(phase)
        self.chapter = {"phase": phase, "done": 0, "status": "active", **{k: spec[k] for k in
                        ("title", "theme", "goal", "need", "goal_text", "bonus", "penalty")}, "speaker": spec["intro"][0]}
        self.last_beat = self.elapsed
        speaker, line = spec["intro"]
        out = [("chapter", self.chapter_info(), None), ("dialogue", {"speaker": speaker, "line": line}, None)]
        # 章節一開始就讓任務對應的災情出現一件，玩家馬上知道要做什麼
        if not any(i["type"] in spec["goal"] and i["state"] == "active" for i in self.incidents):
            cands = [c for c in self.candidates() if c["type"] in spec["goal"]]
            if cands and len(self.incidents) < self.max_incidents() + 1:
                c = random.choice(cands)
                out.append(self.spawn(c["type"], c["x"], c["y"], picked_by="story"))
        return out

    def close_chapter(self, success, penalty=True):
        ch = self.chapter
        if not ch or ch["status"] != "active":
            return []
        spec = self.chapter_spec(ch["phase"])
        ch["status"] = "done" if success else "failed"
        speaker, line = spec["success" if success else "fail"]
        self.chapters.append({"title": ch["title"], "theme": ch["theme"], "goal_text": ch["goal_text"],
                              "status": ch["status"], "speaker": speaker, "line": line})
        self.last_beat = self.elapsed
        out = [("chapter", self.chapter_info(), None), ("dialogue", {"speaker": speaker, "line": line}, None)]
        if success:
            self.coins += ch["bonus"]
            out.append(("fx", {"type": "coin", "x": W / 2, "y": 120, "coins": ch["bonus"], "text": "劇情任務完成"}, None))
        elif penalty:
            self.level = min(100.0, self.level + ch["penalty"])  # 沒準備好的後果：之後更危險
        return out

    def chapter_info(self):
        ch = self.chapter
        if not ch or self.mode != "normal":
            return None
        return {"title": ch["title"], "theme": ch["theme"], "goal_text": ch["goal_text"], "done": min(ch["done"], ch["need"]),
                "need": ch["need"], "status": ch["status"], "speaker": ch["speaker"], "goal": ch["goal"]}

    def chapter_progress(self, kind):
        ch = self.chapter
        if not ch or ch["status"] != "active" or kind not in ch["goal"]:
            return []
        ch["done"] += 1
        if ch["done"] >= ch["need"]:
            return self.close_chapter(True)
        return [("chapter", self.chapter_info(), None)]

    # ── 劇情片段 ───────────────────────────────────────────
    def beat(self, key, line=None, force=False):
        """講一段劇情（每種只講一次，且和上一段至少隔 BEAT_GAP 秒）"""
        if self.mode != "normal" or key in self.beats_done:
            return []
        if not force and self.elapsed - self.last_beat < BEAT_GAP:
            return []
        self.beats_done.add(key)
        self.last_beat = self.elapsed
        speaker, text = line or random.choice(BEATS[key])
        return [("dialogue", {"speaker": speaker, "line": text}, None)]

    def news_beats(self):
        out = []
        for i, t in enumerate(self.news_times):
            if self.elapsed >= t and f"news{i}" not in self.beats_done:
                pool = [n for n in ((self.scenario or {}).get("news") or []) if isinstance(n, str)] or self.D["news"]
                used = {b for b in self.beats_done if b.startswith("newsline:")}
                options = [n for n in pool if f"newsline:{n}" not in used] or pool
                line = random.choice(options)
                got = self.beat(f"news{i}", ("氣象主播", line))
                if got:
                    self.beats_done.add(f"newsline:{line}")
                out += got
        if self.hearts <= 2:
            out += self.beat("low_hearts")
        if self.level >= 70:
            out += self.beat("high_water", random.choice(self.D["high"]))
        return out

    def due_for_spawn(self):
        return (self.status == "playing" and self.mode == "normal" and self.elapsed >= self.next_spawn and not self.director_busy
                and len(self.incidents) < self.max_incidents())

    def schedule_next(self):
        self.next_spawn = self.elapsed + self.spawn_interval()

    # ── 成功／失敗 ─────────────────────────────────────────
    def resolve(self, inc, p):
        if inc not in self.incidents:
            return []
        self.incidents.remove(inc)
        info, r = INCIDENTS[inc["type"]], self.R(inc["type"])
        bonus = int(max(0, inc["timer"]) // 2)
        gain = info["reward"] + bonus
        self.coins += gain
        self.history[inc["hist"]].update({"result": "fixed", "left": round(max(0, inc["timer"]), 1),
                                          "by": p["name"] if p else None, "end": round(self.elapsed),
                                          "phase": self.phase_label(), "phase_key": self.phase()})
        self.tut_flags.add("fixed")
        if r["how"] == "hold" and r["need"]:     # 用完的工具自動歸還（從手上消失）
            for q in self.players.values():
                if q["hold"] == r["need"] and (q is p or (q["work"] and q["work"].get("id") == inc["id"])):
                    q["hold"], q["work"] = None, None
        if p:
            p["stats"]["fixed"] += 1
        tip = None
        if self.mode == "normal" and inc["type"] not in self.tips_shown:   # 每種災情第一次解除時附上一次知識（教學本身已經有講）
            self.tips_shown.add(inc["type"])
            tip = {"name": self.inc_name(inc["type"]), "text": self.D["knowledge"][inc["type"]]}
        out = [("fx", {"type": "fixed", "x": inc["x"], "y": inc["y"], "coins": gain, "tip": tip,
                       "text": f"{self.inc_name(inc['type'])} 解除！", "returned": r["need"] if r["how"] == "hold" else None}, None)]
        if r.get("yield"):                         # 清出來的東西（淤泥、枯枝、碎石）要送去清運
            gx, gy = inc["x"] + 10, inc["y"] + 8
            if self.blocked(gx, gy, 2):
                gx, gy = inc["x"], inc["y"] + 14
            self.ground.append({"id": self._id("g"), "item": r["yield"], "x": gx, "y": gy})
        if inc.get("resident"):
            self.residents = [x for x in self.residents if x["id"] != inc.get("resident")]
            out += self.beat("rescue")
        if self.mode == "normal":
            out += self.chapter_progress(inc["type"])
        return out

    def fail(self, inc):
        self.incidents.remove(inc)
        self.hearts -= 1
        self.level = min(100.0, self.level + 5)
        self.history[inc["hist"]].update({"result": "failed", "end": round(self.elapsed),
                                          "phase": self.phase_label(), "phase_key": self.phase()})
        if inc.get("resident"):
            self.residents = [r for r in self.residents if r["id"] != inc.get("resident")]
        for p in self.players.values():
            if p["work"] and p["work"].get("id") == inc["id"]:
                p["work"] = None
        out = [("fx", {"type": "failed", "x": inc["x"], "y": inc["y"],
                       "text": f"{self.inc_name(inc['type'])} 來不及了…"}, None)]
        return out + self.beat("fail_" + inc["type"], self.D["fail"][inc["type"]], force=True)

    # ── 玩家操作 ───────────────────────────────────────────
    def move(self, sid, x, y, d, moving):
        p = self.players.get(sid)
        if p and self.status == "playing" and time.time() >= p["stun_until"]:
            p["x"] = min(W - PLAYER_R, max(PLAYER_R, float(x)))
            p["y"] = min(H - PLAYER_R, max(WALL_BOTTOM + PLAYER_R, float(y)))
            p["dir"], p["moving"] = int(d) % 4, bool(moving)

    def act(self, sid):
        """按下空白鍵：撿／放／交付／開始按住工作（依這局災難的玩法）"""
        p = self.players.get(sid)
        if not p or self.status != "playing" or time.time() < p["stun_until"]:
            return []
        hold = p["hold"]
        near = lambda x, y, r=REACH: dist(p["x"], p["y"], x, y) <= r
        K = self.K

        # 1. 現場治災
        for inc in sorted(self.incidents, key=lambda i: dist(p["x"], p["y"], i["x"], i["y"])):
            if inc["state"] != "active" or not near(inc["x"], inc["y"], REACH + 4):
                continue
            r = self.R(inc["type"])
            if r["how"] == "multi":
                if hold not in r["need"] or hold in inc["given"]:
                    continue
            elif hold != r["need"]:
                continue
            if r["how"] == "hold":
                p["work"] = {"kind": "incident", "id": inc["id"], "x": inc["x"], "y": inc["y"]}
                return [("fx", {"type": "work", "x": inc["x"], "y": inc["y"]}, None)]
            if hold:                                  # 交出道具
                p["hold"] = None
                p["stats"]["items"] += 1
            if r["how"] == "tap":
                inc["count"] += 1
                if inc["count"] >= inc["need_count"]:
                    return self.resolve(inc, p)
                return [("fx", {"type": "bag", "x": inc["x"], "y": inc["y"],
                                "text": f"{inc['count']}/{inc['need_count']}"}, None)]
            if r["how"] == "pump":
                inc["state"] = "pumping"
                inc["progress"] = 0.0
                return [("fx", {"type": "pump", "x": inc["x"], "y": inc["y"], "text": "抽水中…"}, None)]
            if r["how"] == "multi":
                inc["given"].append(hold)
                if len(inc["given"]) < len(r["need"]):
                    return [("fx", {"type": "bag", "x": inc["x"], "y": inc["y"],
                                    "text": f"{len(inc['given'])}/{len(r['need'])}"}, None)]
            # escort／multi 交齊：居民跟著走
            res = next((x for x in self.residents if x["id"] == inc.get("resident")), None)
            if res:
                res["state"], res["leader"] = "following", sid
                inc["timer"] += 15
                inc["state"] = "escort"           # 護送中：現場不再要求道具
            return [("fx", {"type": "follow", "x": inc["x"], "y": inc["y"], "text": "跟我去避難所！"}, None)]

        st = min(STATIONS, key=lambda s: dist(p["x"], p["y"], s["x"], s["y"]))
        st_near = near(st["x"], st["y"], REACH + max(st["w"], st["h"]) / 2 - 4)
        proc, bench, truck = K["process"], K["bench"], K["truck"]

        # 2. 拿著東西
        if hold:
            if st_near and st["kind"] == "sand" and proc and hold == proc["in"]:
                p["work"] = {"kind": "fill", "x": st["x"], "y": st["y"], "progress": 0.0}
                return [("fx", {"type": "work", "x": st["x"], "y": st["y"]}, None)]
            if st_near and st["kind"] == "bench" and bench and hold in bench["parts"] \
                    and hold not in self.bench["parts"] and bench["product"] not in self.bench["parts"]:
                self.bench["parts"].append(hold)
                p["hold"] = None
                return [("fx", {"type": "drop", "x": st["x"], "y": st["y"]}, sid)]
            if st_near and st["kind"] == "truck" and truck and hold in truck["accepts"]:
                p["hold"] = None
                self.coins += 15
                self.tut_flags.add("trash")
                return [("fx", {"type": "coin", "x": st["x"], "y": st["y"] - 10, "coins": 15, "text": "清運完成"}, None)]
            if st_near and st["kind"] == "crate" and self.crate_item(st) == hold:
                p["hold"] = None
                return [("fx", {"type": "drop", "x": st["x"], "y": st["y"]}, sid)]
            # 丟在地上（隊友可以撿）
            if not self.blocked(p["x"], p["y"] + 6, 2):
                self.ground.append({"id": self._id("g"), "item": hold, "x": p["x"], "y": p["y"] + 6, "by": sid})
                p["hold"] = None
                return [("fx", {"type": "drop", "x": p["x"], "y": p["y"]}, sid)]
            return []

        # 3. 空手
        if st_near and st["kind"] == "bench" and bench:
            parts = self.bench["parts"]
            if bench["product"] in parts:
                self.bench = {"parts": [], "progress": 0.0}
                p["hold"] = bench["product"]
                return [("fx", {"type": "pick", "x": p["x"], "y": p["y"], "item": p["hold"]}, sid)]
            if set(parts) == set(bench["parts"]):
                p["work"] = {"kind": "assemble", "x": st["x"], "y": st["y"]}
                return [("fx", {"type": "work", "x": st["x"], "y": st["y"]}, None)]
            if parts:
                p["hold"] = parts.pop()
                return [("fx", {"type": "pick", "x": p["x"], "y": p["y"], "item": p["hold"]}, sid)]
        g = min(self.ground, key=lambda g: dist(p["x"], p["y"], g["x"], g["y"]), default=None)
        if g and near(g["x"], g["y"], 16):
            self.ground.remove(g)
            p["hold"] = g["item"]
            relay = self.beat("relay") if g.get("by") and g["by"] != sid else []
            return [("fx", {"type": "pick", "x": p["x"], "y": p["y"], "item": g["item"]}, sid)] + relay
        if st_near and st["kind"] == "crate":
            p["hold"] = self.crate_item(st)
            return [("fx", {"type": "pick", "x": p["x"], "y": p["y"], "item": p["hold"]}, sid)] + self.beat("first_crate")
        return []

    def act_end(self, sid):
        """放開空白鍵：停止按住的工作（現場治災的進度會保留，裝沙會重來）"""
        p = self.players.get(sid)
        if p:
            p["work"] = None

    # ── 結算 ───────────────────────────────────────────────
    def finish(self):
        if self.chapter and self.chapter["status"] == "active":
            self.close_chapter(False, penalty=False)       # 最後一章沒做完：只記進故事，不再扣分
        self.status = "finished"
        fixed = sum(1 for h in self.history if h["result"] == "fixed")
        failed = sum(1 for h in self.history if h["result"] == "failed")
        survived = self.hearts > 0 and self.level < 100
        n = max(1, len(self.players))
        target = 110 * n                       # 人越多，星星門檻越高
        stars = 0 if not survived else sum(self.coins >= target * k for k in (0.6, 1.2, 1.8))
        players = sorted(self.players.values(), key=lambda p: -(p["stats"]["fixed"] * 2 + p["stats"]["items"]))
        titles = {}
        for i, p in enumerate(players):
            s = p["stats"]
            titles[p["id"]] = ("救災隊長" if i == 0 and s["fixed"] > 0 else
                               "後勤補給王" if s["items"] >= 4 else
                               "觀光客" if s["fixed"] == 0 and s["items"] == 0 else "熱血隊員")
        by_type = {}
        for h in self.history:
            d = by_type.setdefault(h["type"], {"fixed": 0, "failed": 0, "active": 0})
            d[h["result"]] += 1
        self.result = {
            "win": survived, "coins": self.coins, "stars": stars, "hearts": self.hearts,
            "fixed": fixed, "failed": failed, "water": round(self.level, 1), "duration": round(self.elapsed),
            "by_type": by_type, "scenario": (self.scenario or {}).get("name", ""),
            "disaster": self.disaster, "disaster_name": self.D["name"], "meter": self.D["meter"],
            "win_title": self.D["win_title"],
            "scenario_by": (self.scenario or {}).get("by", "rule"),
            "lessons": [{"name": self.inc_name(k), "text": self.D["knowledge"][k], "fixed": v["fixed"], "failed": v["failed"]}
                        for k, v in by_type.items()],
            "players": [{"id": p["id"], "name": p["name"], "account": p.get("account"),
                         "skin": p["skin"], "fixed": p["stats"]["fixed"],
                         "items": p["stats"]["items"], "title": titles[p["id"]]} for p in players],
            "moments": self.moments(),
            "chapters": list(self.chapters),
        }
        return self.result

    def moments(self):
        """這局值得一提的具體事件，讓鎮長每次講的都不一樣"""
        fixed = [h for h in self.history if h["result"] == "fixed"]
        failed = [h for h in self.history if h["result"] == "failed"]
        name = lambda h: self.inc_name(h["type"])
        m = {
            "peak_level": round(getattr(self, "peak_level", self.level)),
            "peak_active": getattr(self, "peak_active", 0),
            "hearts_lost": START_HEARTS - self.hearts,
            "players": len(self.players),
            "chapters_done": sum(c["status"] == "done" for c in self.chapters),
            "chapters_failed": [c["title"].split("　")[-1] for c in self.chapters if c["status"] == "failed"],
        }
        if fixed:
            close = min(fixed, key=lambda h: h.get("left", 99))
            if close.get("left", 99) < 8:
                m["close_call"] = {"what": name(close), "left": close["left"], "by": close.get("by")}
            fast = min(fixed, key=lambda h: h["end"] - h["t"])
            m["fastest"] = {"what": name(fast), "secs": fast["end"] - fast["t"], "by": fast.get("by")}
            storm = [h for h in fixed if h.get("phase_key") == "暴雨"]
            if storm:
                m["storm_fixed"] = len(storm)
        if failed:
            m["first_fail"] = {"what": name(failed[0]), "phase": failed[0].get("phase")}
            m["failed_names"] = sorted({name(h) for h in failed})
        if self.residents_saved():
            m["residents_saved"] = self.residents_saved()
        return m

    def residents_saved(self):
        return sum(1 for h in self.history if h["type"] == "trapped" and h["result"] == "fixed")

    # ── 每個 tick 廣播的狀態 ───────────────────────────────
    def snapshot(self):
        now = time.time()
        return {
            "time_left": max(0, round(GAME_TIME - self.elapsed, 1)), "level": round(self.level, 1),
            "water_y": round(self.water_y(), 1), "phase": self.phase(),
            "phase_label": self.phase_label(), "disaster": self.disaster, "chapter": self.chapter_info(),
            "hearts": self.hearts, "coins": self.coins, "mode": self.mode, "tutorial": self.tutorial_info(),
            "players": [{"id": p["id"], "name": p["name"], "skin": p["skin"], "x": round(p["x"], 1),
                         "y": round(p["y"], 1), "dir": p["dir"], "moving": p["moving"], "hold": p["hold"],
                         "stun": now < p["stun_until"],
                         "work": round(p["work"]["progress"], 2) if p["work"] and p["work"]["kind"] == "fill" else None}
                        for p in self.players.values()],
            "incidents": [{"id": i["id"], "type": i["type"], "x": i["x"], "y": i["y"], "state": i["state"],
                           "timer": round(i["timer"], 1), "max_timer": i["max_timer"],
                           "progress": round(i["progress"], 2), "count": i["count"], "need": i["need"],
                           "line": i["line"], "w": i.get("w"), "h": i.get("h"),
                           "need_count": i.get("need_count", 1), "given": i.get("given", []),
                           "waiting_team": i.get("waiting_team", False),
                           "story": bool(self.chapter and self.chapter["status"] == "active" and i["type"] in self.chapter["goal"]),
                           "team": self.team_need(self.R(i["type"])),
                           "workers": sum(1 for q in self.players.values()
                                          if q["work"] and q["work"].get("id") == i["id"])} for i in self.incidents],
            "ground": self.ground,
            "bench": {"parts": self.bench["parts"], "progress": round(self.bench["progress"], 2)},
            "residents": [{"id": r["id"], "skin": r["skin"], "x": round(r["x"], 1), "y": round(r["y"], 1),
                           "state": r["state"]} for r in self.residents],
        }
