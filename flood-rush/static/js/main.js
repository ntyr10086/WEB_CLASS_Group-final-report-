// 淹水大作戰：颱風夜救援隊 — 大廳、HUD、災情單、開場、結算
const socket = io();
const $ = (id) => document.getElementById(id);
const ASSET = "/static/assets/";
const ITEM_FILES = {
  bag: "Bag", sandbag: "MoneyBag", rake: "Hoe", gloves: "Interact", ring: "Calamari", axe: "Axe",
  motor: "BarIron", hose: "Scroll", pump: "WateringCan", trash: "Rock", heart: "Heart", coin: "GoldCoin",
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
const recipeHtml = (type, count, card = false) => `<div class="recipe-line">${((card && CARD_STEPS[type]) || RECIPES[type].steps).map((t) =>
  t.startsWith("i:") ? icon(t.slice(2)) : t.startsWith("p:") ? `<span class="place">${t.slice(2)}</span>` :
  t === "×3" && count ? `<span class="arr">×${count}</span>` : `<span class="arr">${t}</span>`).join("")}</div>`;
const NAMES = { breach: "堤防破洞", drain: "排水溝堵塞", electric: "電箱冒火花", house_flood: "民宅淹水", trapped: "居民受困", tree: "大樹倒下" };
const manualHtml = () => Object.keys(RECIPES).map((k) =>
  `<div class="manual-item"><b>${NAMES[k]}</b>${recipeHtml(k)}</div>`).join("");
document.getElementById("manual-list").innerHTML = manualHtml();
document.getElementById("intro-manual").innerHTML = manualHtml();
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
}
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
document.getElementById("btn-settings").onclick = () => openModal("settings");
document.getElementById("btn-settings-lobby").onclick = () => openModal("settings");
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
  $("need-tutorial").classList.toggle("hidden", tutorialDone());
  $("team-up").classList.toggle("hidden", !tutorialDone());
}
refreshGate();
if (!localStorage.getItem("fr-seen-about")) { openModal("about"); localStorage.setItem("fr-seen-about", "1"); }
$("btn-first-tutorial").onclick = () => { soloTutorial = true; socket.emit("create_room", { name: myName() }); };
$("btn-replay-tutorial").onclick = $("btn-first-tutorial").onclick;
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
  MAP = d.map;
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

// ── 開場：AI 颱風劇本 ──────────────────────────────────────
let introTimer = null;
socket.on("intro", (d) => {
  MAP = d.map;
  ensureGame();
  $("lobby").classList.add("hidden");
  $("result").classList.add("hidden");
  $("game-wrap").classList.remove("hidden");
  $("intro").classList.remove("hidden");
  $("intro-name").textContent = d.scenario.name;
  $("intro-story").textContent = d.scenario.story;
  $("intro-by").textContent = d.scenario.by === "ai" ? "AI 災難導演生成" : "";
  let n = d.seconds;
  $("intro-count").textContent = n;
  clearInterval(introTimer);
  introTimer = setInterval(() => { n -= 1; $("intro-count").textContent = Math.max(n, 1); }, 1000);
});

socket.on("intro_map", (m) => { MAP = m; });

socket.on("game_start", (s) => {
  clearInterval(introTimer);
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
  $("hud-phase").textContent = s.phase;
  $("hud-phase").dataset.phase = s.phase;
  $("hud-coins").textContent = s.coins;
  $("hud-hearts").innerHTML = Array.from({ length: 5 }, (_, i) => icon("heart", i < s.hearts ? "" : "lost")).join("");
  document.body.classList.toggle("danger", s.level >= 75 && playing);

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
    el.querySelector(".card-badge").textContent =
      i.state === "pumping" ? "抽水中" : i.state === "escort" ? "護送中" : i.type === "breach" ? `${i.count}/${i.need_count}` : RECIPES[i.type].badge;
  });
}
let lastTutStep = 0;
function updateTutorial(tu) {
  const box = $("tutorial");
  $("tut-skip").classList.toggle("hidden", !tutorialDone());   // 第一次一定要走完
  box.classList.toggle("hidden", !tu || !playing);
  if (!tu) { lastTutStep = 0; return; }
  if (tu.step !== lastTutStep) {
    lastTutStep = tu.step;
    $("tut-step").textContent = `${tu.step}/${tu.total}`;
    $("tut-text").textContent = tu.text;
    box.classList.remove("pop"); void box.offsetWidth; box.classList.add("pop");
  }
}


// 第一次解除某類災情時，畫面下方顯示對應的真實防災知識（6 秒，不出聲）
let tipTimer = null;
function showTip(tip) {
  const box = $("tip-ticker");
  $("tip-text").textContent = `${tip.name}｜${tip.text}`;
  box.classList.remove("hidden");
  box.style.animation = "none"; void box.offsetWidth; box.style.animation = "";
  clearTimeout(tipTimer);
  tipTimer = setTimeout(() => box.classList.add("hidden"), 6000);
}

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
  $("result-title").textContent = r.win ? "颱風過境，小鎮撐住了！" : "小鎮失守了……";
  $("result-scenario").textContent = r.scenario;
  $("result-stars").innerHTML = Array.from({ length: 3 }, (_, i) => `<span class="${i < r.stars ? "on" : ""}">★</span>`).join("");
  $("result-stats").innerHTML =
    `<span>${icon("coin")}<b>${r.coins}</b></span><span>解除 <b>${r.fixed}</b> 件</span>` +
    `<span>失敗 <b>${r.failed}</b> 件</span><span>${icon("heart")}<b>${r.hearts}</b></span>`;
  $("result-players").innerHTML = r.players.map((p) =>
    `<li>${face(p.skin)}<span>${escapeHtml(p.name)}</span><span class="hint">治災 ${p.fixed}・運送 ${p.items}</span>` +
    `<span class="title">${p.title}</span></li>`).join("");
  $("result-report").textContent = "AI 講評生成中…";
  $("tip-ticker").classList.add("hidden");
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
