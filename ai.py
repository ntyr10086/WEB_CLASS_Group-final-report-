"""AI 災難導演（LangChain + OpenAI / Ollama）
1. 開局劇本：每局隨機一種氣候災難（颱風淹水／熱浪野火／豪雨土石流），寫開場劇情、決定各類災情的出現權重
2. 即時派發災情：依戰況從候選清單挑下一個災情，並寫一句居民求救台詞
3. 災後檢討：依這局真的發生的災情，對應真實防災知識講評
沒有 OPENAI_API_KEY 時全部使用規則版備案，遊戲照樣能玩。
AI 只能從清單裡挑選，輸出一律驗證後才採用，不會破壞遊戲規則。"""
import json
import os
import random
import re


TYPE_NAMES = {"breach": "堤防破洞", "drain": "排水溝堵塞", "electric": "電箱冒火花",
              "house_flood": "民宅淹水", "trapped": "居民受困", "tree": "大樹倒下"}

import disasters  # noqa: E402  三種災難的名稱、知識、台詞都在 disasters.py
from game import KNOWLEDGE  # noqa: E402,F401


def names(disaster):
    return disasters.get(disaster)["incidents"]

SPEAKERS = ["氣象主播", "鎮長", "阿嬤", "小宇", "村民"]
CALM_LINE = disasters.DISASTERS["typhoon"]["calm"]
STORM_LINE = disasters.DISASTERS["typhoon"]["storm"]

# 沒有 AI 時的劇本：一樣帶出「氣候變遷、平時準備、分工合作」三件事
PRESET_SCENARIOS = [
    {"disaster": "typhoon", "name": "颱風「小鹿」", "headline": "小鹿急速增強 河川水位創新高",
     "weights": {"breach": 2.0, "drain": 1.0, "electric": 0.8, "house_flood": 1.0, "trapped": 1.0, "tree": 0.8},
     "story": [
         {"speaker": "氣象主播", "line": "插播！颱風小鹿在溫暖的海面上急速增強，雨量可能打破紀錄！"},
         {"speaker": "鎮長", "line": "這幾年的颱風一年比一年兇……河堤年久失修，恐怕撐不住。"},
         {"speaker": "阿嬤", "line": "還好你們平時就把沙包和工具備在倉庫裡，這下派上用場了。"},
         {"speaker": "小宇", "line": "我、我也想幫忙！"},
         {"speaker": "鎮長", "line": "救援隊集合！看災情單分工，我們一起守住小鎮！"}]},
    {"disaster": "typhoon", "name": "颱風「芒果」", "headline": "芒果帶來超大豪雨 老街多處積水",
     "weights": {"breach": 1.0, "drain": 2.0, "electric": 1.2, "house_flood": 1.5, "trapped": 0.8, "tree": 0.8},
     "story": [
         {"speaker": "氣象主播", "line": "芒果颱風的雨帶又厚又慢，專家說這種極端降雨會越來越常見。"},
         {"speaker": "村民", "line": "老街的水溝塞滿落葉，上次下大雨就淹到膝蓋了……"},
         {"speaker": "鎮長", "line": "別慌，倉庫裡耙子、抽水機零件都準備好了，平時的準備就是為了今天。"},
         {"speaker": "阿嬤", "line": "一個人忙不過來的，大家要互相幫忙喔。"},
         {"speaker": "鎮長", "line": "救援隊出動！一個顧水溝、一個做抽水機，分工合作！"}]},
    {"disaster": "typhoon", "name": "颱風「颯颯」", "headline": "颯颯強風來襲 路樹電箱頻傳災情",
     "weights": {"breach": 0.8, "drain": 1.0, "electric": 2.0, "house_flood": 0.8, "trapped": 1.0, "tree": 2.0},
     "story": [
         {"speaker": "氣象主播", "line": "颯颯颱風風力超強，海水溫度偏高讓它一路增強！"},
         {"speaker": "村民", "line": "外面的樹都在搖，電箱也被雨打得滋滋作響……"},
         {"speaker": "鎮長", "line": "記得：碰電箱前一定要戴絕緣手套！工具都在倉庫，平時就準備好了。"},
         {"speaker": "小宇", "line": "倒下的樹我可以幫忙搬嗎？"},
         {"speaker": "鎮長", "line": "交給救援隊吧！大家分頭行動，一起撐過今晚！"}]},
    {"disaster": "typhoon", "name": "颱風「團圓」", "headline": "團圓滯留不走 低窪住宅區告急",
     "weights": {"breach": 1.0, "drain": 1.0, "electric": 1.0, "house_flood": 1.5, "trapped": 2.0, "tree": 0.8},
     "story": [
         {"speaker": "氣象主播", "line": "颱風團圓移動緩慢，豪雨會持續一整晚，這是近年最嚴重的一次。"},
         {"speaker": "阿嬤", "line": "我們家地勢低，水一下子就淹上來了……"},
         {"speaker": "鎮長", "line": "別怕，救生圈和避難所都準備好了，平時演練過的就照著做。"},
         {"speaker": "小宇", "line": "阿嬤！我們一起去避難所！"},
         {"speaker": "鎮長", "line": "救援隊，看災情單！救人、補洞、清水溝，大家分工！"}]},

    # ── 熱浪野火 ──
    {"disaster": "heatwave", "name": "熱浪「烤地瓜」", "headline": "連續高溫破紀錄 後山傳出火警",
     "weights": {"breach": 2.0, "drain": 1.5, "electric": 1.0, "house_flood": 1.0, "trapped": 1.0, "tree": 0.8},
     "story": [
         {"speaker": "氣象主播", "line": "插播！小鎮已經連續十天高溫，專家說熱浪會越來越頻繁、越來越久。"},
         {"speaker": "村民", "line": "後山的草都曬乾了，剛剛好像看到冒煙……"},
         {"speaker": "鎮長", "line": "別慌！倉庫裡沙土袋和消防泵零件平時就備好了，就是為了今天。"},
         {"speaker": "阿嬤", "line": "天氣這麼熱，大家也要記得喝水，別自己先倒下囉。"},
         {"speaker": "鎮長", "line": "救援隊出動！一個築防火線、一個清枯草，分工合作！"}]},
    {"disaster": "heatwave", "name": "熱浪「大火爐」", "headline": "熱浪來襲 用電量創新高",
     "weights": {"breach": 1.0, "drain": 1.0, "electric": 2.0, "house_flood": 1.2, "trapped": 2.0, "tree": 0.8},
     "story": [
         {"speaker": "氣象主播", "line": "大火爐熱浪報到！地球越來越暖，這種高溫以前很少見。"},
         {"speaker": "小宇", "line": "家家戶戶冷氣全開，我家的電線摸起來好燙喔……"},
         {"speaker": "阿嬤", "line": "隔壁阿公一個人住，這麼熱不知道還好嗎？"},
         {"speaker": "鎮長", "line": "絕緣手套、冰毛巾都在倉庫，平時演練過的就照著做。"},
         {"speaker": "鎮長", "line": "救援隊集合！顧電線、照顧長輩，大家分頭行動！"}]},

    # ── 豪雨土石流 ──
    {"disaster": "landslide", "name": "豪雨「泥巴怪」", "headline": "山區連日豪雨 後山土石鬆動",
     "weights": {"breach": 2.0, "drain": 1.5, "electric": 0.8, "house_flood": 1.2, "trapped": 1.0, "tree": 1.2},
     "story": [
         {"speaker": "氣象主播", "line": "插播！山區已經連續下了三天大雨，雨量比以前同期多很多。"},
         {"speaker": "村民", "line": "後山的溪水突然變得好混濁，還聽到轟隆隆的聲音……"},
         {"speaker": "鎮長", "line": "這是土石流的徵兆！還好倉庫裡沙包、鐵鎚平時都備好了。"},
         {"speaker": "小宇", "line": "我、我可以幫忙清水溝！"},
         {"speaker": "鎮長", "line": "救援隊出動！擋土石、清溝渠、帶居民撤離，分工合作！"}]},
    {"disaster": "landslide", "name": "豪雨「滑滑梯」", "headline": "超大豪雨特報 山坡住戶緊急撤離",
     "weights": {"breach": 1.0, "drain": 1.0, "electric": 1.5, "house_flood": 1.0, "trapped": 2.0, "tree": 2.0},
     "story": [
         {"speaker": "氣象主播", "line": "滑滑梯豪雨帶來超大雨量，專家說極端豪雨在氣候變遷下越來越常見。"},
         {"speaker": "阿嬤", "line": "我們家就在山坡邊，地板都在滲水了……"},
         {"speaker": "鎮長", "line": "阿嬤別怕！救援繩和避難所都準備好了，平時演練過的就照著做。"},
         {"speaker": "村民", "line": "外面的路好像被石頭擋住了！"},
         {"speaker": "鎮長", "line": "救援隊，看災情單！敲落石、救居民，大家分工！"}]},
]


def _ask(template, **kw):
    """透過 llm.py 呼叫 AI（依 AI_PROVIDER 設定：OpenAI → Ollama → 規則版），回傳 dict；失敗回傳 None"""
    try:
        import llm
        data, provider = llm.ask_json("你是一款氣候災難救援遊戲的 AI，只能回傳一個 JSON 物件，不要加任何說明文字。",
                                      template.format(**kw))
        if isinstance(data, dict):
            data["_provider"] = provider
            return data
    except Exception as e:
        print("[ai] 呼叫失敗，改用規則版：", e)
    return None


# ── 1. 開局颱風劇本：AI 寫開場劇情（把遊戲想傳達的事放進故事裡）──────────
SCENARIO_PROMPT = """你是一款可愛像素風「{disaster}救援隊」合作遊戲的劇情編劇，請為這一局寫開場劇情。
這局的災難是「{disaster}」。{town}；玩家是鎮上的救援隊。
劇情要自然帶出三件事（用角色對話表現，不要說教、不要條列）：
1. {climate}
2. 平時準備好的防災物資，現在派上用場
3. 一個人做不完，大家分工合作才撐得過去
角色只能用：{speakers}。台灣口語、可愛、有一點幽默。
所有文字都必須是「繁體中文」，不可以出現任何英文字母、拼音或英文單字（例如 town、OK 都不行）。
這局可能的災情類型（代碼: 名稱）：{types}
遊戲分三段：{phase1} → {phase2}（短暫喘息）→ {phase3}（最危險）。
只回傳 JSON：
{{"name": "{event}「兩到三個字的可愛名字」", "headline": "20 字內的新聞標題",
  "story": [{{"speaker": "角色", "line": "40 字內台詞"}}, 共 5 句，最後一句由鎮長號召救援隊出動],
  "calm_line": {{"speaker": "角色", "line": "30 字內，{phase2}時的提醒"}},
  "peak_line": {{"speaker": "角色", "line": "30 字內，{phase3}時的打氣"}},
  "weights": {{每個災情類型代碼: 0.5 到 2.5 的數字，和劇情裡的小鎮弱點相關的給高}}}}"""


def _text(v, limit=60):
    """把 AI 回傳的值整理成一句乾淨的文字。
    本機模型（例如 llama）有時會把字串包成 {"line": "..."} 或清單，直接 str() 會出現亂碼"""
    if isinstance(v, dict):
        v = next((v[k] for k in ("line", "text", "content", "report", "value") if v.get(k)),
                 next((x for x in v.values() if isinstance(x, str)), ""))
    if isinstance(v, (list, tuple)):
        v = "".join(_text(x, limit) for x in v[:1])
    t = str(v or "").strip().strip('"\'').strip()
    if not t or any(c in t for c in "{}[]<>") or "'line'" in t or '"line"' in t:
        return ""                                 # 看起來像程式碼的就不要
    if not _is_chinese(t):
        return ""                                 # 夾英文、不是中文的句子不用，改用內建台詞
    t = t[:limit]
    if t.count("「") > t.count("」"):             # 被截斷的引號補回來
        t += "」"
    return t


def _is_chinese(t):
    """畫面上的文字都要是中文：不能有英文字母，且大部分是中文字"""
    if re.search(r"[A-Za-z]", t):
        return False
    han = len(re.findall(r"[\u4e00-\u9fff]", t))
    return han >= max(2, len(re.sub(r"[\s\d\W_]", "", t)) * 0.8)


def _clean_line(d, default_speaker="村民", limit=60):
    if not isinstance(d, dict):
        return None
    line = _text(d.get("line"), limit)
    if not line:
        return None
    sp = d.get("speaker") if d.get("speaker") in SPEAKERS else default_speaker
    return {"speaker": sp, "line": line}


def _clean_name(v, event):
    """AI 取的名字整理成「颱風「小鹿」」這種格式；不合格就用內建的可愛名字"""
    raw = _text(v, 20)
    m = re.search(r"「([\u4e00-\u9fff]{1,4})」?", raw) if raw else None
    core = m.group(1) if m else re.sub(r"[^\u4e00-\u9fff]", "", raw.replace(event, ""))[:4]
    if len(core) < 2:
        core = random.choice(["小鹿", "芒果", "麻糬", "布丁", "阿吉", "胖胖"])
    return f"{event}「{core}」"


def make_scenario(disaster=None, exclude=None):
    """寫這局的開場劇本；disaster 沒指定就隨機抽一種（盡量不和上一局 exclude 一樣）"""
    disaster = disaster or disasters.pick(exclude)
    d = disasters.get(disaster)
    ph = d["phases"]
    data = _ask(SCENARIO_PROMPT, disaster=d["name"], event=d["event"], town=d["town"], climate=d["climate"],
                speakers="、".join(SPEAKERS), types=json.dumps(d["incidents"], ensure_ascii=False),
                phase1=ph["小雨"], phase2=ph["颱風眼"], phase3=ph["暴雨"])
    if data and isinstance(data.get("weights"), dict) and isinstance(data.get("story"), list):
        story = [l for l in (_clean_line(x) for x in data["story"][:6]) if l]
        if len(story) >= 3:
            weights = {}
            for k in TYPE_NAMES:
                try:
                    weights[k] = float(min(2.5, max(0.5, float(data["weights"].get(k, 1.0)))))
                except (TypeError, ValueError):
                    weights[k] = 1.0
            # 氣象主播的氣候新聞不給 AI 寫：用 disasters.py 裡核對過的句子（本機模型常把科學講錯）
            return {"disaster": disaster, "name": _clean_name(data.get("name"), d["event"]),
                    "headline": _text(data.get("headline"), 24) or _preset_headline(disaster), "news": None,
                    "story": story, "weights": weights, "by": "ai", "provider": data.get("_provider"),
                    "phase_lines": {"颱風眼": _clean_line(data.get("calm_line"), "鎮長") or d["calm"],
                                    "暴雨": _clean_line(data.get("peak_line"), "氣象主播") or d["storm"]}}
    return rule_scenario(disaster)


def _preset_headline(disaster):
    return random.choice([p for p in PRESET_SCENARIOS if p["disaster"] == disaster])["headline"]


def rule_scenario(disaster=None, exclude=None):
    """內建劇本（不呼叫 AI，立刻回傳）"""
    disaster = disaster or disasters.pick(exclude)
    d = disasters.get(disaster)
    preset = random.choice([p for p in PRESET_SCENARIOS if p["disaster"] == disaster])
    return {**preset, "by": "rule", "phase_lines": {"颱風眼": d["calm"], "暴雨": d["storm"]}}


# ── 2. 即時派發災情 ─────────────────────────────────────────
DIRECTOR_PROMPT = """你是{disaster}救災遊戲的「災難導演」，目標是讓玩家緊張又玩得開心。
本局劇本：{story}（各災情權重 {weights}）
現況：剩 {time_left} 秒、天氣 {phase}、愛心 {hearts}/5、{meter} {level}%、
進行中的災情：{active}；最近成功：{fixed} 件，失敗：{failed} 件。
本章劇情任務：{chapter}（可以多派這類災情，讓劇情推進）
規則：愛心 2 以下時挑比較好處理的；玩家很順時可以挑比較難的；同類型不要連續太多次。
可選的災情（只能從這裡挑一個 index）：
{options}
只回傳 JSON：{{"index": 數字, "line": "受災居民的一句求救台詞，20 字內，繁體中文、台灣口語，可愛有梗，不可以有英文"}}"""


def direct(state, candidates):
    """回傳 (候選, 台詞, "ai")；AI 失敗回傳 None 由規則版接手"""
    if not candidates:
        return None
    nm = names(state.get("disaster_key"))
    options = "\n".join(f"{i}. {nm[c['type']]}（位置 {c['x']},{c['y']}）"
                        for i, c in enumerate(candidates[:12]))
    data = _ask(DIRECTOR_PROMPT, options=options, **state)
    if data and isinstance(data.get("index"), int) and 0 <= data["index"] < min(12, len(candidates)):
        line = _text(data.get("line"), 24) or None
        return candidates[data["index"]], line, "ai"
    return None


# ── 3. 災後檢討 ─────────────────────────────────────────────
MAYOR_MOODS = [
    "感動到有點哽咽", "嘴硬心軟、愛碎念", "超級驕傲像在炫耀孫子", "冷笑話很多的老派大叔",
    "累到快睡著但很欣慰", "熱血像體育老師", "很會自嘲自己什麼都沒做",
]

REPORT_PROMPT = """你是遊戲裡的「鎮長」，{disaster}「{scenario}」剛過，你對救援隊說幾句話。
這次你的說話風格：{mood}。
要求：
- 只能用繁體中文（不可以有任何英文字母或英文單字）、第一人稱、台灣口語，80～140 字，像真的在講話，不要條列
- 一定要點名至少一位隊員，並提到下面「這局發生的事」裡至少兩件具體的事（數字、誰、什麼災情）
- 不要用「辛苦了」「多虧」「總結來說」這類制式開頭，每次開場都要不一樣
- 自然帶到一句：{climate}，所以平時準備、鄰居互相照應很重要（換句話說，不要照抄）
- 最後用鎮長自己的口吻，叮嚀下面其中一條防災知識：
{knowledge}
這局結果：{summary}
這局發生的事：{moments}
隊員：{players}"""


def _moments_text(r):
    m, out = r.get("moments", {}), []
    if m.get("close_call"):
        c = m["close_call"]; out.append(f"{c['by'] or '有人'}在{c['what']}只剩 {c['left']} 秒時才搶救成功")
    if m.get("fastest"):
        f = m["fastest"]; out.append(f"最快的一次是{f['by'] or '大家'}只花 {f['secs']} 秒就解決{f['what']}")
    d = disasters.get(r.get("disaster"))
    if m.get("storm_fixed"):
        out.append(f"最後{d['phases']['暴雨']}時還解決了 {m['storm_fixed']} 件災情")
    if m.get("first_fail"):
        out.append(f"第一次失守是在{m['first_fail']['phase']}時的{m['first_fail']['what']}")
    if m.get("residents_saved"):
        out.append(f"救出了 {m['residents_saved']} 位受困居民")
    out.append(f"{d['meter']}最高到 {m.get('peak_level', 0)}%，最多同時有 {m.get('peak_active', 0)} 件災情")
    if m.get("hearts_lost"):
        out.append(f"小鎮損失了 {m['hearts_lost']} 顆愛心")
    for c in r.get("chapters", []):
        out.append(f"{c['title'].split('　')[-1]}{'完成了' if c['status'] == 'done' else '沒做到'}")
    return "；".join(out)


def make_report(result):
    by_type = result.get("by_type", {})
    d = disasters.get(result.get("disaster"))
    nm = d["incidents"]
    parts = [f"{nm[k]} 成功 {v['fixed']}、失敗 {v['failed']}" for k, v in by_type.items()
             if v["fixed"] + v["failed"] > 0]
    summary = (f"{'撐過來了' if result['win'] else '失守了'}，解除 {result['fixed']} 件、失敗 {result['failed']} 件，"
               f"金幣 {result['coins']}，剩 {result['hearts']} 顆愛心。" + "；".join(parts))
    ranked = sorted(by_type, key=lambda k: (-by_type[k]["failed"], -by_type[k]["fixed"]))
    tips = _retrieve_tips(ranked, result.get("disaster"))
    players = "、".join(f"{p['name']}（{p['title']}，治災 {p['fixed']}、運送 {p['items']}）" for p in result["players"])
    data = _ask(REPORT_PROMPT + "\n只回傳 JSON：{{\"report\": \"鎮長的話\"}}",
                scenario=result.get("scenario", ""), disaster=d["name"], climate=d["climate"], mood=random.choice(MAYOR_MOODS), knowledge="\n".join(tips),
                summary=summary, moments=_moments_text(result), players=players)
    report = _text(data.get("report"), 260) if data else ""
    if report:
        return {"report": report, "tips": tips, "by": data.get("_provider") or "ai"}
    return {"report": rule_mayor(result, ranked, tips), "tips": tips, "by": "rule"}


def _retrieve_tips(ranked, disaster=None):
    """簡化版 RAG：用這局最常出事的災情類型當 tags，從知識庫挑 2 條（每局隨機，不會都一樣）
    颱風的 tag 是災情代碼（例如 drain）；其他災難是「災難:代碼」（例如 heatwave:drain）"""
    disaster = disaster if disaster in disasters.DISASTERS else "typhoon"
    know = disasters.get(disaster)["knowledge"]
    tag = (lambda k: k) if disaster == "typhoon" else (lambda k: f"{disaster}:{k}")
    try:
        import db
        docs = db.find_knowledge([tag(k) for k in (ranked[:3] or ["drain"])], limit=2)
        tips = [d["content"] for d in docs if d.get("content")]
        if tips:
            return tips
    except Exception as e:
        print("[ai] 知識庫檢索失敗，改用內建知識：", e)
    return [know[k] for k in ranked[:2]] or [know["drain"]]


# ── 規則版鎮長：依這局真的發生的事，從很多句子裡挑著組合，每次都不一樣 ──────────
def rule_mayor(r, ranked, tips):
    m, ps = r.get("moments", {}), r["players"]
    pick = random.choice
    mvp = ps[0] if ps else None
    lazy = next((p for p in ps if p["fixed"] == 0 and p["items"] == 0), None)
    d = disasters.get(r.get("disaster"))
    ev = d["event"]
    typhoon = r.get("scenario") or f"這次的{ev}"
    funny_win = {"typhoon": "颱風走了，我的假髮也被吹走了，但小鎮還在！",
                 "heatwave": "熱浪退了，我的假髮也熱到捲起來了，但小鎮還在！",
                 "landslide": "雨停了，我的皮鞋整雙都是泥巴，但小鎮還在！"}
    funny_lose = {"typhoon": "鎮公所的地下室現在變成游泳池了……沒關係，我們一起整理。",
                  "heatwave": "鎮公所的冷氣燒壞了，我現在汗流成河……沒關係，我們一起整理。",
                  "landslide": "鎮公所門口堆了一座泥巴山……沒關係，我們一起鏟。"}
    key = r.get("disaster") if r.get("disaster") in funny_win else "typhoon"

    # 開場：依結果和險不險挑
    if r["win"] and r["hearts"] == 5:
        opens = [f"{typhoon}來勢洶洶，結果一顆愛心都沒少！我當鎮長三十年第一次看到。",
                 "我剛剛躲在避難所偷看，你們根本是專業的吧？小鎮完好無缺！",
                 f"報告！{typhoon}已經離開，小鎮全員平安，連阿嬤的貓都沒事。"]
    elif r["win"]:
        opens = [f"呼……撐過來了。雖然小鎮掉了 {m.get('hearts_lost', 0)} 顆愛心，但大家都還在。",
                 f"{typhoon}比我想的兇，但你們比{ev}更兇。",
                 funny_win[key]]
        if m.get("peak_level", 0) >= 55:
            opens.append(f"老實說{d['meter']}衝到 {m['peak_level']}% 的時候，我已經在收行李準備跑了。結果我們撐住了！")
    else:
        opens = [f"唉……{typhoon}這次贏了一回合。不過沒關係，明年我們再跟它算帳。",
                 f"我們輸給了{typhoon}，但今晚每個衝出去的人，我都記得。",
                 funny_lose[key]]
        if d["incidents"]["trapped"] not in m.get("failed_names", []):
            opens.append("房子壞了可以再修，但人都平安，這才是最重要的。")
    lines = [pick(opens)]

    # 點名隊員（具體的人和數字）
    shout = []
    if mvp and mvp["fixed"] > 0:
        shout += [f"{mvp['name']}一個人就處理了 {mvp['fixed']} 件災情，明天鎮公所幫你頒獎。",
                  f"特別點名{mvp['name']}，跑得比我家的狗還快，{mvp['fixed']} 件災情都是你搞定的。"]
    if lazy and len(ps) > 1:
        shout += [f"至於{lazy['name']}……我有看到你在避難所旁邊躲雨喔，下次換你衝第一個。",
                  f"{lazy['name']}今天比較像觀光客，沒關係，第一次出任務都是這樣的。"]
    if m.get("close_call"):
        c = m["close_call"]
        shout += [f"{c['what']}只剩 {c['left']} 秒的時候{c['by'] or '你們'}才衝到，我心臟差點停掉！",
                  f"還記得{c['what']}嗎？只差 {c['left']} 秒，好險{c['by'] or '有人'}及時趕到。"]
    if m.get("fastest") and m["fastest"]["secs"] <= 12:
        f = m["fastest"]
        shout.append(f"{f['by'] or '有人'}只花 {f['secs']} 秒就解決{f['what']}，這速度我沒看過。")
    if m.get("residents_saved"):
        shout.append(f"你們救出了 {m['residents_saved']} 位受困的鄰居，他們說明天要請大家吃滷肉飯。")
    if m.get("first_fail"):
        ff = m["first_fail"]
        shout.append(f"{ff['phase']}那時候的{ff['what']}沒來得及，我知道大家都盡力了。")
    if m.get("peak_active", 0) >= 4:
        shout.append(f"最多同時有 {m['peak_active']} 件災情在響，你們還是分得過來，這就是團隊。")
    random.shuffle(shout)
    lines += shout[:2]
    # 劇情任務：把「準備、互助、氣候」三章的結果講出來
    chs = r.get("chapters", [])
    if chs:
        done = [c for c in chs if c["status"] == "done"]
        if len(done) == len(chs):
            lines.append("今晚交代的事你們全做到了：先做好準備、去幫鄰居、再一起撐過最兇的那一波。")
        elif done:
            miss = next(c for c in chs if c["status"] != "done")
            lines.append(f"「{miss['title'].split('　')[-1]}」那件事沒做到，下次記得：{miss['theme']}很重要。")
        else:
            lines.append("今晚交代的事都沒做到……沒關係，記住先準備、再互助，下一次一定更好。")

    # 氣候變遷（換著說，不照抄）
    # 氣候變遷的叮嚀：沒撐住或有章節沒做到時，不用「今晚能撐住是因為…」這類句子（不然前後矛盾）
    pool = d["climate_lines"]
    if not r["win"] or any(c["status"] != "done" for c in r.get("chapters", [])):
        pool = [l for l in pool if "撐住" not in l]
    lines.append(pick(pool + ["天氣越來越極端，靠的不是運氣，是平時的準備和鄰居之間的默契。"]))    # 防災叮嚀（鎮長口吻）
    lines.append(pick(["對了，", "最後碎念一句：", "鎮長的叮嚀：", "回家前記得，"]) + tips[0])
    return "".join(lines)
