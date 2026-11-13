// 災變大作戰：災難救援隊 — 大廳、HUD、災情單、開場、結算
const socket = io();
const $ = (id) => document.getElementById(id);
const ASSET = "/static/assets/";
const ITEM_FILES = {
  bag: "Bag", sandbag: "MoneyBag", rake: "Hoe", gloves: "Interact", ring: "Calamari", axe: "Axe",
  motor: "BarIron", hose: "Scroll", pump: "WateringCan", trash: "Rock", heart: "Heart", coin: "GoldCoin",
  // 熱浪
  bucket: "EmptyPot", water: "WaterBucket", sickle: "Sickle", extinguisher: "Extinguisher", drink: "WaterPot",
  towel: "ScrollIce", branch: "Branch",
  // 土石流
  shovel: "Shovel", pickaxe: "Pickaxe", hammer: "Hammer", tape: "ScrollThunder", stake: "Branch", wire: "BarSilver",
  fence: "CrateEmpty", rubble: "Rock",
  hand: "Hand",          // 空手就能處理
};
const icon = (item, cls = "") => `<img class="px ${cls}" src="${ASSET}items/${ITEM_FILES[item]}.png" alt="">`;
const face = (skin) => `<img class="px face" src="${ASSET}chars/${skin}_face.png" alt="">`;

// 每種災情的「食譜」：要準備什麼 → 在哪裡加工 → 怎麼處理
const RECIPES = {
  breach: { badge: "放下", steps: ["i:bag", "→", "p:沙堆", "→", "i:sandbag", "×3"] },
  drain: { badge: "按住", steps: ["i:rake", "→", "p:現場按住", "→", "i:trash", "→", "p:垃圾車"] },
  electric: { badge: "按住", steps: ["i:gloves", "→", "p:現場"] },
  house_flood: { badge: "放下", steps: ["i:motor", "+", "i:hose", "→", "p:工作台", "→", "i:pump"] },
  trapped: { badge: "帶走", steps: ["i:ring", "→", "p:避難所"] },
  tree: { badge: "按住", steps: ["i:axe", "→", "p:現場"] },
};
// 災情單上只放最短的食譜；完整版（含淤泥、成品）放在救災手冊
const CARD_STEPS = {
  drain: ["i:rake", "→", "p:現場"],
  house_flood: ["i:motor", "+", "i:hose", "→", "p:工作台"],
};
// 這局災難的做法（伺服器 map_info.kit.recipes）；還沒拿到時用上面颱風的版本
let curKit = null;                     // 拿到 MAP 之後（refreshManual）換成這局的玩法
const recipeOf = (type) => {
  const k = curKit && curKit.recipes[type];
  return k ? { badge: k.badge, steps: k.steps, card: k.card } : { ...RECIPES[type], card: CARD_STEPS[type] };
};
const recipeHtml = (type, count, card = false) => {
  const r = recipeOf(type);
  return `<div class="recipe-line">${((card && r.card) || r.steps).map((t) =>
    t.startsWith("i:") ? icon(t.slice(2)) : t.startsWith("p:") ? `<span class="place">${t.slice(2)}</span>` :
    t.startsWith("×") && count && t === "×3" ? `<span class="arr">×${count}</span>` : `<span class="arr">${t}</span>`).join("")}</div>`;
};
const NAMES = { breach: "堤防破洞", drain: "排水溝堵塞", electric: "電箱冒火花", house_flood: "民宅淹水", trapped: "居民受困", tree: "大樹倒下" };
// 災情名稱依這局的災難而不同（颱風／熱浪／土石流），從 MAP.incident_names 拿
let manualNames = NAMES;                 // 拿到 MAP 之後換成這局災難的名稱
const incName = (k) => manualNames[k] || NAMES[k];
const manualHtml = () => Object.keys(RECIPES).map((k) =>
  `<div class="manual-item"><b>${incName(k)}</b>${recipeHtml(k)}</div>`).join("");
const refreshManual = () => {
  manualNames = (MAP && MAP.incident_names) || NAMES;
  curKit = (MAP && MAP.kit) || null;
  document.getElementById("manual-list").innerHTML = manualHtml();
};
document.getElementById("manual-list").innerHTML = manualHtml();
const toggleManual = () => document.getElementById("manual").classList.toggle("hidden");
document.getElementById("btn-manual").onclick = toggleManual;
document.getElementById("manual").onclick = toggleManual;
document.addEventListener("keydown", (e) => {
  if ((e.key === "h" || e.key === "H") && !e.target.matches("input")) toggleManual();
});

// ── 聲音設定（存在瀏覽器）─────────────────────────────────
window.AUDIO = Object.assign({ master: 80, music: 60, sfx: 80, ambient: 50, muted: false },
  JSON.parse(localStorage.getItem("fr-audio") || "{}"));
function saveAudio() {
  localStorage.setItem("fr-audio", JSON.stringify(window.AUDIO));
  if (scene && scene.applyAudio) scene.applyAudio();
  updateLobbyMusic();
}

// ── 大廳音樂＋按鈕音效（大廳還沒載入遊戲引擎，用瀏覽器內建的 Audio 播）──────────
// 瀏覽器規定：使用者還沒點過頁面前不能自動出聲，所以先試著播，被擋就等第一次點擊／按鍵再播
const vol01 = (kind) => (window.AUDIO.muted ? 0 : (window.AUDIO.master / 100) * (window.AUDIO[kind] / 100));
const lobbyMusic = new Audio(ASSET + "audio/music_lobby.ogg");
lobbyMusic.loop = true;
let lobbyFade = null;
function lobbyShown() { return !document.getElementById("lobby").classList.contains("hidden"); }
function updateLobbyMusic() {
  clearInterval(lobbyFade);
  const target = 0.5 * vol01("music");
  if (lobbyShown() && target > 0) {
    lobbyMusic.volume = target;
    if (lobbyMusic.paused) lobbyMusic.play().catch(() => {});      // 被瀏覽器擋住就等使用者點一下
  } else if (!lobbyMusic.paused) {                                  // 離開大廳：一秒內慢慢變小聲再停
    lobbyFade = setInterval(() => {
      lobbyMusic.volume = Math.max(0, lobbyMusic.volume - 0.05);
      if (lobbyMusic.volume <= 0.001) { clearInterval(lobbyFade); lobbyMusic.pause(); }
    }, 50);
  }
}
updateLobbyMusic();                                              // 一進來就試著播
// 大廳出現／消失（進遊戲、教學、回大廳）時自動切換
new MutationObserver(updateLobbyMusic).observe(document.getElementById("lobby"), { attributes: true, attributeFilter: ["class"] });
["pointerdown", "keydown", "touchstart"].forEach((ev) =>
  document.addEventListener(ev, () => { if (lobbyShown() && lobbyMusic.paused) updateLobbyMusic(); }, { capture: true }));

// 按鈕音效：一般按鈕「喀」一聲；關閉、離開、退出用比較低的聲音
const uiSounds = { click: ASSET + "audio/ui_click.wav", cancel: ASSET + "audio/ui_cancel.wav" };
let lastUi = 0;
function uiSound(kind) {
  const v = 0.6 * vol01("sfx"), now = performance.now();
  if (v <= 0 || now - lastUi < 60) return;
  lastUi = now;
  const a = new Audio(uiSounds[kind]);
  a.volume = Math.min(1, v);
  a.play().catch(() => {});
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("button, .link-btn");
  if (!b || b.disabled || b.closest(".touch")) return;          // 遊戲中的觸控「拿・放」按鈕不算
  const cancel = b.matches(".modal-close, #btn-leave, #btn-quit, #btn-logout, #tut-skip, [data-del]");
  uiSound(cancel ? "cancel" : "click");
}, { capture: true });
["master", "music", "sfx", "ambient"].forEach((k) => {
  const input = document.getElementById("vol-" + k), out = input.nextElementSibling;
  input.value = window.AUDIO[k]; out.textContent = window.AUDIO[k];
  input.addEventListener("input", () => { window.AUDIO[k] = +input.value; out.textContent = input.value; saveAudio(); });
});
const muteBox = document.getElementById("vol-muted");
muteBox.checked = window.AUDIO.muted;
muteBox.addEventListener("change", () => { window.AUDIO.muted = muteBox.checked; saveAudio(); });
function toggleMute() {
  window.AUDIO.muted = !window.AUDIO.muted; muteBox.checked = window.AUDIO.muted; saveAudio();
  banner(window.AUDIO.muted ? "已靜音（按 M 恢復）" : "已開啟聲音");
}
const openModal = (id) => document.getElementById(id).classList.remove("hidden");
document.querySelectorAll(".modal").forEach((m) => m.addEventListener("click", (e) => {
  if (e.target === m || e.target.classList.contains("modal-close")) m.classList.add("hidden");
}));
document.getElementById("btn-about").onclick = () => openModal("about");
// 遊戲中打開設定才有「退出遊戲」；大廳打開的設定不顯示
document.getElementById("btn-settings").onclick = () => { $("btn-quit").classList.remove("hidden"); resetQuit(); openModal("settings"); };
document.getElementById("btn-settings-lobby").onclick = () => { $("btn-quit").classList.add("hidden"); openModal("settings"); };
// 退出要按兩下確認（不用瀏覽器的 confirm 視窗）
function resetQuit() { const b = $("btn-quit"); delete b.dataset.sure; b.textContent = "退出遊戲，回到大廳"; }
$("btn-quit").onclick = () => {
  const b = $("btn-quit");
  if (!b.dataset.sure) {
    b.dataset.sure = "1"; b.textContent = playing ? "確定退出？這局會少你一個人" : "確定退出？";
    setTimeout(resetQuit, 3000);
    return;
  }
  $("settings").classList.add("hidden");
  quitToLobby();
  socket.emit("leave_room");
};
// 回到大廳：停掉遊戲畫面、音樂、所有劇情框
function quitToLobby() {
  playing = false;
  if (scene) scene.stopAudio();
  if (scene && scene.resultMusic) scene.resultMusic.stop();
  dialogQueue.length = 0;
  ["dialog-toast", "tutorial", "intro", "result", "game-wrap"].forEach((id) => $(id).classList.add("hidden"));
  document.body.classList.remove("danger");
  $("cards").innerHTML = "";
  $("lobby").classList.remove("hidden");
  $("lobby-room").classList.add("hidden");
  $("lobby-join").classList.remove("hidden");
  $("lobby-error").textContent = "";
  refreshGate();
}
document.addEventListener("keydown", (e) => {
  if ((e.key === "m" || e.key === "M") && !e.target.matches("input")) toggleMute();
});

let myId = null;
let MAP = null;
let scene = null;
let playing = false;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── 大廳 ───────────────────────────────────────────────────
$("name").value = localStorage.getItem("fr-name") || "";
function myName() {
  const n = $("name").value.trim() || "隊員" + Math.floor(Math.random() * 100);
  localStorage.setItem("fr-name", n);
  return n;
}
// 新手門檻：完成過教學（存在這台瀏覽器）才能建立或加入隊伍
const tutorialDone = () => localStorage.getItem("fr-tutorial-done") === "1";
let soloTutorial = false;
function refreshGate() {
  const ok = tutorialDone();
  $("btn-create").disabled = !ok;
  $("btn-join").disabled = !ok;
  $("code").disabled = !ok;
  $("play-sub").textContent = ok ? "建立房間，邀朋友一起救災" : "完成新手教學後解鎖";
  $("lock-note").classList.toggle("hidden", ok);
}
// 教學完成紀錄也存在資料庫（依暱稱），換網址、換瀏覽器、換電腦都記得
let checkTimer = null;
function checkTutorialByName() {
  const n = $("name").value.trim();
  if (!n || tutorialDone()) return;
  fetch(`/api/players/${encodeURIComponent(n)}`).then((r) => r.ok ? r.json() : null).then((p) => {
    if (p && p.tutorial_done) { localStorage.setItem("fr-tutorial-done", "1"); refreshGate(); }
  }).catch(() => {});
}
$("name").addEventListener("input", () => { clearTimeout(checkTimer); checkTimer = setTimeout(checkTutorialByName, 400); });
setTimeout(checkTutorialByName, 300);
refreshGate();
$("btn-first-tutorial").onclick = () => { soloTutorial = true; socket.emit("create_room", { name: myName() }); };
$("btn-leave").onclick = () => socket.emit("leave_room");
socket.on("left", () => {
  $("lobby-room").classList.add("hidden");
  $("lobby-join").classList.remove("hidden");
  refreshGate();
});
$("btn-create").onclick = () => socket.emit("create_room", { name: myName() });
$("btn-join").onclick = () => socket.emit("join_room", { code: $("code").value, name: myName() });
$("code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("btn-join").click(); });
$("btn-start").onclick = () => socket.emit("start_game");
$("btn-tutorial").onclick = () => socket.emit("start_tutorial");
$("tut-skip").onclick = () => socket.emit("skip_tutorial");
$("btn-again").onclick = () => socket.emit("start_game");

socket.on("error_msg", (d) => { $("lobby-error").textContent = d.message; });
socket.on("joined", (d) => {
  myId = d.you;
  MAP = d.map; refreshManual();
  $("lobby-join").classList.add("hidden");
  $("lobby-room").classList.remove("hidden");
  $("room-code").textContent = d.code;
  ensureGame();                          // 先載入素材，開始時就不用等
  if (soloTutorial) { soloTutorial = false; socket.emit("start_tutorial"); }   // 第一次玩：直接進教學
});
socket.on("room_update", (info) => {
  const isHost = info.host === myId;
  $("player-list").innerHTML = info.players.map((p) =>
    `<li>${face(p.skin)}<span>${escapeHtml(p.name)}</span>` +
    (p.facility && SHOP.items[p.facility] ? `<span class="fac-chip">${icon2(SHOP.items[p.facility].icon)}${SHOP.items[p.facility].name}</span>` : "") +
    `<span class="tag">${p.id === info.host ? "房主" : ""}${p.id === myId ? "　你" : ""}</span></li>`).join("");
  $("btn-start").classList.toggle("hidden", !isHost || info.status !== "waiting" || !tutorialDone());
  $("btn-tutorial").classList.toggle("hidden", !isHost || info.status !== "waiting");
  $("wait-host").classList.toggle("hidden", isHost);
  $("btn-again").classList.toggle("hidden", !isHost || info.status !== "finished");
  $("wait-again").classList.toggle("hidden", isHost);
});

// ── Phaser ─────────────────────────────────────────────────
function ensureGame() {
  if (window.phaserGame) return;
  window.phaserGame = new Phaser.Game({
    type: Phaser.AUTO, parent: "game", width: 384, height: 256, pixelArt: true, backgroundColor: "#7fae5d",
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_HORIZONTALLY },
    scene: FloodScene,
  });
}

// ── 開場劇情：這局的災難故事，一句一句看完再出發 ─────────────
const FACES = { "氣象主播": "Woman", "鎮長": "OldMan", "阿嬤": "OldWoman", "小宇": "Child", "村民": "Villager" };
const faceSrc = (speaker) => `${ASSET}chars/${FACES[speaker] || "Villager"}_face.png`;
let story = [], storyIdx = 0, typing = null, storyDone = false;

const LOADING_LINES = [
  "救援隊集合中", "正在把沙包裝滿沙", "鎮長在找他的雨鞋", "阿嬤在幫貓咪穿雨衣",
  "小宇在練習跑步", "檢查抽水機有沒有漏油", "把救生圈吹得鼓鼓的", "氣象主播在看天氣圖…",
  "今天會是什麼災難呢…",
];
let loadingTimer = null;
function stopLoading() {
  clearInterval(loadingTimer);
  $("intro").classList.remove("loading");
  $("intro-loading").classList.add("hidden");
}
socket.on("intro_loading", () => {
  ensureGame();
  $("lobby").classList.add("hidden");
  $("result").classList.add("hidden");
  $("game-wrap").classList.remove("hidden");
  $("intro").classList.remove("hidden");
  $("intro").classList.add("loading");
  $("intro-loading").classList.remove("hidden");
  $("story-actions").classList.add("hidden");
  const lines = [...LOADING_LINES].sort(() => Math.random() - 0.5);
  let i = 0;
  $("loading-line").textContent = lines[0];
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => { i = (i + 1) % lines.length; $("loading-line").textContent = lines[i]; }, 1400);
});

socket.on("intro", (d) => {
  stopLoading();
  MAP = d.map; refreshManual();
  const sc = d.scenario, dis = MAP.disaster || {};
  $("intro-name").textContent = sc.name;
  $("intro-disaster").textContent = dis.name || "";
  document.body.dataset.disaster = dis.key || "typhoon";
  if (scene && scene.previewLook) scene.previewLook();
  if (dis.meter) $("hud-meter").textContent = dis.meter;
  if (dis.phases) $("hud-phase").textContent = dis.phases["小雨"];
  $("intro-news").textContent = `${dis.event || "颱風"}新聞快報`;
  $("intro-headline").textContent = sc.headline || "";
  $("intro-by").textContent = "";                // 畫面上不顯示劇情是誰寫的
  story = sc.story || [];
  storyIdx = -1; storyDone = false;
  $("ready-status").textContent = "";
  $("btn-ready").disabled = false;
  nextLine();
});

function nextLine() {
  if (typing) {                                   // 正在打字 → 先顯示整句
    clearInterval(typing); typing = null;
    $("story-line").textContent = story[storyIdx].line;
    return;
  }
  if (storyDone) return;
  storyIdx += 1;
  if (storyIdx >= story.length) return;
  const { speaker, line } = story[storyIdx];
  $("story-speaker").textContent = speaker;
  $("story-face").src = faceSrc(speaker);
  $("story-line").textContent = "";
  let i = 0;
  typing = setInterval(() => {                    // 打字機效果
    i += 1;
    $("story-line").textContent = line.slice(0, i);
    if (i >= line.length) { clearInterval(typing); typing = null; }
  }, 35);
  const last = storyIdx === story.length - 1;
  $("story-next").classList.toggle("hidden", last);
  $("story-actions").classList.toggle("hidden", !last);
  if (last) storyDone = true;
}
$("story-box").addEventListener("click", (e) => { if (!e.target.closest("button")) nextLine(); });
document.addEventListener("keydown", (e) => {
  if ($("intro").classList.contains("hidden") || e.target.matches("input")) return;
  if (e.key === " " || e.key === "Enter") {
    e.preventDefault();
    if (storyDone && !typing) $("btn-ready").click(); else nextLine();
  }
});
$("btn-ready").onclick = () => {
  $("btn-ready").disabled = true;
  socket.emit("intro_ready");
  $("ready-status").textContent = "等待隊友看完劇情…";
};
socket.on("intro_status", (d) => { $("ready-status").textContent = `已準備 ${d.ready}/${d.total}`; });

socket.on("intro_map", (m) => { MAP = m; refreshManual(); });

socket.on("game_start", (s) => {
  dialogQueue.length = 0;
  ensureGame();
  $("lobby").classList.add("hidden");
  $("result").classList.add("hidden");
  $("intro").classList.add("hidden");
  $("game-wrap").classList.remove("hidden");
  playing = true;
  if (scene && scene.sys.isActive()) scene.startRound(s);
  else window.pendingState = s;
  banner(s.mode === "tutorial" ? "新手教學：照著下方的提示做" : "救援開始！看上方的災情單");
});

socket.on("tutorial_done", (d) => {
  if (d && d.completed) localStorage.setItem("fr-tutorial-done", "1");
  refreshGate();
  playing = false;
  if (scene) { scene.stopAudio(); scene.sfx("success", 0.5); }
  $("tutorial").classList.add("hidden");
  setTimeout(() => {
    $("game-wrap").classList.add("hidden");
    $("lobby").classList.remove("hidden");
    $("lobby-error").textContent = "";
  }, 1200);
});

socket.on("state_sync", (s) => { if (scene && scene.state !== undefined) scene.applyState(s); });

// ── HUD 與災情單 ───────────────────────────────────────────
function updateHud(s) {
  const t = Math.ceil(s.time_left), tut = s.mode === "tutorial";
  $("hud-time").textContent = tut ? "教學中" : `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  $("hud-time").classList.toggle("warn", !tut && t <= 30);
  updateTutorial(s.tutorial);
  $("hud-water-fill").style.width = `${s.level}%`;
  $("hud-water").textContent = `${Math.round(s.level)}%`;
  $("hud-phase").textContent = s.phase_label || s.phase;
  $("hud-phase").dataset.phase = s.phase;
  document.body.dataset.disaster = s.disaster || "typhoon";      // 換災難：計量條名稱、顏色
  $("hud-meter").textContent = (MAP && MAP.disaster && MAP.disaster.meter) || "水位";
  $("hud-coins").textContent = s.coins;
  $("hud-hearts").innerHTML = Array.from({ length: s.max_hearts || 5 }, (_, i) => icon("heart", i < s.hearts ? "" : "lost")).join("");
  document.body.classList.toggle("danger", s.level >= 75 && playing);
  updateStoryTask(s.chapter);

  const cards = $("cards");
  if (!playing) { cards.innerHTML = ""; return; }
  const ids = new Set(s.incidents.map((i) => i.id));
  [...cards.children].forEach((el) => { if (!ids.has(el.dataset.id)) el.remove(); });
  s.incidents.forEach((i) => {
    let el = cards.querySelector(`[data-id="${i.id}"]`);
    if (!el) {
      el = document.createElement("div");
      el.className = "card new";
      el.dataset.id = i.id;
      el.innerHTML = `<div class="card-top"><span class="card-name"></span><span class="card-badge"></span></div>
        ${recipeHtml(i.type, i.need_count, true)}
        <div class="card-bar"><div></div></div>`;
      el.querySelector(".card-name").textContent = MAP.incident_names[i.type];
      cards.appendChild(el);
      const line = pendingLines[i.id] || i.line;
      if (line) {
        const say = document.createElement("div");
        say.className = "card-say";
        say.textContent = line;
        el.appendChild(say);
        setTimeout(() => say.remove(), 3500);
        delete pendingLines[i.id];
      }
      setTimeout(() => el.classList.remove("new"), 400);
    }
    const ratio = Math.max(0, i.timer / i.max_timer);
    el.querySelector(".card-bar div").style.width = `${(i.state === "pumping" ? 1 : ratio) * 100}%`;
    el.classList.toggle("urgent", ratio < 0.3 && i.state === "active");
    el.classList.toggle("ok", i.state === "pumping" || i.state === "escort");
    el.classList.toggle("story", !!i.story);           // 這一章劇情任務要處理的災情
    el.querySelector(".card-badge").textContent =
      i.state === "pumping" ? "抽水中" : i.state === "escort" ? "護送中" :
      i.need_count > 1 ? `${i.count}/${i.need_count}` :
      Array.isArray(i.need) ? `${(i.given || []).length}/${i.need.length}` :
      i.team > 1 ? `${i.workers}/${i.team} 人` : recipeOf(i.type).badge;
  });
}
// 劇情任務（右上角）：這一章誰交代了什麼事、做了幾件
let lastTask = "";
function updateStoryTask(ch) {
  const box = $("story-task");
  box.classList.toggle("hidden", !ch || !playing);
  if (!ch) { lastTask = ""; return; }
  const key = `${ch.title}|${ch.done}|${ch.status}`;
  if (key === lastTask) return;
  const changed = lastTask && lastTask.split("|")[0] === ch.title;
  lastTask = key;
  $("task-face").src = faceSrc(ch.speaker);
  $("task-title").textContent = ch.title;
  $("task-goal").textContent = ch.goal_text;
  $("task-count").textContent = ch.status === "done" ? "完成！" : ch.status === "failed" ? "沒做到" : `${ch.done}/${ch.need}`;
  box.classList.toggle("done", ch.status === "done");
  box.classList.toggle("failed", ch.status === "failed");
  if (changed || !box.classList.contains("pop")) { box.classList.remove("pop"); void box.offsetWidth; box.classList.add("pop"); }
}

let lastTutStep = 0;
function updateTutorial(tu) {
  const box = $("tutorial");
  $("tut-skip").classList.toggle("hidden", !tutorialDone());   // 第一次一定要走完
  box.classList.toggle("hidden", !tu || !playing);
  if (!tu) { lastTutStep = 0; return; }
  if (tu.step !== lastTutStep) {
    lastTutStep = tu.step;
    if ($("tut-step")) $("tut-step").textContent = `${tu.step}/${tu.total}`;   // 步驟編號已從畫面拿掉
    $("tut-text").textContent = tu.text;
    $("tut-speaker").textContent = tu.speaker || "鎮長";
    $("tut-face").src = faceSrc(tu.speaker || "鎮長");
    box.classList.remove("pop"); void box.offsetWidth; box.classList.add("pop");
  }
}


// 遊戲中的角色對話：天氣轉變、第一次解除某類災情時，由劇情角色說出來（排隊，一次一句）
const dialogQueue = [];
let dialogBusy = false;
function showDialogue(d) {
  if (!$("tutorial").classList.contains("hidden")) return;   // 教學框已經在講話，不再疊一個對話框
  dialogQueue.push(d);
  if (!dialogBusy) playDialogue();
}
function playDialogue() {
  const d = dialogQueue.shift(), box = $("dialog-toast");
  if (!d || !playing) { dialogBusy = false; box.classList.add("hidden"); return; }
  dialogBusy = true;
  $("toast-face").src = faceSrc(d.speaker);
  $("toast-speaker").textContent = d.speaker;
  $("toast-line").textContent = d.line;
  box.classList.remove("hidden");
  box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
  setTimeout(playDialogue, Math.min(8500, 3200 + d.line.length * 100));
}
function showTip(tip) {
  showDialogue({ speaker: "鎮長", line: `${tip.name}解除了，做得好！記住：${tip.text}` });
}
socket.on("dialogue", (d) => showDialogue(d));

let bannerTimer = null;
function banner(msg) {
  const b = $("banner");
  b.textContent = msg;
  b.classList.remove("hidden");
  b.style.animation = "none"; void b.offsetWidth; b.style.animation = "";
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => b.classList.add("hidden"), 2400);
}

// ── 遊戲事件 ───────────────────────────────────────────────
socket.on("banner", (d) => { banner(d.message); if (scene) scene.sfx("alert", 0.4); });

socket.on("incident_new", (d) => {
  if (!scene) return;
  scene.sfx("alert", 0.25);
  scene.ping(d.x, d.y);
  pendingLines[d.id] = d.line;          // 台詞顯示在災情單下方，3.5 秒後消失
});
const pendingLines = {};

socket.on("fx", (d) => {
  // 完成任務只跳一個「+金幣」，其餘用音效表示，避免畫面塞滿字
  if (!scene) return;
  const S = scene;
  switch (d.type) {
    // 完成任務只響一聲金幣；教學換步、做出東西、開始按住都不出聲
    case "pick": S.sfx("pick", 0.3); break;
    case "drop": case "bag": S.sfx("drop", 0.3); break;
    case "pump": S.sfx("water", 0.3); break;
    case "coin": S.sfx("coin", 0.4); S.coinPop(d.x, d.y, d.coins); S.floatText(d.x, d.y, `+${d.coins}`, "#ffd166"); break;
    case "fixed":
      S.sfx("coin", 0.45); S.coinPop(d.x, d.y, d.coins); S.floatText(d.x, d.y - 16, `+${d.coins}`, "#ffd166");
      if (d.tip) showTip(d.tip);
      break;
    case "failed": S.sfx("hit", 0.6); S.cameras.main.shake(150, 0.003); S.floatText(d.x, d.y - 16, "來不及了", "#ffadad"); break;
  }
});

socket.on("stun", (d) => {
  if (!scene) return;
  scene.sfx("hit", 0.5);
  scene.floatText(d.x, d.y - 16, "要戴手套！", "#ffd166");
  if (d.id === myId) scene.cameras.main.shake(150, 0.003);
});

socket.on("ping_marker", (d) => { if (scene) scene.ping(d.x, d.y); });

// ── 結算 ───────────────────────────────────────────────────
socket.on("game_over", (r) => {
  playing = false;
  document.body.classList.remove("danger");
  $("cards").innerHTML = "";
  if (scene) { scene.stopAudio(true); scene.sfx(r.win ? "success" : "gameover", 0.5); }
  $("result-title").textContent = r.win ? (r.win_title || "小鎮撐住了！") : "小鎮失守了……";
  $("result-scenario").textContent = r.scenario;
  $("result-stars").innerHTML = Array.from({ length: 3 }, (_, i) => `<span class="${i < r.stars ? "on" : ""}">★</span>`).join("");
  $("result-stats").innerHTML =
    `<span>${icon("coin")}<b>${r.coins}</b></span><span>解除 <b>${r.fixed}</b> 件</span>` +
    `<span>失敗 <b>${r.failed}</b> 件</span><span>${icon("heart")}<b>${r.hearts}</b></span>`;
  $("result-players").innerHTML = r.players.map((p) =>
    `<li>${face(p.skin)}<span>${escapeHtml(p.name)}</span><span class="hint">治災 ${p.fixed}・運送 ${p.items}・防災基金 +${p.earned || 0}</span>` +
    `<span class="title">${p.title}</span></li>`).join("") +
    (r.facilities && r.facilities.length ? `<li class="fac-used">這局帶的防災建設：${r.facilities.map(escapeHtml).join("、")}</li>` : "");
  $("result-report").textContent = "鎮長正在想要說什麼…";
  $("result-story").innerHTML = (r.chapters || []).map((c) =>
    `<li class="${c.status}"><span class="ch-mark">${c.status === "done" ? "✓" : "✗"}</span>` +
    `<div><b>${escapeHtml(c.title)}</b><span class="ch-theme">${escapeHtml(c.theme)}</span><br>` +
    `<img class="px face" src="${faceSrc(c.speaker)}" alt="">${escapeHtml(c.speaker)}：${escapeHtml(c.line)}</div></li>`).join("")
    || "<li>這局還沒開始說故事。</li>";
  dialogQueue.length = 0; $("dialog-toast").classList.add("hidden");
  $("result-lessons").innerHTML = (r.lessons || []).map((l) =>
    `<li><b>${l.name}</b>　<span class="tag-ok">解除 ${l.fixed}</span>${l.failed ? `　<span class="tag-bad">失敗 ${l.failed}</span>` : ""}<br>${escapeHtml(l.text)}</li>`)
    .join("") || "<li>這局還沒遇到災情。</li>";
  $("leaderboard").innerHTML = "";
  $("result").classList.remove("hidden");
});

socket.on("report_ready", (d) => {
  $("result-report").textContent = d.report;
  fetch("/api/leaderboard").then((res) => res.json()).then((rows) => {
    $("leaderboard").innerHTML = rows.map((x) =>
      `<li><span>${escapeHtml(x.team)}</span><span>${x.score} 金幣 ${"★".repeat(x.stars)}</span></li>`).join("") || "<li>還沒有紀錄</li>";
  });
});

// ── 觸控操作：虛擬搖桿 + 拿放鍵（按住＝處理災情）────────────────
window.touchDir = { x: 0, y: 0 };
(function setupTouch() {
  const joy = $("joy"), knob = $("knob");
  let active = null;
  const move = (e) => {
    const r = joy.getBoundingClientRect(), R = r.width / 2;
    let dx = e.clientX - (r.left + R), dy = e.clientY - (r.top + R);
    const len = Math.hypot(dx, dy);
    if (len > R) { dx = dx / len * R; dy = dy / len * R; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const dead = R * 0.25;                       // 中間一小圈不算移動
    window.touchDir = len < dead ? { x: 0, y: 0 } : { x: dx / R, y: dy / R };
  };
  const end = () => { active = null; knob.style.transform = ""; window.touchDir = { x: 0, y: 0 }; };
  joy.addEventListener("pointerdown", (e) => { active = e.pointerId; joy.setPointerCapture(e.pointerId); move(e); });
  joy.addEventListener("pointermove", (e) => { if (e.pointerId === active) move(e); });
  ["pointerup", "pointercancel"].forEach((t) => joy.addEventListener(t, (e) => { if (e.pointerId === active) end(); }));

  const act = $("t-act");
  const down = (e) => { e.preventDefault(); act.classList.add("down"); window.actHeld = true; if (playing) socket.emit("act"); };
  const up = () => { if (!act.classList.contains("down")) return; act.classList.remove("down"); window.actHeld = false; if (playing) socket.emit("act_end"); };
  act.addEventListener("pointerdown", down);
  ["pointerup", "pointercancel", "pointerleave"].forEach((t) => act.addEventListener(t, up));
  $("t-ping").addEventListener("pointerdown", (e) => {
    e.preventDefault();
    if (playing && scene) socket.emit("ping_marker", { x: scene.me.x, y: scene.me.y });
  });
  document.addEventListener("contextmenu", (e) => { if (e.target.closest(".touch")) e.preventDefault(); });
})();

// ── 帳號：登入／註冊、我的紀錄、好友 ───────────────────────────
// 帳號名就是遊戲暱稱；登入後暱稱鎖定，每局紀錄會記在帳號底下。不登入也能用訪客玩。
let ME = null;
const api = (url, opt = {}) => fetch(url, {
  method: opt.method || "GET", credentials: "same-origin",
  headers: opt.body ? { "Content-Type": "application/json" } : {},
  body: opt.body ? JSON.stringify(opt.body) : undefined,
}).then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }));

function setMe(user) {
  ME = user;
  const btn = $("btn-account");
  btn.textContent = ME ? `${ME.name} 的隊員證` : "登入／註冊";
  btn.classList.toggle("logged", !!ME);
  if (ME) { $("name").value = ME.name; localStorage.setItem("fr-name", ME.name); }
  $("name").readOnly = !!ME;
  checkTutorialByName();
}
// 登入狀態改變後重新連線，伺服器才知道這條連線是誰（只在大廳做）
function reconnectSocket() {
  if (!$("lobby-room").classList.contains("hidden")) return;
  socket.disconnect(); socket.connect();
}
api("/api/me").then(({ data }) => setMe(data.user || null));

$("btn-account").onclick = () => {
  if (!ME) { $("auth-error").textContent = ""; $("auth").classList.remove("hidden"); $("auth-name").focus(); return; }
  openAccount();
};
async function doAuth(kind) {
  const body = { name: $("auth-name").value.trim(), password: $("auth-pw").value };
  if (!body.name || !body.password) { $("auth-error").textContent = "帳號和密碼都要填"; return; }
  const { ok, data } = await api(`/api/${kind}`, { method: "POST", body });
  if (!ok) { $("auth-error").textContent = data.error || "出了點問題，再試一次"; return; }
  $("auth-pw").value = "";
  $("auth").classList.add("hidden");
  setMe(data.user);
  reconnectSocket();
}
$("btn-login").onclick = () => doAuth("login");
$("btn-register").onclick = () => doAuth("register");
$("auth-pw").addEventListener("keydown", (e) => { if (e.key === "Enter") doAuth("login"); });
$("btn-logout").onclick = async () => {
  if (!$("lobby-room").classList.contains("hidden")) { $("friend-msg").textContent = "先離開房間再登出"; return; }
  await api("/api/logout", { method: "POST" });
  $("account").classList.add("hidden");
  setMe(null);
  reconnectSocket();
};

// 我的隊員證
function openAccount(tab = "records") {
  $("acc-name").textContent = ME.name;
  $("acc-code").textContent = ME.friend_code;
  $("friend-msg").textContent = "";
  showTab(tab);
  $("account").classList.remove("hidden");
}
function showTab(tab) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === tab));
  $("tab-records").classList.toggle("hidden", tab !== "records");
  $("tab-friends").classList.toggle("hidden", tab !== "friends");
  if (tab === "records") loadMyRecords(); else loadFriends();
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });
$("btn-copy-code").onclick = () => {
  navigator.clipboard?.writeText(ME.friend_code).then(() => { $("btn-copy-code").textContent = "已複製"; });
  setTimeout(() => { $("btn-copy-code").textContent = "複製"; }, 1500);
};

const DIS_NAMES = { typhoon: "颱風淹水", heatwave: "熱浪野火", landslide: "豪雨土石流" };
function recordsHtml(list) {
  if (!list.length) return `<li class="empty">還沒有紀錄，快去救災吧！</li>`;
  return list.map((r) => {
    const d = r.disaster || "typhoon", when = r.played_at ? new Date(r.played_at) : null;
    return `<li><div class="r-top"><span class="r-dis ${d}">${r.disaster_name || DIS_NAMES[d]}</span>` +
      `<span class="${r.result === "win" ? "r-win" : "r-lose"}">${r.result === "win" ? "撐住了" : "失守"}</span>` +
      `<span class="r-stars">${"★".repeat(r.stars || 0)}${"☆".repeat(3 - (r.stars || 0))}</span>` +
      `<span>${r.score} 金幣</span>` +
      `<span class="when">${when ? `${when.getMonth() + 1}/${when.getDate()} ${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}` : ""}</span></div>` +
      `<div class="r-sub">${escapeHtml(r.scenario || "")}・隊友：${escapeHtml(r.team || "")}・解除 ${r.fixed} 件</div></li>`;
  }).join("");
}
async function loadMyRecords() {
  $("acc-records").innerHTML = `<li class="empty">讀取中…</li>`;
  const { ok, data } = await api("/api/me/records");
  if (!ok) { $("acc-records").innerHTML = `<li class="empty">${data.error || "讀取失敗"}</li>`; return; }
  const s = data.stats || {};
  $("acc-stats").innerHTML = [["場數", s.games || 0], ["撐住", s.wins || 0], ["最高金幣", s.best_score || 0], ["最多星", s.best_stars || 0]]
    .map(([k, v]) => `<div><b>${v}</b><small>${k}</small></div>`).join("");
  $("acc-records").innerHTML = recordsHtml(data.records || []);
}

async function loadFriends() {
  const { ok, data } = await api("/api/friends");
  if (!ok) { $("friend-list").innerHTML = `<li class="empty">${data.error || "讀取失敗"}</li>`; return; }
  if (!data.length) { $("friend-list").innerHTML = `<li class="empty">還沒有好友。把你的好友碼給朋友，或輸入朋友的好友碼！</li>`; return; }
  const inRoom = !$("lobby-room").classList.contains("hidden");
  $("friend-list").innerHTML = data.map((f) => {
    const where = !f.online ? "離線" : f.room && f.room.code ? `在房間 ${f.room.code} 等人` :
      f.room ? "正在救災中" : "在大廳";
    const join = f.room && f.room.code && !inRoom ? `<button class="mini-btn" data-join="${f.room.code}">加入</button>` : "";
    return `<li><span class="dot ${f.online ? "on" : ""}"></span>` +
      `<span><span class="f-name">${escapeHtml(f.name)}</span><br><span class="f-sub">${where}・${f.games} 場・撐住 ${f.wins} 場・最高 ${f.best_score}</span></span>` +
      `<span class="f-act">${join}<button class="mini-btn" data-rec="${escapeHtml(f.name)}">紀錄</button>` +
      `<button class="mini-btn" data-del="${escapeHtml(f.name)}">刪除</button></span>` +
      `<ul class="record-list f-records" data-for="${escapeHtml(f.name)}"></ul></li>`;
  }).join("");
}
$("friend-list").onclick = async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.join) {
    $("account").classList.add("hidden");
    $("code").value = b.dataset.join;
    if ($("btn-join").disabled) { $("lobby-error").textContent = "先完成新手教學才能加入房間"; return; }
    $("btn-join").click();
  } else if (b.dataset.rec) {
    const box = [...document.querySelectorAll(".f-records")].find((u) => u.dataset.for === b.dataset.rec);
    if (box.innerHTML) { box.innerHTML = ""; return; }
    const { ok, data } = await api(`/api/friends/${encodeURIComponent(b.dataset.rec)}/records`);
    box.innerHTML = ok ? recordsHtml(data.records || []) : `<li class="empty">${data.error}</li>`;
  } else if (b.dataset.del) {
    if (!confirmDelete(b)) return;
    await api(`/api/friends/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
    loadFriends();
  }
};
// 刪除要按兩下（不用瀏覽器的 confirm 視窗）
function confirmDelete(b) {
  if (b.dataset.sure) return true;
  b.dataset.sure = "1"; b.textContent = "確定刪除？";
  setTimeout(() => { delete b.dataset.sure; b.textContent = "刪除"; }, 2500);
  return false;
}
$("btn-add-friend").onclick = async () => {
  const code = $("friend-code").value.trim().toUpperCase();
  if (!code) return;
  const { ok, data } = await api("/api/friends", { method: "POST", body: { code } });
  $("friend-msg").textContent = ok ? "" : data.error;
  $("friend-msg").style.color = ok ? "var(--accent)" : "";
  if (ok) { $("friend-code").value = ""; $("friend-msg").textContent = `已經和 ${data.name} 成為好友！`; loadFriends(); }
};
$("friend-code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("btn-add-friend").click(); });


// ── 局間防災建設：用防災基金蓋建設，每局開始前每人選一樣帶進場 ──────────
const SHOP = { items: {}, fund: 0, owned: [], equipped: null };
const icon2 = (file) => `<img class="px" src="${ASSET}items/${file}.png" alt="">`;
function renderShop() {
  $("shop-fund").textContent = SHOP.fund;
  $("shop-list").innerHTML = Object.entries(SHOP.items).map(([id, it]) => {
    const own = SHOP.owned.includes(id), on = SHOP.equipped === id;
    const btn = !own ? `<button data-buy="${id}" ${SHOP.fund < it.price ? "disabled" : ""}>蓋　${it.price} 金幣</button>`
      : on ? `<button data-equip="" class="on">帶著中 ✓</button>` : `<button data-equip="${id}">這局帶這個</button>`;
    return `<li class="${own ? "own" : ""} ${on ? "on" : ""}">${icon2(it.icon)}<div><b>${it.name}</b>` +
      `<span class="fac-desc">${it.desc}</span><span class="fac-why">${it.why}</span></div>${btn}</li>`;
  }).join("");
}
function openShop() { $("shop-msg").textContent = ""; socket.emit("shop"); renderShop(); openModal("shop"); }
$("btn-shop").onclick = openShop;
$("btn-shop2").onclick = openShop;
socket.on("shop", (d) => {
  if (!d) return;
  SHOP.fund = d.fund; SHOP.owned = d.owned; SHOP.equipped = d.equipped;
  d.items.forEach((it) => { SHOP.items[it.id] = it; });
  if (d.equipped) localStorage.setItem("fr-facility", d.equipped);
  renderShop();
});
socket.on("shop_msg", (d) => {
  $("shop-msg").textContent = d.message;
  $("shop-msg").style.color = d.ok ? "var(--accent)" : "";
});
$("shop-list").onclick = (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  if (b.dataset.buy) socket.emit("buy", { item: b.dataset.buy });
  else if ("equip" in b.dataset) {
    localStorage.setItem("fr-facility", b.dataset.equip || "");
    socket.emit("equip", { item: b.dataset.equip || null });
  }
};
// 進房間：拿防災基金資料，並自動帶上次選的建設
socket.on("joined", () => {
  socket.emit("shop");
  const last = localStorage.getItem("fr-facility");
  if (last) socket.emit("equip", { item: last });
});


// 結算畫面「回到大廳」：離開這個房間，回到大廳（和設定裡的退出遊戲一樣）
$("btn-result-lobby").onclick = () => {
  quitToLobby();
  socket.emit("leave_room");
};
