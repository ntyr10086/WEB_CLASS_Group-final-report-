// 淹水大作戰：颱風夜救援隊 — Phaser 場景
// 美術：Ninja Adventure Asset Pack（pixel-boy & AAA，CC0）；字型：俐方體11號 Cubic 11（OFL）
// 用到 main.js 的全域：socket、myId、playing、MAP、ITEM_FILES

const FONT = "Cubic11";
const A = "/static/assets/";
const PLAYER_SKINS = ["NinjaBlue", "NinjaRed", "NinjaGreen", "NinjaYellow"];
const NPC_SKINS = { OldWoman: 2, OldMan: 4, Child: 2, Woman: 4, Villager: 4 };   // 走路動畫有幾格
const COLS = { Field: 5, Floor: 22, House: 33, Nature: 24, Water: 28, Element: 16 };
const F = (sheet, c, r) => r * COLS[sheet] + c;              // 圖塊 (欄, 列) → frame 編號
const SPEED = 64;                                             // 每秒幾個像素
const HOW = { breach: "tap", drain: "hold", electric: "hold", house_flood: "tap", trapped: "tap", tree: "hold" };
const PHASE_LOOK = { "小雨": { dark: 0.12, rain: 2 }, "颱風眼": { dark: 0.03, rain: 0 }, "暴雨": { dark: 0.3, rain: 6 } };

class FloodScene extends Phaser.Scene {
  constructor() { super("flood"); }

  preload() {
    Object.keys(COLS).forEach((n) =>
      this.load.spritesheet("t" + n, `${A}tiles/Tileset${n}.png`, { frameWidth: 16, frameHeight: 16 }));
    [...PLAYER_SKINS, ...Object.keys(NPC_SKINS)].forEach((s) =>
      this.load.spritesheet(s, `${A}chars/${s}.png`, { frameWidth: 16, frameHeight: 16 }));
    Object.entries(ITEM_FILES).forEach(([k, f]) => this.load.image("i_" + k, `${A}items/${f}.png`));
    this.load.spritesheet("rain", `${A}fx/Rain.png`, { frameWidth: 8, frameHeight: 8 });
    this.load.spritesheet("splash", `${A}fx/RainOnFloor.png`, { frameWidth: 8, frameHeight: 8 });
    this.load.spritesheet("spark", `${A}fx/Spark.png`, { frameWidth: 10, frameHeight: 8 });
    this.load.spritesheet("leaf", `${A}fx/Leaf.png`, { frameWidth: 12, frameHeight: 7 });
    ["rain", "pick", "drop", "coin", "alert", "hit", "water", "slash", "impact", "success", "gameover"].forEach((k) =>
      this.load.audio(k, `${A}audio/${k}.wav`));
    // 依天氣換音樂（每首 32～96 秒，比原本 26 秒的循環長很多，不容易聽到重複）
    ["light", "eye", "storm", "result"].forEach((k) => this.load.audio("music_" + k, `${A}audio/music_${k}.ogg`));
  }

  create() {
    scene = this;
    this.state = null;
    this.objs = { players: {}, incidents: {}, ground: {}, residents: {} };
    this.me = { x: 190, y: 186, dir: 0 };
    this.lastSent = 0;
    this.waterShown = MAP.wall_bottom;
    this.stunUntil = 0;
    this.nextLightning = 0;
    this.addFrames();
    this.makeAnims();
    this.buildWorld();

    this.water = this.add.graphics().setDepth(60);
    this.dark = this.add.rectangle(0, 0, MAP.w, MAP.h, 0x0b1a2b, 0.1).setOrigin(0).setDepth(300);
    this.rain = this.add.particles(0, 0, "rain", {
      frame: 2, x: { min: 0, max: MAP.w + 80 }, y: -8, lifespan: 700,
      speedY: { min: 230, max: 290 }, speedX: { min: -70, max: -50 }, alpha: { start: 0.7, end: 0.3 },
      quantity: 2, frequency: 30,
    }).setDepth(310);
    this.splash = this.add.particles(0, 0, "splash", {
      frame: [0, 1, 2], x: { min: 0, max: MAP.w }, y: { min: 70, max: MAP.h }, lifespan: 260,
      alpha: { start: 0.8, end: 0 }, quantity: 1, frequency: 70,
    }).setDepth(55);

    // 教學箭頭：指向下一步要去的地方
    this.guide = this.add.container(0, 0).setDepth(420).setVisible(false);
    const ring = this.add.circle(0, 0, 10).setStrokeStyle(2, 0xffd166);
    const arrow = this.add.triangle(0, -20, 0, 0, 10, 0, 5, 7, 0xffd166).setStrokeStyle(1, 0x3b2a1e);
    this.guide.add([ring, arrow]);
    this.tweens.add({ targets: ring, scale: 1.8, alpha: 0, duration: 800, repeat: -1 });
    this.tweens.add({ targets: arrow, y: -15, duration: 350, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
    // 頭上的操作提示
    this.hint = this.add.text(0, 0, "", { fontFamily: FONT, fontSize: "11px", color: "#ffffff", backgroundColor: "#3b2a1ee6", padding: { x: 3, y: 1 } })
      .setOrigin(0.5, 1).setDepth(430).setResolution(2).setVisible(false);
    this.lastHint = 0;

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT,SPACE,Q");
    this.keys.SPACE.on("down", () => { if (playing) socket.emit("act"); });
    this.keys.SPACE.on("up", () => { if (playing) socket.emit("act_end"); });
    this.keys.Q.on("down", () => { if (playing) socket.emit("ping_marker", { x: this.me.x, y: this.me.y }); });

    // ── 音樂與雨聲 ──
    this.tracks = {
      "小雨": this.sound.add("music_light", { loop: true }),
      "颱風眼": this.sound.add("music_eye", { loop: true }),
      "暴雨": this.sound.add("music_storm", { loop: true }),
    };
    this.resultMusic = this.sound.add("music_result", { loop: true });
    this.curTrack = null;
    // 雨聲只有 4.5 秒：疊兩層、錯開時間、速度略不同，聽起來就不會一直「同一段」
    this.rainA = this.sound.add("rain", { loop: true, rate: 1 });
    this.rainB = this.sound.add("rain", { loop: true, rate: 0.87 });
    this.rainLevel = 0.6;

    // 音效節流：同一種音效 0.35 秒內只響一次，任何音效之間至少隔 0.12 秒，避免同時疊一堆聲音
    this.lastSfx = {}; this.lastAnySfx = 0;
    this.sfx = (k, vol = 0.5) => {
      const now = this.time.now;
      if (now - (this.lastSfx[k] || -1e9) < 350 || now - this.lastAnySfx < 120) return;
      this.lastSfx[k] = now; this.lastAnySfx = now;
      try { this.sound.play(k, { volume: vol * this.vol("sfx") }); } catch (e) { /* 沒聲音就算了 */ }
    };
    if (window.pendingState) { this.startRound(window.pendingState); window.pendingState = null; }
  }

  addFrames() {   // 多格的物件（房子、樹、推車…）切成自訂 frame
    const add = (tex, name, x, y, w, h) => this.textures.get(tex).add(name, 0, x, y, w, h);
    for (let i = 0; i < 4; i++) add("tHouse", "house" + i, i * 64, 0, 64, 48);
    add("tHouse", "shelter", 26 * 16, 0, 48, 48);
    add("tNature", "tree", 0, 0, 16, 32);
    add("tNature", "log", 12 * 16, 14 * 16, 16, 32);
    add("tElement", "cart", 0, 3 * 16, 32, 32);
  }

  makeAnims() {
    PLAYER_SKINS.forEach((s) => this.walkAnims(s, 4));
    Object.entries(NPC_SKINS).forEach(([s, n]) => this.walkAnims(s, n));
    this.anims.create({ key: "spark", frames: this.anims.generateFrameNumbers("spark", { start: 0, end: 6 }), frameRate: 14, repeat: -1 });
  }

  walkAnims(skin, rows) {
    for (let d = 0; d < 4; d++) {
      this.anims.create({ key: `${skin}-${d}`, frameRate: 8, repeat: -1,
        frames: Array.from({ length: rows }, (_, r) => ({ key: skin, frame: r * 4 + d })) });
    }
  }

  // ── 地圖 ─────────────────────────────────────────────
  buildWorld() {
    const T = 16, cols = MAP.w / T, rows = MAP.h / T;
    const rnd = new Phaser.Math.RandomDataGenerator(["flood"]);
    const path = (c, r) => r === 4 || r === 10 || ((c === 5 || c === 6 || c === 11 || c === 12 || c === 17 || c === 18) && r > 4 && r < 10);
    const yard = (c, r) => r >= 12 && c >= 5;
    for (let r = 4; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        let frame = rnd.frac() < 0.12 ? F("Field", 1, 4) : F("Field", 3, 3);
        let sheet = "tField";
        if (path(c, r)) { sheet = "tFloor"; frame = F("Floor", 1, 8); }
        else if (yard(c, r)) { sheet = "tField"; frame = F("Field", 3, 0); }
        this.add.image(c * T, r * T, sheet, frame).setOrigin(0).setDepth(0);
      }
    }
    this.river = this.add.tileSprite(0, 0, MAP.w, 48, "tWater", F("Water", 1, 1)).setOrigin(0).setDepth(1);
    this.riverShine = this.add.graphics().setDepth(2);
    for (let c = 0; c < cols; c++) this.add.image(c * T, 48, "tHouse", F("House", 11, 9)).setOrigin(0).setDepth(3);

    MAP.drains.forEach(([x, y]) => this.add.image(x, y, "tElement", F("Element", 1, 11)).setDepth(4));
    MAP.boxes.forEach(([x, y]) => this.add.image(x, y - 2, "tElement", F("Element", 2, 6)).setDepth(10 + y));
    MAP.houses.forEach((h) => this.add.image(h.x, h.y, "tHouse", "house" + h.style).setOrigin(0).setDepth(10 + h.y + h.h));
    MAP.trees.forEach(([x, y]) => this.add.image(x, y + 4, "tNature", "tree").setOrigin(0.5, 1).setDepth(10 + y));

    this.benchItems = this.add.container(0, 0).setDepth(200);
    MAP.stations.forEach((s) => {
      const d = 10 + s.y + s.h / 2;
      if (s.kind === "shelter") {
        this.add.image(s.x, s.y + s.h / 2, "tHouse", "shelter").setOrigin(0.5, 1).setDepth(d);
        this.label(s.x, s.y - 34, "避難所", "#ffffff", "#2a9d8f");
      } else if (s.kind === "crate") {
        this.add.image(s.x, s.y, "tElement", F("Element", 0, 0)).setDepth(d);
        const icon = this.add.image(s.x, s.y - 14, "i_" + s.item).setDepth(d + 1);
        this.tweens.add({ targets: icon, y: s.y - 16, duration: 700, yoyo: true, repeat: -1, ease: "Sine.easeInOut" });
      } else if (s.kind === "sand") {
        this.add.image(s.x - 8, s.y, "tFloor", F("Floor", 2, 2)).setDepth(d - 1);
        this.add.image(s.x + 8, s.y, "tFloor", F("Floor", 2, 2)).setDepth(d - 1);
        this.add.image(s.x, s.y - 3, "tElement", F("Element", 8, 2)).setDepth(d);
        this.label(s.x, s.y + 15, "沙堆", "#3b2a1e", "#fff8e7b3", 6);
      } else if (s.kind === "bench") {
        this.add.image(s.x - 8, s.y, "tElement", F("Element", 12, 1)).setDepth(d);
        this.add.image(s.x + 8, s.y, "tElement", F("Element", 15, 1)).setDepth(d);
        this.label(s.x, s.y + 13, "工作台", "#3b2a1e", "#fff8e7b3", 6);
        this.benchX = s.x; this.benchY = s.y;
      } else if (s.kind === "truck") {
        this.add.image(s.x, s.y + 4, "tElement", "cart").setDepth(d);
        this.label(s.x, s.y + 22, "垃圾車", "#3b2a1e", "#fff8e7b3", 6);
      }
    });
  }

  label(x, y, text, color = "#1d2a36", bg = "#ffffffcc", depth = 250) {
    return this.add.text(x, y, text, { fontFamily: FONT, fontSize: "11px", color, backgroundColor: bg, padding: { x: 2, y: 0 } })
      .setOrigin(0.5).setDepth(depth).setResolution(2);
  }

  // ── 開局 ─────────────────────────────────────────────
  startRound(s) {
    Object.values(this.objs).forEach((m) => Object.values(m).forEach((o) => o.destroy()));
    this.objs = { players: {}, incidents: {}, ground: {}, residents: {} };
    this.waterShown = MAP.wall_bottom;
    const me = s.players.find((p) => p.id === myId);
    if (me) this.me = { x: me.x, y: me.y, dir: 0 };
    this.applyState(s);
    this.resultMusic.stop();
    this.playPhase(s.phase, true);
    if (!this.rainA.isPlaying) {
      this.rainA.play({ volume: 0 });
      this.time.delayedCall(2200, () => { if (playing && !this.rainB.isPlaying) this.rainB.play({ volume: 0 }); });
    }
    this.applyAudio();
  }

  // 0～1 的實際音量：總音量 × 分類音量，靜音時為 0
  vol(kind) {
    const a = window.AUDIO || {};
    return a.muted ? 0 : ((a.master ?? 80) / 100) * ((a[kind] ?? 80) / 100);
  }

  applyAudio() {
    const m = 0.5 * this.vol("music");
    Object.values(this.tracks).forEach((t) => { if (t.isPlaying && !t.fading) t.setVolume(t === this.curTrack ? m : 0); });
    if (this.resultMusic.isPlaying) this.resultMusic.setVolume(m);
    const r = 0.35 * this.rainLevel * this.vol("ambient");
    this.rainA.setVolume(r); this.rainB.setVolume(r * 0.7);
  }

  // 換天氣時，舊音樂淡出、新音樂淡入
  playPhase(phase, instant = false) {
    const next = this.tracks[phase];
    if (!next || next === this.curTrack) return;
    const prev = this.curTrack;
    this.curTrack = next;
    this.rainLevel = { "小雨": 0.6, "颱風眼": 0.2, "暴雨": 1 }[phase];
    if (prev) {
      prev.fading = true;
      this.tweens.add({ targets: prev, volume: 0, duration: instant ? 10 : 1500, onComplete: () => { prev.stop(); prev.fading = false; } });
    }
    next.play({ volume: 0 });
    this.tweens.add({ targets: next, volume: 0.5 * this.vol("music"), duration: instant ? 10 : 1500 });
    this.applyAudio();
  }

  stopAudio(result = false) {
    Object.values(this.tracks).forEach((t) => t.stop());
    this.curTrack = null;
    this.rainA.stop(); this.rainB.stop();
    if (result) { this.resultMusic.play({ volume: 0.5 * this.vol("music") }); }
  }

  // ── 物件 ─────────────────────────────────────────────
  makeChar(skin, isMe) {
    const c = this.add.container(0, 0);
    const shadow = this.add.ellipse(0, 7, 10, 4, 0x000000, 0.3);
    const spr = this.add.sprite(0, 0, skin, 0);
    const held = this.add.image(0, -13, "i_bag").setVisible(false).setScale(0.75);
    const bar = this.add.graphics();
    c.add([shadow, spr, held, bar]);
    if (isMe) {
      const arrow = this.add.triangle(0, -22, 0, 0, 6, 0, 3, 4, 0xffd166);
      c.add(arrow);
      this.tweens.add({ targets: arrow, y: -20, duration: 400, yoyo: true, repeat: -1 });
    }
    Object.assign(c, { spr, held, bar, skin, dir: 0 });
    return c;
  }

  setWalk(o, dir, moving) {
    if (moving) o.spr.play(`${o.skin}-${dir}`, true);
    else { o.spr.stop(); o.spr.setFrame(dir); }
  }

  makeIncident(inc) {
    const c = this.add.container(inc.x, inc.y).setDepth(inc.type === "breach" ? 5 : 12 + inc.y);
    const fx = this.add.container(0, 0);
    c.add(fx);
    if (inc.type === "breach") {
      const g = this.add.graphics();
      g.fillStyle(0x2d1b12).fillEllipse(0, 0, 18, 12).fillStyle(0x4ea8de).fillEllipse(0, 1, 12, 7);
      fx.add(g);
      c.bags = this.add.container(0, 0); c.add(c.bags);
      for (let i = 0; i < 3; i++) {
        const sp = this.add.sprite(-6 + i * 6, 8, "splash", i).setAlpha(0.9);
        this.tweens.add({ targets: sp, y: 14, alpha: 0, duration: 450, delay: i * 150, repeat: -1 });
        fx.add(sp);
      }
    } else if (inc.type === "drain") {
      const g = this.add.graphics().fillStyle(0x4ea8de, 0.55).fillEllipse(0, 2, 34, 16);
      fx.add(g);
      [[-6, -2, 0], [5, 1, 2], [0, 4, 4]].forEach(([x, y, f]) => fx.add(this.add.image(x, y, "leaf", f)));
    } else if (inc.type === "electric") {
      const ring = this.add.circle(0, 0, 18, 0xffd166, 0.12).setStrokeStyle(1, 0xffd166, 0.6);   // 危險範圍（不閃爍）
      fx.add([ring, this.add.sprite(-3, -6, "spark").play("spark"), this.add.sprite(4, -2, "spark").play({ key: "spark", startFrame: 3 })]);
    } else if (inc.type === "house_flood") {
      const g = this.add.graphics().fillStyle(0x4ea8de, 0.6).fillEllipse(0, 2, 40, 14);
      fx.add(g);
      const sp = this.add.sprite(0, -2, "splash", 1);
      this.tweens.add({ targets: sp, alpha: 0.2, duration: 300, yoyo: true, repeat: -1 });
      fx.add(sp);
      c.pump = this.add.image(10, -2, "i_pump").setVisible(false); c.add(c.pump);
    } else if (inc.type === "tree") {
      const log = this.add.image(0, 0, "tNature", "log");
      if (inc.w > inc.h) log.setAngle(90);
      fx.add([log, this.add.image(inc.w > inc.h ? 14 : 0, inc.w > inc.h ? 0 : 12, "tNature", F("Nature", 0, 10))]);
      fx.setScale(0.2).setAlpha(0);
      this.tweens.add({ targets: fx, scale: 1, alpha: 1, duration: 300, ease: "Bounce.easeOut" });
      this.cameras.main.shake(150, 0.003);
    }
    // 頭上的需求泡泡：要帶什麼來
    const bubble = this.add.container(0, inc.type === "breach" ? 18 : -22);
    const bg = this.add.graphics();
    const need = this.add.image(0, -1, "i_" + inc.need).setScale(0.75);
    bubble.add([bg, need]);
    const bar = this.add.graphics();
    c.add([bubble, bar]);
    if (inc.type !== "breach") this.tweens.add({ targets: bubble, y: bubble.y - 2, duration: 500, yoyo: true, repeat: -1 });
    Object.assign(c, { bubble, bubbleBg: bg, bar, inc });
    this.drawBubble(c, false);
    return c;
  }

  drawBubble(o, urgent) {
    o.urgent = urgent;
    o.bubbleBg.clear().fillStyle(urgent ? 0xffadad : 0xffffff).fillRoundedRect(-8, -9, 16, 16, 4)
      .lineStyle(1, urgent ? 0xe63946 : 0x1d2a36).strokeRoundedRect(-8, -9, 16, 16, 4);
  }

  // ── 套用伺服器狀態 ───────────────────────────────────
  sync(map, list, make, update) {
    const seen = new Set();
    list.forEach((d) => {
      seen.add(d.id);
      if (!map[d.id]) map[d.id] = make(d);
      update(map[d.id], d);
    });
    Object.keys(map).forEach((id) => { if (!seen.has(id)) { map[id].destroy(); delete map[id]; } });
  }

  applyState(s) {
    this.state = s;
    this.sync(this.objs.players, s.players, (p) => this.makeChar(p.skin, p.id === myId), (o, p) => {
      o.target = p;
      o.held.setVisible(!!p.hold);
      if (p.hold) o.held.setTexture("i_" + p.hold);
      o.bar.clear();
      if (p.work != null) {
        o.bar.fillStyle(0x3b2a1e).fillRect(-11, -24, 22, 6).fillStyle(0xfff8e7).fillRect(-10, -23, 20, 4)
          .fillStyle(0x80ed99).fillRect(-10, -23, 20 * p.work, 4);
      }
      o.spr.setTint(p.stun ? 0xfff3b0 : 0xffffff);
    });
    const myHold = (s.players.find((p) => p.id === myId) || {}).hold;
    this.sync(this.objs.incidents, s.incidents, (i) => this.makeIncident(i), (o, i) => {
      const ratio = i.timer / i.max_timer;
      if ((ratio < 0.3) !== o.urgent) this.drawBubble(o, ratio < 0.3);
      o.bubble.setScale(myHold === i.need ? 1.35 : 1);      // 手上拿著對的東西 → 需求泡泡放大
      o.bar.clear();
      const working = i.state === "pumping" || i.progress > 0;
      if (working) {                                   // 進度條畫在泡泡原本的位置，泡泡先藏起來
        const by = i.type === "breach" ? 16 : -24, color = i.state === "pumping" ? 0x48cae4 : 0x80ed99;
        o.bar.fillStyle(0x3b2a1e).fillRect(-13, by - 1, 26, 6).fillStyle(0xfff8e7).fillRect(-12, by, 24, 4)
          .fillStyle(color).fillRect(-12, by, 24 * Math.min(1, i.progress), 4);
      }
      if (o.pump) o.pump.setVisible(i.state === "pumping");
      o.bubble.setVisible(!working && i.state === "active");     // 護送中、抽水中都不再顯示需求
      if (o.bags && o.shownCount !== i.count) {
        o.shownCount = i.count;
        o.bags.removeAll(true);
        for (let k = 0; k < i.count; k++) o.bags.add(this.add.image(-6 + k * 6, -1 - (k % 2) * 2, "i_sandbag").setScale(0.7));
      }
    });
    this.sync(this.objs.ground, s.ground, (g) => {
      const c = this.add.container(g.x, g.y).setDepth(11 + g.y);
      c.add([this.add.ellipse(0, 5, 10, 3, 0x000000, 0.3), this.add.image(0, 0, "i_" + g.item).setScale(0.8)]);
      return c;
    }, () => {});
    this.sync(this.objs.residents, s.residents, (r) => {
      const c = this.makeChar(r.skin, false);
      c.setPosition(r.x, r.y);
      c.mark = this.label(0, -16, "♥", "#ffffff", "#2a9d8f").setVisible(false); c.add(c.mark);
      return c;
    }, (o, r) => {
      o.target = r;
      o.mark.setVisible(r.state === "following");      // 等待中由災情泡泡提示，跟隨時顯示愛心
    });
    // 工作台上的零件
    this.benchItems.removeAll(true);
    s.bench.parts.forEach((part, k) =>
      this.benchItems.add(this.add.image(this.benchX - 6 + k * 12, this.benchY - 6, "i_" + part).setScale(0.8)));
    if (s.bench.progress > 0) {
      const by = this.benchY - 22;
      const g = this.add.graphics().fillStyle(0x3b2a1e).fillRect(this.benchX - 13, by - 1, 26, 6).fillStyle(0xfff8e7)
        .fillRect(this.benchX - 12, by, 24, 4).fillStyle(0x80ed99).fillRect(this.benchX - 12, by, 24 * s.bench.progress, 4);
      this.benchItems.add(g);
    }
    const tu = s.tutorial;
    this.guide.setVisible(!!(tu && tu.target && playing));
    if (tu && tu.target) this.guide.setPosition(tu.target[0], tu.target[1] - 6);
    updateHud(s);
  }

  // ── 操作提示：現在按空白鍵會發生什麼 ───────────────────
  hintText() {
    const s = this.state, me = this.me, my = s.players.find((p) => p.id === myId);
    if (!my || my.stun) return "";
    const near = (x, y, r = 24) => Math.hypot(me.x - x, me.y - y) <= r;
    const name = (k) => MAP.items[k];
    const active = s.incidents.filter((i) => i.state === "active");
    const st = (kind) => MAP.stations.find((x) => x.kind === kind);
    if (my.hold !== "gloves" && active.some((i) => i.type === "electric" && near(i.x, i.y, 28))) return "危險！要戴絕緣手套";
    if (my.hold) {
      const here = active.find((i) => i.need === my.hold && near(i.x, i.y, 28));
      if (here) return HOW[here.type] === "hold" ? "按住空白鍵　處理" : "空白鍵　交出" + name(my.hold);
      const sand = st("sand"), bench = st("bench"), truck = st("truck");
      if (my.hold === "bag") return near(sand.x, sand.y, 34) ? "按住空白鍵　裝沙" : "拿去沙堆裝沙";
      if ((my.hold === "motor" || my.hold === "hose") && near(bench.x, bench.y, 34)) return "空白鍵　放上工作台";
      if (my.hold === "trash") return near(truck.x, truck.y, 36) ? "空白鍵　倒進垃圾車" : "送去垃圾車";
      const target = active.find((i) => i.need === my.hold);
      if (target) return "帶去：" + MAP.incident_names[target.type];
      if (my.hold === "motor" || my.hold === "hose") return "放到工作台組裝";
      return "現在用不到，可以放回箱子";
    }
    const bench = st("bench");
    if (near(bench.x, bench.y, 34)) {
      const parts = s.bench.parts;
      if (parts.includes("pump")) return "空白鍵　拿起抽水機";
      if (parts.length === 2) return "按住空白鍵　組裝抽水機";
      if (parts.length === 1) return "還差" + name(parts[0] === "motor" ? "hose" : "motor");
    }
    const g = s.ground.find((x) => near(x.x, x.y, 16));
    if (g) return "空白鍵　撿起" + name(g.item);
    const crate = MAP.stations.find((x) => x.kind === "crate" && near(x.x, x.y, 26));
    if (crate) return "空白鍵　拿" + name(crate.item);
    const inc = active.find((i) => near(i.x, i.y, 28));
    if (inc) return "需要：" + name(inc.need);
    return "";
  }

  // ── 碰撞（和伺服器同一套規則）──────────────────────────
  solids() {
    const r = MAP.houses.map((h) => [h.x, h.y, h.w, h.h]);
    MAP.stations.forEach((s) => r.push([s.x - s.w / 2, s.y - s.h / 2, s.w, s.h]));
    MAP.trees.forEach(([x, y]) => r.push([x - 6, y - 4, 12, 8]));
    MAP.boxes.forEach(([x, y]) => r.push([x - 5, y - 6, 10, 10]));
    (this.state ? this.state.incidents : []).forEach((i) => {
      if (i.type === "tree") r.push([i.x - i.w / 2, i.y - i.h / 2, i.w, i.h]);
    });
    return r;
  }

  blocked(x, y, pad = 5) {
    if (y < MAP.wall_bottom + pad || x < pad || x > MAP.w - pad || y > MAP.h - pad) return true;
    return this.solids().some(([rx, ry, rw, rh]) => x > rx - pad && x < rx + rw + pad && y > ry - pad && y < ry + rh + pad);
  }

  update(time, delta) {
    this.river.tilePositionX -= delta * 0.012;
    this.riverShine.clear().fillStyle(0xffffff, 0.35);
    for (let i = 0; i < 10; i++) {
      const x = ((i * 53 + time * 0.02) % (MAP.w + 20)) - 10, y = 8 + (i * 13) % 34;
      this.riverShine.fillRect(MAP.w - x, y, 4 + (i % 3) * 2, 1);
    }
    if (!this.state) return;
    const dt = delta / 1000, s = this.state;

    // 自己：本地先動
    const meObj = this.objs.players[myId];
    if (meObj && playing) {
      const k = this.keys, stunned = (s.players.find((p) => p.id === myId) || {}).stun;
      let vx = (k.D.isDown || k.RIGHT.isDown) - (k.A.isDown || k.LEFT.isDown);
      let vy = (k.S.isDown || k.DOWN.isDown) - (k.W.isDown || k.UP.isDown);
      const t = window.touchDir || { x: 0, y: 0 };            // 手機搖桿
      if (!vx && !vy && (t.x || t.y)) { vx = t.x; vy = t.y; }
      if (stunned) vx = vy = 0;
      const moving = !!(vx || vy);
      if (moving) {
        const mag = Math.hypot(vx, vy), len = mag / Math.min(1, mag);   // 鍵盤：固定速度；搖桿：推越遠走越快
        const sp = SPEED * (this.me.y < this.waterShown ? 0.55 : 1) * dt;
        const nx = this.me.x + vx / len * sp, ny = this.me.y + vy / len * sp;
        if (!this.blocked(nx, this.me.y)) this.me.x = nx;
        if (!this.blocked(this.me.x, ny)) this.me.y = ny;
        this.me.dir = Math.abs(vx) >= Math.abs(vy) && vx ? (vx < 0 ? 2 : 3) : (vy < 0 ? 1 : 0);
      }
      if (this.blocked(this.me.x, this.me.y)) this.pushOut();
      meObj.setPosition(this.me.x, this.me.y).setDepth(100 + this.me.y);
      this.setWalk(meObj, this.me.dir, moving);
      if (time - this.lastSent > 66) {
        socket.emit("player_move", { x: Math.round(this.me.x * 10) / 10, y: Math.round(this.me.y * 10) / 10, d: this.me.dir, m: moving });
        this.lastSent = time;
      }
    }

    // 其他人：內插
    const lerp = Math.min(1, delta / 90);
    Object.entries(this.objs.players).forEach(([id, o]) => {
      if (id === myId || !o.target) return;
      o.x += (o.target.x - o.x) * lerp; o.y += (o.target.y - o.y) * lerp;
      o.setDepth(100 + o.y);
      this.setWalk(o, o.target.dir, o.target.moving);
    });
    Object.values(this.objs.residents).forEach((o) => {
      const dx = o.target.x - o.x, dy = o.target.y - o.y, moving = Math.abs(dx) + Math.abs(dy) > 0.4;
      o.x += dx * lerp; o.y += dy * lerp;
      o.setDepth(100 + o.y);
      this.setWalk(o, Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 2 : 3) : (dy < 0 ? 1 : 0), moving);
    });

    this.drawWater(time, delta, s);
    this.updateWeather(time, delta, s);
    if (time - this.lastHint > 100) {
      this.lastHint = time;
      const working = this.keys.SPACE.isDown || window.actHeld;      // 按住處理時不顯示提示，免得蓋住進度條
      const text = playing && !working ? this.hintText() : "";
      this.hint.setText(text).setVisible(!!text);
    }
    if (this.hint.visible) this.hint.setPosition(Math.round(this.me.x), Math.round(this.me.y) - 24);
  }

  pushOut() {
    for (let r = 2; r < 60; r += 2) {
      for (let a = 0; a < 16; a++) {
        const x = this.me.x + Math.cos(a / 8 * Math.PI) * r, y = this.me.y + Math.sin(a / 8 * Math.PI) * r;
        if (!this.blocked(x, y)) { this.me.x = x; this.me.y = y; return; }
      }
    }
  }

  drawWater(time, delta, s) {
    this.waterShown += (s.water_y - this.waterShown) * Math.min(1, delta / 250);
    const g = this.water, wy = Math.round(this.waterShown);
    g.clear();
    if (wy <= MAP.wall_bottom + 1) return;
    g.fillStyle(0x3a86c8, 0.42).fillRect(0, MAP.wall_bottom, MAP.w, wy - MAP.wall_bottom);
    g.fillStyle(0xcaf0f8, 0.8);
    for (let x = 0; x < MAP.w; x += 4) {                      // 像素風的浪
      const y = wy + Math.round(Math.sin(time / 300 + x / 14) * 1.5);
      g.fillRect(x, y, 3, 1);
    }
    g.fillStyle(0xffffff, 0.35);
    for (let i = 0; i < 12; i++) {
      const x = (i * 71 + Math.floor(time / 90)) % MAP.w, y = MAP.wall_bottom + 6 + (i * 37) % Math.max(1, wy - MAP.wall_bottom - 8);
      g.fillRect(x, y, 3, 1);
    }
  }

  updateWeather(time, delta, s) {
    if (playing && this.curTrack && this.tracks[s.phase] !== this.curTrack) this.playPhase(s.phase);
    const look = PHASE_LOOK[s.phase] || PHASE_LOOK["小雨"];
    this.dark.alpha += ((playing ? look.dark : 0.05) - this.dark.alpha) * Math.min(1, delta / 600);
    const q = playing ? look.rain : 0;
    if (q !== this.rain.quantity) {
      this.rain.setQuantity(q);
      q ? (this.rain.start(), this.splash.start()) : (this.rain.stop(), this.splash.stop());
    }
    if (playing && s.phase === "暴雨" && time > this.nextLightning) {
      this.nextLightning = time + Phaser.Math.Between(4000, 8000);
      this.sfx("impact", 0.3);                // 打雷只有聲音，不閃畫面（避免刺眼）
    }
  }

  // ── 特效 ─────────────────────────────────────────────
  floatText(x, y, text, color = "#ffffff") {
    const now = this.time.now;
    this.floats = (this.floats || []).filter((f) => now - f.t < 900);
    const stack = this.floats.filter((f) => Math.abs(f.x - x) < 70 && Math.abs(f.y - y) < 30).length;
    this.floats.push({ x, y, t: now });
    y -= stack * 13;                                   // 疊加時往上錯開一行
    const t = this.add.text(x, y - 8, text, { fontFamily: FONT, fontSize: "11px", color, stroke: "#1d2a36", strokeThickness: 3 })
      .setOrigin(0.5).setDepth(400).setResolution(2);
    this.tweens.add({ targets: t, y: y - 30, alpha: 0, delay: 350, duration: 900, onComplete: () => t.destroy() });
  }

  coinPop(x, y, n) {
    for (let i = 0; i < Math.min(6, Math.ceil(n / 10)); i++) {
      const c = this.add.image(x, y, "i_coin").setScale(0.6).setDepth(400);
      this.tweens.add({ targets: c, x: x + Phaser.Math.Between(-14, 14), y: y - Phaser.Math.Between(14, 26),
        duration: 300, ease: "Quad.easeOut", yoyo: true, delay: i * 40, onComplete: () => c.destroy() });
    }
  }

  ping(x, y) {
    const ring = this.add.circle(x, y, 4).setStrokeStyle(1.5, 0xffd166).setDepth(400);
    this.tweens.add({ targets: ring, scale: 4, alpha: 0, duration: 600, repeat: 2, onComplete: () => ring.destroy() });
  }
}
