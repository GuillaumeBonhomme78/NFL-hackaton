/* Pocket Clock : en-tête, matchup, classements, scouting et démarrage. Utilise core.js et replay.js. */

/* ---------- En-tête : cadran de la ligue et indicateurs ---------- */
function renderHero() {
  const k = DATA.kpi, teams = DATA.offense;
  const best = teams[0], worstClock = teams[teams.length - 1].pocket_clock;
  const worst = teams.filter(t => t.pocket_clock === worstClock).map(t => t.team).join(", ");
  $("#hero-clock").textContent = num(k.leagueClock);
  $("#hero-range").textContent = `Lignes offensives : de ${clockLabel(worstClock)} (${worst}) `
    + `à ${best.pocket_clock >= MAX_CLOCK ? "plus de 6 s" : clockLabel(best.pocket_clock)} (${best.team})`;
  const dial = buildDial($("#hero-dial"));
  if (REDUCED_MOTION) dial.set(k.leagueClock / MAX_CLOCK, RGB.cyan);
  else requestAnimationFrame(() => requestAnimationFrame(() => dial.set(k.leagueClock / MAX_CLOCK, RGB.cyan)));
}

function countUp(node, target, render, duration = 1400) {
  const start = performance.now();
  const step = now => {
    const t = clamp((now - start) / duration, 0, 1);
    node.textContent = render(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderKpis() {
  const k = DATA.kpi;
  const items = [
    { value: k.leagueClock, render: v => num(v), unit: "s", label: "Pocket Clock de la ligue", note: "médiane Kaplan-Meier" },
    { value: k.intact25 * 100, render: v => Math.round(v), unit: "%", label: "Poches intactes à 2,5 s",
      note: `sur ${k.plays.toLocaleString("fr-FR")} actions de passe` },
    { value: k.agreement * 100, render: v => Math.round(v), unit: "%", label: "D'accord avec PFF",
      note: `action par action · AUC ${num(k.auc, 2)}` },
    { value: k.rhoClock, render: v => signed(v), unit: "", label: "ρ avec les yards / action",
      note: `pression PFF : ρ = ${signed(k.rhoPff)}` },
  ];
  const root = $("#kpis");
  items.forEach(item => {
    const card = document.createElement("div");
    card.className = "panel kpi";
    card.innerHTML = `<div class="kpi-value"><span></span><small>${item.unit}</small></div>
      <div class="kpi-label">${item.label}</div><div class="kpi-note">${item.note}</div>`;
    const value = $("span", card);
    value.textContent = item.render(item.value);
    if (!REDUCED_MOTION) countUp(value, item.value, item.render);
    root.append(card);
  });
}

function fillKpiSpans() {
  const formats = { pct: v => pct(v), num0: v => num(v, 0), num2: v => num(v, 2), int: v => Number(v).toLocaleString("fr-FR") };
  $$("[data-kpi]").forEach(node => { node.textContent = formats[node.dataset.fmt || "int"](DATA.kpi[node.dataset.kpi]); });
}

/* ---------- 02 Matchup ---------- */
const Matchup = (() => {
  const OFF = Object.fromEntries(DATA.offense.map((r, i) => [r.team, { ...r, rank: i + 1 }]));
  const DEF = Object.fromEntries(DATA.defense.map((r, i) => [r.team, { ...r, rank: i + 1 }]));
  const selects = { off: $("#sel-off"), def: $("#sel-def") };
  const chart = $("#chart-survival");
  const METRICS = [
    { key: "pocket_clock", label: "Pocket Clock", fmt: clockLabel },
    { key: "pocket_intact_2_5s", label: "Poche intacte à 2,5 s", fmt: v => pct(v) },
    { key: "breach_rate", label: "Taux de percée", fmt: v => pct(v) },
    { key: "pff_pressure_rate", label: "Pression PFF", fmt: v => pct(v) },
    { key: "time_to_throw", label: "Temps de lancer", fmt: v => `${num(v)} s` },
    { key: "yards_per_play", label: "Yards / action", fmt: v => num(v) },
    { key: "sack_rate", label: "Taux de sacks", fmt: v => pct(v, 1) },
  ];
  let hooked = false;

  function renderVersus(a, b) {
    const all = DATA.offense.concat(DATA.defense);
    const rows = METRICS.map(m => {
      const values = all.map(r => r[m.key]);
      const lo = Math.min(...values), hi = Math.max(...values);
      const width = v => `${(clamp((v - lo) / (hi - lo || 1), 0.04, 1) * 100).toFixed(1)}%`;
      return `<div class="vs-row">
        <div class="vs-cell off"><span>${m.fmt(a[m.key])}</span><i style="--w:${width(a[m.key])}"></i></div>
        <div class="vs-label">${m.label}</div>
        <div class="vs-cell def"><span>${m.fmt(b[m.key])}</span><i style="--w:${width(b[m.key])}"></i></div></div>`;
    }).join("");
    $("#versus").innerHTML = `<div class="vs-head">
        <div class="vs-team off"><b>${escapeHtml(a.team)}</b><span>Ligne offensive</span><span>${ordinal(a.rank)} sur 32</span></div>
        <div class="vs-badge">VS</div>
        <div class="vs-team def"><b>${escapeHtml(b.team)}</b><span>Pass rush</span><span>${ordinal(b.rank)} sur 32</span></div>
      </div>${rows}`;
  }

  function renderVerdict(a, b) {
    const league = DATA.kpi.leagueClock;
    const offDelta = a.pocket_clock - league, defDelta = league - b.pocket_clock;
    const offText = a.pocket_clock >= MAX_CLOCK ? `au moins ${num(offDelta)} s de plus`
      : `${num(Math.abs(offDelta))} s ${offDelta >= 0 ? "de plus" : "de moins"}`;
    const defText = `${num(Math.abs(defDelta))} s ${defDelta >= 0 ? "plus vite" : "moins vite"}`;
    const edge = Math.abs(offDelta - defDelta) < 0.15 ? "Duel équilibré"
      : offDelta > defDelta ? `Avantage ligne offensive (${a.team})` : `Avantage pass rush (${b.team})`;
    $("#verdict").innerHTML = `<b>Lecture rapide · ${escapeHtml(edge)}.</b> La ligne de ${escapeHtml(a.team)} tient ${offText}
      que la ligue ; le pass rush de ${escapeHtml(b.team)} perce ${defText} que la ligue (${clockLabel(league)}).`;
  }

  function traces(a, b) {
    const x = DATA.grid, line = (color, width, dash) => ({ color, width, dash, shape: "hv" });
    const crossings = [[a, RGB.cyan], [b, RGB.red]].filter(([t]) => t.pocket_clock < MAX_CLOCK);
    return [
      { x, y: DATA.band.low, mode: "lines", line: line("rgba(0,0,0,0)", 0), hoverinfo: "skip" },
      { x, y: DATA.band.high, mode: "lines", line: line("rgba(0,0,0,0)", 0), fill: "tonexty",
        fillcolor: "rgba(34,229,255,0.07)", hoverinfo: "skip" },
      { x, y: DATA.league, mode: "lines", line: line("rgba(230,241,255,0.7)", 2, "dot"),
        hovertemplate: "Ligue : %{y:.0%}<extra></extra>" },
      { x, y: a.curve, mode: "lines", line: line(rgba(RGB.cyan), 3),
        hovertemplate: `${a.team} (ligne offensive) : %{y:.0%}<extra></extra>` },
      { x, y: b.curve, mode: "lines", line: line(rgba(RGB.red), 3),
        hovertemplate: `${b.team} (pass rush) : %{y:.0%}<extra></extra>` },
      { x: crossings.map(([t]) => t.pocket_clock), y: crossings.map(() => 0.5), mode: "markers", hoverinfo: "skip",
        marker: { size: 12, color: crossings.map(([, c]) => rgba(c)), line: { color: "#04070f", width: 2 } } },
    ];
  }

  function layout() {
    return plotLayout({
      hovermode: "x unified",
      xaxis: { range: [0, MAX_CLOCK], dtick: 1, ticksuffix: " s", hoverformat: ".1f", title: { text: "Temps depuis le snap" } },
      yaxis: { range: [0, 1.02], tickformat: ".0%", title: { text: "P(poche intacte)" } },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.5, y1: 0.5,
        line: { color: "rgba(230,241,255,0.35)", width: 1, dash: "dash" } }],
      annotations: [{ xref: "paper", x: 0.01, y: 0.5, xanchor: "left", yanchor: "bottom", showarrow: false,
        text: "50 % → Pocket Clock", font: { family: MONO, size: 10, color: rgba(RGB.muted) } }],
    });
  }

  function renderLegend(a, b) {
    const items = [
      [`--c:${rgba(RGB.cyan)}`, "", `${a.team} · ligne offensive · ${clockLabel(a.pocket_clock)}`],
      [`--c:${rgba(RGB.red)}`, "", `${b.team} · pass rush · ${clockLabel(b.pocket_clock)}`],
      ["", "dotted", `Ligue · ${clockLabel(DATA.kpi.leagueClock)}`],
      ["", "band", "Plage des 32 équipes"],
    ];
    $("#survival-legend").innerHTML = items
      .map(([style, cls, label]) => `<span><i class="${cls}" style="${style}"></i>${escapeHtml(label)}</span>`).join("");
  }

  function render() {
    const a = OFF[selects.off.value], b = DEF[selects.def.value];
    renderVersus(a, b);
    renderVerdict(a, b);
    renderLegend(a, b);
    Boards.highlight(a.team, b.team);
    if (!HAS_PLOTLY) return;
    Plotly.react(chart, traces(a, b), layout(), PLOT_CONFIG).then(() => {
      addGlow(chart);
      if (!hooked) { chart.on("plotly_afterplot", () => addGlow(chart)); hooked = true; }
    });
  }

  function set(side, team) {
    selects[side].value = team;
    render();
    $("#matchup").scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth", block: "start" });
  }

  function init() {
    Object.keys(OFF).sort().forEach(team => Object.values(selects).forEach(sel => sel.append(new Option(team, team))));
    selects.off.value = DATA.replays[0].offense;
    selects.def.value = DATA.replays[0].defense;
    Object.values(selects).forEach(sel => sel.addEventListener("change", render));
    render();
  }

  return { init, set };
})();

/* ---------- 03 Classements ---------- */
const Boards = (() => {
  const BAR_MIN = 2.8;  // s : origine des barres

  function renderBoard(root, rows, side) {
    rows.forEach((r, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "row";
      btn.dataset.team = r.team;
      btn.style.setProperty("--c", rgba(rankColor(i / (rows.length - 1))));
      btn.style.setProperty("--w", `${(clamp((r.pocket_clock - BAR_MIN) / (MAX_CLOCK - BAR_MIN), 0.04, 1) * 100).toFixed(1)}%`);
      btn.style.setProperty("--d", `${i * 25}ms`);
      btn.setAttribute("aria-label", `${r.team}, ${i === 0 ? "1er" : `${i + 1}e`}, Pocket Clock ${clockLabel(r.pocket_clock)} : envoyer dans le matchup`);
      btn.innerHTML = `<span class="rk">${String(i + 1).padStart(2, "0")}</span><span class="tm">${escapeHtml(r.team)}</span>
        <span class="br"><i></i></span><span class="vl">${clockLabel(r.pocket_clock)}</span><span class="sb">${pct(r.pocket_intact_2_5s)}</span>`;
      btn.addEventListener("click", () => Matchup.set(side, r.team));
      const li = document.createElement("li");
      li.append(btn);
      root.append(li);
    });
  }

  function highlight(offTeam, defTeam) {
    $$("#board-off .row").forEach(b => b.classList.toggle("is-selected", b.dataset.team === offTeam));
    $$("#board-def .row").forEach(b => b.classList.toggle("is-selected", b.dataset.team === defTeam));
  }

  function init() {
    renderBoard($("#board-off"), DATA.offense, "off");
    renderBoard($("#board-def"), DATA.defense, "def");
  }

  return { init, highlight };
})();

/* ---------- 04 Scouting ---------- */
const Scouting = (() => {
  const chart = $("#chart-players");
  const search = $("#player-search");
  const POSITION_COLORS = { T: RGB.cyan, G: RGB.violet, C: RGB.amber };
  const pct1 = v => pct(v, 1), count = v => String(Math.round(v));
  const KINDS = {
    rushers: {
      rows: DATA.rushers, x: "pff_pressure_rate", y: "breach_rate", snaps: "rush_snaps", label: "pass rusher", noun: "pass rushers",
      xTitle: "Taux de pression PFF (noté à la main)", yTitle: "Taux de percée (tracking)",
      hero: { key: "breach_rate", label: "de percées", fmt: pct1 },
      metrics: [
        { key: "breach_rate", label: "Taux de percée", fmt: pct1, high: true },
        { key: "pff_pressure_rate", label: "Pression PFF", fmt: pct1, high: true },
        { key: "median_breach_time", label: "Temps médian de percée", fmt: v => `${num(v)} s`, high: false },
        { key: "get_off", label: "Get-off (0,5 s)", fmt: v => `${num(v, 2)} yd/s`, high: true },
        { key: "first_in", label: "Premier dans la poche", fmt: v => `${count(v)} fois`, high: true },
        { key: "sacks", label: "Sacks (PFF)", fmt: count, high: true },
      ],
      marker(rows) {
        const snaps = rows.map(r => r.rush_snaps), lo = Math.min(...snaps), hi = Math.max(...snaps);
        return { size: snaps.map(v => 9 + ((v - lo) / (hi - lo || 1)) * 14), color: rows.map(r => r.median_breach_time),
          colorscale: [[0, rgba(RGB.red)], [0.5, rgba(RGB.amber)], [1, rgba(RGB.cyan)]], opacity: 0.9,
          line: { color: "rgba(4,7,15,0.9)", width: 1 },
          colorbar: { title: { text: "Temps médian<br>de percée (s)", font: { size: 11, color: rgba(RGB.muted) } },
            thickness: 10, outlinewidth: 0, tickfont: { family: MONO, size: 10, color: rgba(RGB.muted) } } };
      },
    },
    blockers: {
      rows: DATA.blockers, x: "pff_allowed_rate", y: "breach_allowed_rate", snaps: "block_snaps", label: "bloqueur", noun: "bloqueurs",
      xTitle: "Pressions concédées selon PFF", yTitle: "Percées concédées (tracking, duel PFF)",
      hero: { key: "breach_allowed_rate", label: "de percées concédées", fmt: pct1 },
      metrics: [
        { key: "breach_allowed_rate", label: "Percées concédées", fmt: pct1, high: false },
        { key: "pff_allowed_rate", label: "Pressions PFF concédées", fmt: pct1, high: false },
        { key: "breaches_allowed", label: "Percées (total)", fmt: count, high: false },
        { key: "sacks_allowed", label: "Sacks concédés", fmt: count, high: false },
      ],
      marker(rows) {
        return { size: 12, opacity: 0.92, line: { color: "rgba(4,7,15,0.9)", width: 1 },
          color: rows.map(r => rgba(POSITION_COLORS[r.officialPosition] || RGB.muted)) };
      },
    },
  };
  let kind = "rushers", hooked = false;

  function traces(cfg) {
    const rows = cfg.rows, top = rows.slice(0, 5);  // lignes déjà triées du meilleur au moins bon
    return [
      { x: rows.map(r => r[cfg.x]), y: rows.map(r => r[cfg.y]), mode: "markers", marker: cfg.marker(rows),
        customdata: rows.map((_, i) => i), text: rows.map(r => `${r.displayName} · ${r.officialPosition} · ${r.team ?? "?"}`),
        hovertemplate: `<b>%{text}</b><br>${cfg.yTitle} : %{y:.1%}<br>${cfg.xTitle} : %{x:.1%}<extra></extra>` },
      { x: top.map(r => r[cfg.x]), y: top.map(r => r[cfg.y]), text: top.map(r => r.displayName), mode: "markers+text",
        marker: { ...cfg.marker(top), color: "rgba(0,0,0,0)", line: { width: 0 }, colorbar: undefined },  // décale le nom au-dessus du point
        textposition: "top center", textfont: { family: MONO, size: 10, color: rgba(RGB.muted) }, hoverinfo: "skip" },
      { x: [], y: [], mode: "markers", hoverinfo: "skip",
        marker: { size: 30, color: "rgba(0,0,0,0)", line: { color: rgba(RGB.text), width: 2 } } },
    ];
  }

  function layout(cfg) {
    return plotLayout({ hovermode: "closest", margin: { l: 58, r: 10, t: 24, b: 52 },
      xaxis: { tickformat: ".0%", title: { text: cfg.xTitle } }, yaxis: { tickformat: ".0%", title: { text: cfg.yTitle } } });
  }

  function percentile(rows, key, value, higherIsBetter) {
    const values = rows.map(r => r[key]).filter(v => v !== null);
    const better = values.filter(v => (higherIsBetter ? v < value : v > value)).length;
    return values.length > 1 ? better / (values.length - 1) : 1;
  }

  function renderCard(cfg, row) {
    const metrics = cfg.metrics.map(m => {
      const v = row[m.key];
      const p = v === null ? null : percentile(cfg.rows, m.key, v, m.high);
      const bar = p === null ? "" : `<i style="--w:${(p * 100).toFixed(0)}%;--c:${rgba(rankColor(1 - p))}"></i>`;
      const tip = p === null ? "" : `Meilleur que ${Math.round(p * 100)} % des ${cfg.noun}`;
      return `<li><span class="m-label">${m.label}</span><span class="m-value">${v === null ? "—" : m.fmt(v)}</span>
        <span class="m-bar" title="${tip}">${bar}</span><span class="m-pct">${p === null ? "" : `P${Math.round(p * 100)}`}</span></li>`;
    }).join("");
    $("#player-card").innerHTML = `<p class="card-kicker">Fiche ${cfg.label}</p>
      <h3>${escapeHtml(row.displayName)}</h3>
      <p class="card-meta">${escapeHtml(row.officialPosition)} · ${escapeHtml(row.team ?? "—")} · ${row[cfg.snaps]} snaps</p>
      <div class="card-hero"><b>${cfg.hero.fmt(row[cfg.hero.key])}</b>
        <span>${cfg.hero.label}<br><em>${ordinal(cfg.rows.indexOf(row) + 1)} sur ${cfg.rows.length}</em></span></div>
      <ul class="metrics">${metrics}</ul>`;
  }

  function select(row) {
    const cfg = KINDS[kind];
    renderCard(cfg, row);
    search.value = row.displayName;
    $(".search").classList.remove("is-invalid");
    if (HAS_PLOTLY) Plotly.restyle(chart, { x: [[row[cfg.x]]], y: [[row[cfg.y]]] }, [2]);
  }

  function show(next) {
    kind = next;
    const cfg = KINDS[kind];
    $$(".tabs [role=tab]").forEach(t => t.setAttribute("aria-selected", String(t.dataset.tab === kind)));
    $("#player-list").replaceChildren(...cfg.rows.map(r => new Option(r.displayName, r.displayName)));
    $("#position-legend").hidden = kind !== "blockers";
    if (!HAS_PLOTLY) { select(cfg.rows[0]); return; }
    Plotly.react(chart, traces(cfg), layout(cfg), PLOT_CONFIG).then(() => {
      if (!hooked) {
        chart.on("plotly_click", ev => {
          const point = ev.points.find(p => p.curveNumber === 0);
          if (point) select(KINDS[kind].rows[point.customdata]);
        });
        hooked = true;
      }
      select(cfg.rows[0]);
    });
  }

  function init() {
    $$(".tabs [role=tab]").forEach(t => t.addEventListener("click", () => show(t.dataset.tab)));
    search.addEventListener("change", () => {
      const query = search.value.trim().toLowerCase();
      const row = KINDS[kind].rows.find(r => r.displayName.toLowerCase() === query);
      if (row) select(row); else $(".search").classList.add("is-invalid");
    });
    show(kind);
  }

  return { init };
})();

/* ---------- Navigation et apparitions ---------- */
function revealOnScroll() {
  const targets = $$(".reveal");
  if (REDUCED_MOTION || !("IntersectionObserver" in window)) { targets.forEach(t => t.classList.add("is-visible")); return; }
  const io = new IntersectionObserver(entries => entries.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add("is-visible");
    io.unobserve(e.target);
  }), { threshold: 0.12 });
  targets.forEach(t => io.observe(t));
}

function navSpy() {
  if (!("IntersectionObserver" in window)) return;
  const links = new Map($$(".nav a").map(a => [a.getAttribute("href").slice(1), a]));
  const io = new IntersectionObserver(entries => entries.forEach(e => {
    if (e.isIntersecting) links.forEach((a, id) => a.classList.toggle("is-active", id === e.target.id));
  }), { rootMargin: "-45% 0px -50% 0px" });
  links.forEach((_, id) => { const section = document.getElementById(id); if (section) io.observe(section); });
}

function init() {
  renderHero();
  renderKpis();
  fillKpiSpans();
  Boards.init();
  Matchup.init();
  Replay.init();
  Scouting.init();
  revealOnScroll();
  navSpy();
  if (!HAS_PLOTLY) {
    $$(".chart").forEach(c => {
      c.innerHTML = `<p class="offline">Graphiques indisponibles : Plotly n'a pas pu être chargé (connexion internet requise).</p>`;
    });
  }
}

init();
