/* Pocket Clock : module 01, replay tactique (canvas). Utilise core.js. */

/* ---------- 01 Replay tactique ---------- */
const Replay = (() => {
  const canvas = $("#field");
  const ctx = canvas.getContext("2d");
  const scrub = $("#scrub");
  const playBtn = $("#btn-play");
  const VIEW_WIDTH_YD = 30, QB_SCREEN_X = 0.38, TRAIL_FRAMES = 12, HOLD_MS = 1800, SHOCK_MS = 750;
  const DRAW_ORDER = { other: 0, block: 1, rush: 2, qb: 3, ball: 4 };
  const segments = Array.from({ length: METER_SEGMENTS }, () => $("#meter").appendChild(document.createElement("i")));
  let play = null, order = [], qbIndex = -1, dial = null;
  let pos = 0, playing = false, userPaused = false, speed = 1, lastTs = 0, holdMs = 0, shockAt = -Infinity, rafId = 0;
  let view = { s: 1, x0: 0, yTop: 0 }, size = { w: 0, h: 0 };

  const sx = x => (x - view.x0) * view.s;
  const sy = y => (view.yTop - y) * view.s;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    size = { w: rect.width, h: rect.height };
    computeView();
    render();
  }

  function computeView() {
    if (!play || !size.w) return;
    const s = size.w / VIEW_WIDTH_YD;
    view = { s, x0: play.center[0] - VIEW_WIDTH_YD * QB_SCREEN_X, yTop: play.center[1] + size.h / s / 2 };
  }

  function positionAt(p, k) {
    const i = Math.floor(k);
    const a = play.frames[i].p[p];
    const b = play.frames[Math.min(i + 1, play.frames.length - 1)].p[p];
    if (!a || !b) return a || b;
    return [lerp(a[0], b[0], k - i), lerp(a[1], b[1], k - i)];
  }

  function stateAt(k) {
    const i = Math.floor(k);
    const next = play.frames[Math.min(i + 1, play.frames.length - 1)];
    const frameId = lerp(play.frames[i].f, next.f, k - i);
    const t = (Math.min(frameId, play.end) - play.snap) / FPS;  // chrono figé à la passe / au sack
    const rec = play.frames[Math.min(i, play.endIndex)];
    return { t, preSnap: frameId < play.snap, ended: frameId >= play.end, gauge: rec.g ?? 0, dist: rec.d, rusher: rec.r,
      breached: play.breachTime !== null && t >= play.breachTime - 1e-6 };
  }

  function line(x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  function pill(x, y, text, rgb) {
    ctx.save();
    ctx.font = `600 10px ${MONO}`;
    const w = ctx.measureText(text).width + 12, h = 18;
    ctx.fillStyle = "rgba(4,8,18,0.88)";
    ctx.strokeStyle = rgba(rgb, 0.9);
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x - w / 2, y - h / 2, w, h, 4); else ctx.rect(x - w / 2, y - h / 2, w, h);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = rgba(rgb);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y + 0.5);
    ctx.restore();
  }

  function fieldMarker(x, rgb, label) {
    const X = sx(x);
    if (X < 0 || X > size.w) return;
    ctx.save();
    ctx.strokeStyle = rgba(rgb, 0.85);
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 6]);
    ctx.shadowColor = rgba(rgb);
    ctx.shadowBlur = 10;
    line(X, 0, X, size.h);
    ctx.restore();
    pill(X, 36, label, rgb);
  }

  function drawField() {
    const { w, h } = size;
    const bg = ctx.createRadialGradient(w * 0.4, h * 0.5, 0, w * 0.4, h * 0.5, w * 0.8);
    bg.addColorStop(0, "#0c1734");
    bg.addColorStop(1, "#03060d");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = "rgba(0,0,0,0.35)";  // hors des limites du terrain
    if (sy(0) < h) ctx.fillRect(0, sy(0), w, h - sy(0));
    if (sy(FIELD_WIDTH) > 0) ctx.fillRect(0, 0, w, sy(FIELD_WIDTH));

    ctx.font = `500 11px ${MONO}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let x = Math.ceil(view.x0); x <= view.x0 + w / view.s; x++) {
      const ten = x % 10 === 0, five = x % 5 === 0;
      ctx.strokeStyle = ten ? "rgba(34,229,255,0.30)" : five ? "rgba(34,229,255,0.16)" : "rgba(140,180,255,0.05)";
      ctx.lineWidth = ten ? 1.2 : 1;
      line(sx(x), 0, sx(x), h);
      if (ten && x > 10 && x < 110) {
        const yard = String(x <= 60 ? x - 10 : 110 - x);
        ctx.fillStyle = "rgba(140,200,255,0.45)";
        ctx.fillText(yard, sx(x), 14);
        ctx.fillText(yard, sx(x), h - 14);
      }
    }
    ctx.strokeStyle = "rgba(140,180,255,0.05)";
    for (let y = Math.ceil((view.yTop - h / view.s) / 5) * 5; y <= view.yTop; y += 5) line(0, sy(y), w, sy(y));

    fieldMarker(play.los, RGB.cyan, "LOS");
    if (play.firstDown < 110) fieldMarker(play.firstDown, RGB.amber, "1ER DOWN");
  }

  function playerColor(pl) {
    if (pl.role === "qb") return RGB.amber;
    if (pl.role === "rush") return RGB.red;
    return pl.side === "off" ? RGB.cyan : RGB.violet;
  }

  function drawTrails(k) {
    const start = Math.max(0, Math.floor(k) - TRAIL_FRAMES);
    ctx.save();
    ctx.lineCap = "round";
    order.forEach(p => {
      const pl = play.players[p];
      if (pl.side === "ball") return;
      const pts = [];
      for (let j = start; j <= Math.floor(k); j++) pts.push(play.frames[j].p[p]);
      pts.push(positionAt(p, k));
      const rgb = playerColor(pl);
      ctx.lineWidth = pl.role === "rush" || pl.role === "qb" ? 2.5 : 1.5;
      for (let i = 1; i < pts.length; i++) {
        if (!pts[i - 1] || !pts[i]) continue;
        ctx.strokeStyle = rgba(rgb, 0.5 * (i / pts.length));
        line(sx(pts[i - 1][0]), sy(pts[i - 1][1]), sx(pts[i][0]), sy(pts[i][1]));
      }
    });
    ctx.restore();
  }

  function drawPocket(k, st) {
    const qb = qbIndex >= 0 ? positionAt(qbIndex, k) : null;
    if (!qb) return;
    const x = sx(qb[0]), y = sy(qb[1]), r = DATA.kpi.radius * view.s;
    const rgb = st.breached ? RGB.red : heat(st.gauge);

    const fill = ctx.createRadialGradient(x, y, r * 0.15, x, y, r);
    fill.addColorStop(0, rgba(rgb, 0));
    fill.addColorStop(1, rgba(rgb, st.breached ? 0.32 : 0.16));
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fill();
    ctx.save();
    ctx.strokeStyle = rgba(rgb, 0.95);
    ctx.lineWidth = 1.6;
    ctx.setLineDash([5, 4]);
    ctx.shadowColor = rgba(rgb);
    ctx.shadowBlur = 14;
    ctx.stroke();
    ctx.restore();

    const sweep = Math.max(st.t, 0) * Math.PI * 1.4;  // radar qui tourne avec le chrono
    ctx.save();
    ctx.strokeStyle = rgba(rgb, 0.9);
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.shadowColor = rgba(rgb);
    ctx.shadowBlur = 10;
    [0, Math.PI].forEach(offset => {
      ctx.beginPath();
      ctx.arc(x, y, r + 6, sweep + offset, sweep + offset + Math.PI / 4);
      ctx.stroke();
    });
    ctx.restore();

    const age = performance.now() - shockAt;
    if (age < SHOCK_MS) {  // onde de choc à l'instant de la percée
      const p = age / SHOCK_MS;
      ctx.save();
      ctx.strokeStyle = rgba(RGB.red, 1 - p);
      ctx.lineWidth = 3 * (1 - p) + 0.5;
      ctx.shadowColor = rgba(RGB.red);
      ctx.shadowBlur = 20;
      ctx.beginPath();
      ctx.arc(x, y, r * (1 + p * 1.8), 0, 2 * Math.PI);
      ctx.stroke();
      ctx.restore();
    }

    if (st.preSnap || st.ended || st.rusher === null || st.dist === null) return;
    const rp = positionAt(st.rusher, k);
    if (!rp) return;
    const X = sx(rp[0]), Y = sy(rp[1]);
    ctx.save();
    ctx.strokeStyle = rgba(rgb, 0.9);
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 4]);
    line(x, y, X, Y);
    ctx.restore();
    pill((x + X) / 2, (y + Y) / 2 - 14, `${num(st.dist)} yd`, rgb);
  }

  function drawPlayers(k) {
    const radius = clamp(view.s * 0.33, 5, 11);
    order.forEach(p => {
      const pl = play.players[p], xy = positionAt(p, k);
      if (!xy) return;
      const x = sx(xy[0]), y = sy(xy[1]);
      ctx.save();
      if (pl.side === "ball") {
        ctx.fillStyle = "#fff";
        ctx.shadowColor = "#fff";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.ellipse(x, y, radius * 0.45, radius * 0.3, 0, 0, 2 * Math.PI);
        ctx.fill();
        ctx.restore();
        return;
      }
      const rgb = playerColor(pl), r = pl.role === "qb" ? radius * 1.2 : radius;
      const coverage = pl.side === "def" && pl.role === "other";
      ctx.shadowColor = rgba(rgb);
      ctx.shadowBlur = pl.role === "rush" || pl.role === "qb" ? 18 : 8;
      ctx.fillStyle = rgba(rgb, coverage ? 0.55 : 0.95);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "rgba(255,255,255,0.65)";
      ctx.lineWidth = 1;
      ctx.stroke();
      if (r >= 8) {
        ctx.fillStyle = "#020611";
        ctx.font = `700 ${Math.round(r * 0.95)}px ${MONO}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(pl.jersey, x, y + 0.5);
      }
      ctx.restore();
    });
  }

  function updateHud(st) {
    const t = Math.max(st.t, 0);
    const rgb = st.breached ? RGB.red : heat(st.gauge);
    $("#clock-time").textContent = num(t);
    dial.set(t / MAX_CLOCK, rgb);
    $("#hud-status").dataset.state = st.preSnap ? "pre" : st.breached ? "breach" : "safe";
    $("#hud-status-main").textContent = st.preSnap ? "Pré-snap" : st.breached ? `Percée à ${num(play.breachTime)} s` : "Poche intacte";
    $("#hud-status-sub").textContent = st.preSnap ? "en attente du snap"
      : st.breached ? `par ${play.breachRusher}` : `aucun rusher à moins de ${num(DATA.kpi.radius, 0)} yd`;
    const lit = Math.round(st.gauge * METER_SEGMENTS);
    segments.forEach((seg, i) => {
      const c = heat(i / (METER_SEGMENTS - 1));
      seg.style.background = i < lit ? rgba(c) : "";
      seg.style.boxShadow = i < lit ? `0 0 10px ${rgba(c, 0.8)}` : "";
    });
    $("#hud-gauge").textContent = pct(st.gauge);
    $("#hud-dist").textContent = st.preSnap || st.dist === null ? "—" : `${num(st.dist)} yd`;
    $("#hud-result").textContent = st.ended ? `${RESULTS[play.result] ?? play.result} · ${yardsLabel(play.yards)}` : "En cours";
    $("#timecode").textContent = `T${st.t < 0 ? "−" : "+"}${num(Math.abs(st.t))} s`;
    scrub.value = Math.floor(pos);
    scrub.style.setProperty("--p", `${(pos / (play.frames.length - 1)) * 100}%`);
  }

  function render() {
    if (!play || !size.w) return;
    const st = stateAt(pos);
    ctx.clearRect(0, 0, size.w, size.h);
    drawField();
    drawTrails(pos);
    drawPocket(pos, st);
    drawPlayers(pos);
    updateHud(st);
  }

  function loop(ts) {
    if (!playing) return;
    const dt = Math.min(ts - lastTs, 100);
    lastTs = ts;
    const last = play.frames.length - 1;
    if (pos >= last) {
      holdMs += dt;
      if (holdMs >= HOLD_MS) { pos = 0; holdMs = 0; }
    } else {
      const wasBreached = stateAt(pos).breached;
      pos = Math.min(last, pos + (dt * speed) / FRAME_MS);
      if (!wasBreached && stateAt(pos).breached) shockAt = performance.now();
    }
    render();
    rafId = requestAnimationFrame(loop);
  }

  function setPlaying(on) {
    playing = on;
    playBtn.classList.toggle("is-playing", on);
    playBtn.setAttribute("aria-label", on ? "Pause" : "Lecture");
    cancelAnimationFrame(rafId);
    if (on) {
      lastTs = performance.now();
      rafId = requestAnimationFrame(loop);
    }
  }

  function load(i) {
    play = DATA.replays[i];
    order = play.players.map((_, p) => p).sort((a, b) => DRAW_ORDER[play.players[a].role] - DRAW_ORDER[play.players[b].role]);
    qbIndex = play.players.findIndex(pl => pl.role === "qb");
    pos = 0;
    holdMs = 0;
    shockAt = -Infinity;
    scrub.max = play.frames.length - 1;
    const marks = [{ value: DATA.kpi.leagueClock, label: "NFL", cls: "league" }];
    if (play.breachTime !== null) marks.push({ value: play.breachTime, cls: "breach" });
    dial = buildDial($("#clock-svg"), marks);
    $$("#play-picker .pick").forEach((b, j) => b.setAttribute("aria-selected", String(j === i)));
    $("#play-desc").textContent = play.description;
    computeView();
    render();
  }

  function renderPicker() {
    DATA.replays.forEach((p, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pick";
      btn.setAttribute("role", "tab");
      const tag = p.breachTime === null ? `<span class="tag safe">Poche intacte</span>`
        : `<span class="tag breach">Percée ${num(p.breachTime)} s</span>`;
      btn.innerHTML = `<span class="pick-meta">S${p.week} · ${escapeHtml(p.offense)} vs ${escapeHtml(p.defense)}</span>
        <span class="pick-title">${escapeHtml(p.title)}</span>${tag}`;
      btn.addEventListener("click", () => { load(i); userPaused = false; setPlaying(true); });
      $("#play-picker").append(btn);
    });
  }

  function bindControls() {
    const toggle = () => { userPaused = playing; setPlaying(!playing); };
    playBtn.addEventListener("click", toggle);
    canvas.addEventListener("click", toggle);
    $("#btn-restart").addEventListener("click", () => { pos = 0; holdMs = 0; userPaused = false; render(); setPlaying(true); });
    scrub.addEventListener("input", () => { userPaused = true; setPlaying(false); pos = Number(scrub.value); render(); });
    $$(".speed button").forEach(b => b.addEventListener("click", () => {
      speed = Number(b.dataset.speed);
      $$(".speed button").forEach(o => o.setAttribute("aria-pressed", String(o === b)));
    }));
    window.addEventListener("resize", resize);
    if (REDUCED_MOTION || !("IntersectionObserver" in window)) return;
    new IntersectionObserver(([entry]) => {  // lecture auto quand le terrain est visible
      if (entry.isIntersecting && !userPaused) setPlaying(true);
      else if (!entry.isIntersecting) setPlaying(false);
    }, { threshold: 0.35 }).observe(canvas);
  }

  function init() {
    renderPicker();
    bindControls();
    load(0);
    resize();
    if (document.fonts) document.fonts.ready.then(render);
  }

  return { init };
})();

