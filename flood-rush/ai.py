"""AI 災難導演（LangChain + OpenAI）
1. 開局颱風劇本：生成這局的颱風與小鎮弱點，決定各類災情的出現權重
2. 即時派發災情：依戰況從候選清單挑下一個災情，並寫一句居民求救台詞
3. 災後檢討：依這局真的發生的災情，對應真實防災知識講評
沒有 OPENAI_API_KEY 時全部使用規則版備案，遊戲照樣能玩。
AI 只能從清單裡挑選，輸出一律驗證後才採用，不會破壞遊戲規則。"""
import json
import os
import random
import re

_llm = None
_tried = False

TYPE_NAMES = {"breach": "堤防破洞", "drain": "排水溝堵塞", "electric": "電箱冒火花",
              "house_flood": "民宅淹水", "trapped": "居民受困", "tree": "大樹倒下"}

from game import KNOWLEDGE  # noqa: E402  防災知識只維護一份（game.py）

PRESET_SCENARIOS = [
    {"name": "颱風「小鹿」", "story": "小鹿從東北方逼近，河川水位暴漲，河堤年久失修。",
     "weights": {"breach": 2.0, "drain": 1.0, "electric": 0.8, "house_flood": 1.0, "trapped": 1.0, "tree": 0.8}},
    {"name": "颱風「芒果」", "story": "芒果帶來超大豪雨，老街排水溝塞滿落葉，到處積水。",
     "weights": {"breach": 1.0, "drain": 2.0, "electric": 1.2, "house_flood": 1.5, "trapped": 0.8, "tree": 0.8}},
    {"name": "颱風「颯颯」", "story": "颯颯的強風吹倒路樹，電線和電箱也跟著出狀況。",
     "weights": {"breach": 0.8, "drain": 1.0, "electric": 2.0, "house_flood": 0.8, "trapped": 1.0, "tree": 2.0}},
    {"name": "颱風「團圓」", "story": "團圓滯留不走，低窪住宅區有長輩受困，需要大家幫忙。",
     "weights": {"breach": 1.0, "drain": 1.0, "electric": 1.0, "house_flood": 1.5, "trapped": 2.0, "tree": 0.8}},
]


def get_llm():
    global _llm, _tried
    if _tried:
        return _llm
    _tried = True
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                          temperature=0.9, timeout=6, max_retries=0)
    except Exception as e:
        print("[ai] LLM 無法使用，改用規則版：", e)
    return _llm


def _ask(template, **kw):
    """呼叫 LLM 並解析 JSON；失敗回傳 None"""
    llm = get_llm()
    if not llm:
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        res = (ChatPromptTemplate.from_template(template) | llm).invoke(kw)
        m = re.search(r"\{.*\}", res.content, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as e:
        print("[ai] 呼叫失敗，改用規則版：", e)
        return None


# ── 1. 開局颱風劇本 ─────────────────────────────────────────
SCENARIO_PROMPT = """你是一款可愛的颱風救災合作遊戲的關卡編劇。請為這一局創造一個虛構颱風。
小鎮有：河堤、四間民宅、排水溝、電箱、行道樹。可能的災情類型：{types}
只回傳 JSON：
{{"name": "颱風「兩個字的可愛名字」", "story": "40 字內的新聞快報，點出這次小鎮的弱點",
  "weights": {{每個災情類型代碼: 0.5 到 2.5 的數字，弱點相關的給高}}}}"""


def make_scenario():
    data = _ask(SCENARIO_PROMPT, types=json.dumps(TYPE_NAMES, ensure_ascii=False))
    if data and isinstance(data.get("weights"), dict):
        weights = {k: float(min(2.5, max(0.5, data["weights"].get(k, 1.0)))) for k in TYPE_NAMES}
        return {"name": str(data.get("name", "颱風"))[:12], "story": str(data.get("story", ""))[:60],
                "weights": weights, "by": "ai"}
    return {**random.choice(PRESET_SCENARIOS), "by": "rule"}


# ── 2. 即時派發災情 ─────────────────────────────────────────
DIRECTOR_PROMPT = """你是颱風救災遊戲的「災難導演」，目標是讓玩家緊張又玩得開心。
本局劇本：{story}（各災情權重 {weights}）
現況：剩 {time_left} 秒、天氣 {phase}、愛心 {hearts}/5、水位 {level}%、
進行中的災情：{active}；最近成功：{fixed} 件，失敗：{failed} 件。
規則：愛心 2 以下時挑比較好處理的；玩家很順時可以挑比較難的；同類型不要連續太多次。
可選的災情（只能從這裡挑一個 index）：
{options}
只回傳 JSON：{{"index": 數字, "line": "受災居民的一句求救台詞，20 字內，台灣口語，可愛有梗"}}"""


def direct(state, candidates):
    """回傳 (候選, 台詞)；AI 失敗回傳 None 由規則版接手"""
    if not candidates:
        return None
    options = "\n".join(f"{i}. {TYPE_NAMES[c['type']]}（位置 {c['x']},{c['y']}）"
                        for i, c in enumerate(candidates[:12]))
    data = _ask(DIRECTOR_PROMPT, options=options, **state)
    if data and isinstance(data.get("index"), int) and 0 <= data["index"] < min(12, len(candidates)):
        line = str(data.get("line", "")).strip()[:24] or None
        return candidates[data["index"]], line
    return None


# ── 3. 災後檢討 ─────────────────────────────────────────────
REPORT_PROMPT = """你是防災遊戲的講評員，用繁體中文寫 120 字內的災後檢討，語氣活潑：
先一句總評，再點出處理得好、和來不及處理的災情，
最後挑 1～2 條下面的真實防災知識，自然地帶進講評：
{knowledge}
這局結果：{summary}"""


def make_report(result):
    by_type = result.get("by_type", {})
    parts = [f"{TYPE_NAMES[k]} 成功 {v['fixed']}、失敗 {v['failed']}" for k, v in by_type.items()
             if v["fixed"] + v["failed"] > 0]
    summary = (f"{result['scenario']}，{'撐過來了' if result['win'] else '失守了'}，"
               f"解除 {result['fixed']} 件、失敗 {result['failed']} 件，金幣 {result['coins']}，"
               f"剩 {result['hearts']} 顆愛心。" + "；".join(parts) + "。")
    # 挑這局最常出事（或失敗最多）的災情，對應真實知識
    ranked = sorted(by_type, key=lambda k: (-by_type[k]["failed"], -by_type[k]["fixed"]))
    tips = [KNOWLEDGE[k] for k in ranked[:2]] or [KNOWLEDGE["drain"]]
    data = _ask(REPORT_PROMPT + "\n只回傳 JSON：{{\"report\": \"講評內容\"}}",
                knowledge="\n".join(tips), summary=summary)
    if data and data.get("report"):
        return {"report": str(data["report"])[:220], "tips": tips, "by": "ai"}
    head = "颱風過境，小鎮撐住了！" if result["win"] else "這次小鎮失守了，下一局再拚！"
    worst = ranked[0] if ranked else None
    mid = f"最讓大家手忙腳亂的是「{TYPE_NAMES[worst]}」。" if worst else ""
    return {"report": f"{head}{summary}{mid}", "tips": tips, "by": "rule"}
