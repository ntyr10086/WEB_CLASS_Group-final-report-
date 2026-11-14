"""AI 供應層：用 LangChain 把 OpenAI、Groq 和 Ollama 包成同一個介面

AI_PROVIDER 設定：
  auto   （預設）依序試 OpenAI → Groq → 本機 Ollama（有設 key 的才會用），都不行就用規則版
  groq   只用 Groq（免費、速度快，雲端版建議用這個）
  ollama 只用本機 Ollama（課堂 ch7 的做法，不用錢、不用網路）
  openai 只用 OpenAI
  off    全部用規則版

某一家呼叫失敗時會自動換下一家；全部失敗回傳 None，由 ai.py 的規則版接手。
Render 免費主機跑不動 Ollama，雲端版在 auto 模式下會自動略過它。
"""
import json
import os
import re
import threading
import time
import urllib.request

PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"   # Groq 相容 OpenAI 的 API 格式
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "20"))   # 本機模型第一次載入比較慢

_chain = None            # [(名稱, LangChain 模型)]，依序嘗試
_lock = threading.Lock()
status = {"provider": PROVIDER, "chain": [], "calls": 0, "fails": 0,
          "last": None, "last_ms": None, "last_error": None, "ollama": None,
          "init_error": None}


# ── 建立模型 ───────────────────────────────────────────────
def _ollama_check():
    """確認 Ollama 有開、模型已下載。回傳 (可用, 說明)"""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=1.5) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception:
        return False, f"連不到 Ollama（{OLLAMA_HOST}），請先開啟 Ollama"
    want = OLLAMA_MODEL if ":" in OLLAMA_MODEL else OLLAMA_MODEL + ":latest"
    if want not in names:
        return False, f"Ollama 還沒有 {OLLAMA_MODEL}，請執行：ollama pull {OLLAMA_MODEL}"
    return True, f"{OLLAMA_MODEL} 已就緒"


def _make_openai():
    if not os.getenv("OPENAI_API_KEY"):
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=OPENAI_MODEL, temperature=0.9, timeout=6, max_retries=0)


def _make_groq():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=GROQ_MODEL, api_key=key, base_url=GROQ_BASE_URL,
                      temperature=0.9, timeout=15, max_retries=0)


def _make_ollama():
    ok, msg = _ollama_check()
    status["ollama"] = msg
    if not ok:
        print("[ai]", msg)
        return None
    from langchain_ollama import ChatOllama
    return ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_HOST,
                      format="json",          # 強制輸出 JSON，小模型才不會亂講
                      temperature=0.8, num_predict=600,   # 開場劇情有 5 句中文，200 會被截斷
                      keep_alive="30m",       # 模型留在記憶體，下一次就快
                      client_kwargs={"timeout": OLLAMA_TIMEOUT})


def get_chain():
    global _chain
    with _lock:
        if _chain is not None:
            return _chain
        order = {"auto": ["openai", "groq", "ollama"], "openai": ["openai"],
                 "groq": ["groq"], "ollama": ["ollama"],
                 "off": []}.get(PROVIDER, ["openai", "groq", "ollama"])
        makers = {"openai": _make_openai, "groq": _make_groq, "ollama": _make_ollama}
        _chain = []
        status["init_error"] = None
        for name in order:
            try:
                m = makers[name]()
                if m is not None:
                    _chain.append((name, m))
            except Exception as e:
                print(f"[ai] {name} 無法使用：", e)
                status["init_error"] = f"{name}: {type(e).__name__}: {str(e)[:200]}"
        status["chain"] = [n for n, _ in _chain]
        print("[ai] 使用順序：", " → ".join(status["chain"] + ["規則版"]))
        return _chain


def reset():
    """重新偵測（例如 Ollama 晚一點才打開）"""
    global _chain
    with _lock:
        _chain = None
    return get_chain()


# ── 呼叫 ───────────────────────────────────────────────────
def _parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else None


def ask_json(system, user):
    """依序呼叫可用的模型，回傳 (dict, 供應者名稱)；全部失敗回傳 (None, None)"""
    from langchain_core.messages import HumanMessage, SystemMessage
    msgs = [SystemMessage(content=system), HumanMessage(content=user)]
    for name, model in get_chain():
        t0 = time.time()
        status["calls"] += 1
        try:
            data = _parse(model.invoke(msgs).content)
            if not isinstance(data, dict):
                raise ValueError("沒有回傳 JSON")
            status.update(last=name, last_ms=round((time.time() - t0) * 1000), last_error=None)
            return data, name
        except Exception as e:
            status["fails"] += 1
            status["last_error"] = f"{name}: {str(e)[:120]}"
            print(f"[ai] {name} 失敗，換下一個：", e)
    return None, None


def warm_up():
    """開伺服器時先叫醒 Ollama，把模型載進記憶體，第一局就不會等很久"""
    chain = get_chain()
    for name, model in chain:
        if name == "ollama":
            try:
                t0 = time.time()
                model.invoke("回傳 JSON：{\"ok\": true}")
                print(f"[ai] Ollama 預熱完成（{time.time() - t0:.1f} 秒）")
            except Exception as e:
                print("[ai] Ollama 預熱失敗：", e)


def info():
    return {**status, "openai_model": OPENAI_MODEL if "openai" in status["chain"] else None,
            "groq_model": GROQ_MODEL if "groq" in status["chain"] else None,
            "ollama_model": OLLAMA_MODEL, "ollama_host": OLLAMA_HOST,
            # 診斷用：只顯示有沒有讀到、key 的長度和開頭，不會顯示完整 key
            "groq_key_set": bool(os.getenv("GROQ_API_KEY")),
            "groq_key_len": len(os.getenv("GROQ_API_KEY") or ""),
            "groq_key_head": (os.getenv("GROQ_API_KEY") or "")[:4],
            "env_groq_names": [repr(k) for k in os.environ if "GROQ" in k.upper()]}