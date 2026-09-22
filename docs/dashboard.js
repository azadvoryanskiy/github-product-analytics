/* Feature usage and retention dashboard.
 *
 * The JSON holds counts, never percentages, so a filtered view and a
 * volume-matched view can both be derived from the same file. Filters add up
 * the counts they select and divide at the end.
 */
"use strict";

const PALETTE = {
  surface: "#141417", ink: "#f5f5f4", ink2: "#a1a1aa", muted: "#71717a",
  grid: "#2c2c2a", axis: "#383835",
  blue: "#3987e5", orange: "#d95926", aqua: "#199e70", yellow: "#c98500",
  accent: "#ff6a3d",
};

const state = {
  cube: null,
  bands: new Set(),       // activity bands, empty means all
  ages: new Set(),        // account-age bands, empty means all
  matched: false,
  horizon: 90,
  feature: null,          // highlighted feature
  sort: { key: "retention", dir: -1 },
};

const charts = {};
const $ = (sel) => document.querySelector(sel);
const pct = (x) => (x === null || !isFinite(x)) ? "—" : (100 * x).toFixed(1) + "%";
const pts = (x) => (x === null || !isFinite(x)) ? "—"
  : (x >= 0 ? "+" : "−") + Math.abs(100 * x).toFixed(1);

/* ---------- selection helpers ---------- */

const bandOk = (b) => state.bands.size === 0 || state.bands.has(b);
const ageOk = (a) => state.ages.size === 0 || state.ages.has(a);
const selectedBands = () =>
  state.cube.meta.activity_bands.filter(bandOk);

function rows(kind, extra) {
  return state.cube[kind].filter(
    (r) => bandOk(r.band) && ageOk(r.age_band) && (!extra || extra(r)));
}

/* ---------- the numbers ---------- */

function adoptionByFeature() {
  const totals = new Map();
  for (const r of rows("adoption")) {
    const t = totals.get(r.feature) || { users: 0, accounts: 0 };
    t.users += r.users; t.accounts += r.accounts;
    totals.set(r.feature, t);
  }
  return state.cube.meta.features.map((f) => {
    const t = totals.get(f) || { users: 0, accounts: 0 };
    return { feature: f, users: t.users, accounts: t.accounts,
             share: t.accounts ? t.users / t.accounts : null };
  });
}

/* Raw and matched retention for one feature at the chosen horizon.
 *
 * Matched is direct standardisation: the rate is taken inside each activity
 * band and then re-weighted to the same band mix for both arms, so the
 * comparison is not just "people who use this are busier". */
function retentionFor(feature) {
  const sel = rows("retention", (r) => r.feature === feature
    && r.horizon === state.horizon);
  let users = 0, usersKept = 0, others = 0, othersKept = 0;
  const perBand = new Map();
  for (const r of sel) {
    users += r.users; usersKept += r.users_kept;
    others += r.others; othersKept += r.others_kept;
    const b = perBand.get(r.band) || { u: 0, uk: 0, o: 0, ok: 0 };
    b.u += r.users; b.uk += r.users_kept; b.o += r.others; b.ok += r.others_kept;
    perBand.set(r.band, b);
  }
  let wSum = 0, mUsers = 0, mOthers = 0;
  for (const [, b] of perBand) {
    if (!b.u || !b.o) continue;          // a band with only one arm cannot match
    const w = b.u + b.o;
    wSum += w;
    mUsers += w * (b.uk / b.u);
    mOthers += w * (b.ok / b.o);
  }
  const rawU = users ? usersKept / users : null;
  const rawO = others ? othersKept / others : null;
  const matU = wSum ? mUsers / wSum : null;
  const matO = wSum ? mOthers / wSum : null;
  return {
    feature, users, others,
    usersRate: state.matched ? matU : rawU,
    othersRate: state.matched ? matO : rawO,
    rawGap: (rawU !== null && rawO !== null) ? rawU - rawO : null,
    matchedGap: (matU !== null && matO !== null) ? matU - matO : null,
  };
}

const retentionAll = () =>
  state.cube.meta.features.map(retentionFor)
    .filter((r) => r.users > 0 && r.others > 0);

function baselineRetention() {
  const sel = rows("curves", (r) => r.horizon === state.horizon);
  let n = 0, kept = 0;
  for (const r of sel) { n += r.accounts; kept += r.kept; }
  return { n, rate: n ? kept / n : null };
}

function curveRows() {
  const out = new Map();
  for (const r of rows("curves")) {
    const key = r.n_features + "|" + r.horizon;
    const t = out.get(key) || { n_features: r.n_features, horizon: r.horizon, n: 0, kept: 0 };
    t.n += r.accounts; t.kept += r.kept;
    out.set(key, t);
  }
  return [...out.values()];
}

function topPairs(limit) {
  return state.cube.pairs
    .filter((p) => p.both >= 500)
    .map((p) => {
      const both = p.both_kept / p.both;
      const a = p.only_a ? p.only_a_kept / p.only_a : null;
      const b = p.only_b ? p.only_b_kept / p.only_b : null;
      const best = (a === null || b === null) ? null : Math.max(a, b);
      return { ...p, bothRate: both, bestAlone: best,
               lift: best === null ? null : both - best };
    })
    .filter((p) => p.lift !== null)
    .sort((x, y) => y.lift - x.lift)
    .slice(0, limit);
}

/* ---------- charts ---------- */

const base = {
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: PALETTE.ink2 },
  grid: { left: 150, right: 70, top: 16, bottom: 34, containLabel: false },
  tooltip: { trigger: "item", backgroundColor: "#1f1f23",
             borderColor: PALETTE.axis, textStyle: { color: PALETTE.ink } },
};

const axisLine = { lineStyle: { color: PALETTE.axis } };
const splitLine = { lineStyle: { color: PALETTE.grid } };

function dim(feature) {
  return state.feature && state.feature !== feature ? 0.25 : 1;
}

function drawAdoption() {
  const d = adoptionByFeature().sort((a, b) => (b.share || 0) - (a.share || 0));
  charts.adoption.setOption({
    ...base,
    grid: { ...base.grid, right: 90 },
    xAxis: { type: "value", axisLabel: { formatter: (v) => v + "%",
             color: PALETTE.muted }, splitLine, axisLine },
    yAxis: { type: "category", inverse: true, data: d.map((x) => x.feature),
             axisLabel: { color: PALETTE.ink2 }, axisLine, axisTick: { show: false } },
    series: [{
      type: "bar", barWidth: "62%",
      color: PALETTE.blue,
      data: d.map((x) => ({ value: x.share === null ? 0 : +(100 * x.share).toFixed(2),
                            users: x.users,
                            itemStyle: { opacity: dim(x.feature) } })),
      label: { show: true, position: "right", color: PALETTE.ink,
               formatter: (p) => p.value.toFixed(1) + "%" },
    }],
    tooltip: { ...base.tooltip, formatter: (p) =>
      `<b>${p.name}</b><br>${p.data.users.toLocaleString()} accounts<br>${p.value.toFixed(1)}% of the selection` },
  }, true);
}

function drawFrequency() {
  const order = adoptionByFeature().sort((a, b) => (b.share || 0) - (a.share || 0))
    .map((x) => x.feature);
  const byName = new Map(state.cube.frequency.map((f) => [f.feature, f]));
  const d = order.map((f) => byName.get(f)).filter(Boolean);
  charts.frequency.setOption({
    ...base,
    grid: { ...base.grid, right: 40 },
    xAxis: { type: "value", axisLabel: { color: PALETTE.muted }, splitLine, axisLine,
             name: "events per active day", nameLocation: "middle", nameGap: 26,
             nameTextStyle: { color: PALETTE.muted } },
    yAxis: { type: "category", inverse: true, data: d.map((x) => x.feature),
             axisLabel: { color: PALETTE.ink2 }, axisLine, axisTick: { show: false } },
    series: [
      { type: "custom", renderItem: (params, api) => {
          const y = api.coord([0, api.value(0)])[1];
          const x1 = api.coord([api.value(1), 0])[0];
          const x2 = api.coord([api.value(3), 0])[0];
          return { type: "rect", shape: { x: x1, y: y - 3, width: Math.max(x2 - x1, 2), height: 6 },
                   style: { fill: PALETTE.axis } };
        },
        data: d.map((x, i) => [i, x.p25, x.median, x.p75]), encode: { x: [1, 3], y: 0 },
        silent: true },
      { type: "scatter", symbolSize: 11, color: PALETTE.aqua,
        data: d.map((x) => ({ value: [x.median, x.feature], p25: x.p25, p75: x.p75,
                              itemStyle: { opacity: dim(x.feature) } })),
        label: { show: true, position: "right", color: PALETTE.ink,
                 formatter: (p) => p.value[0].toFixed(1) } },
    ],
    tooltip: { ...base.tooltip, formatter: (p) => p.data.p25 === undefined ? "" :
      `<b>${p.value[1]}</b><br>median ${p.value[0]} per active day<br>middle half ${p.data.p25}–${p.data.p75}` },
  }, true);
}

function drawRetention() {
  const d = retentionAll().sort((a, b) =>
    (b.usersRate - b.othersRate) - (a.usersRate - a.othersRate));
  const gapOf = (x) => state.matched ? x.matchedGap : x.rawGap;
  // The gap sits in its own column past the 100% mark rather than trailing the
  // bars, so the numbers line up instead of stepping in and out with each row.
  const GAP_X = 116;
  charts.retention.setOption({
    ...base,
    grid: { ...base.grid, right: 30 },
    legend: { data: ["used the feature", "everyone else"], top: 0, right: 10,
              textStyle: { color: PALETTE.ink2 }, icon: "roundRect" },
    xAxis: { type: "value", max: 124, interval: 20,
             axisLabel: { color: PALETTE.muted,
                          formatter: (v) => v > 100 ? "" : v + "%" },
             splitLine: { lineStyle: { color: PALETTE.grid } }, axisLine },
    yAxis: { type: "category", inverse: true, data: d.map((x) => x.feature),
             axisLabel: { color: PALETTE.ink2 }, axisLine, axisTick: { show: false } },
    series: [
      { name: "used the feature", type: "bar", barGap: "10%", barWidth: "34%",
        color: PALETTE.blue,
        data: d.map((x) => ({ value: +(100 * x.usersRate).toFixed(2), n: x.users,
                              itemStyle: { opacity: dim(x.feature) } })) },
      { name: "everyone else", type: "bar", barWidth: "34%",
        color: PALETTE.orange,
        data: d.map((x) => ({ value: +(100 * x.othersRate).toFixed(2), n: x.others,
                              itemStyle: { opacity: dim(x.feature) } })) },
      { name: "gap", type: "scatter", symbolSize: 0, silent: true,
        color: "transparent", legendHoverLink: false,
        data: d.map((x, i) => ({ value: [GAP_X, i], gap: gapOf(x) })),
        label: { show: true, position: "inside", fontSize: 12.5,
                 color: PALETTE.ink,
                 formatter: (p) => pts(p.data.gap) } },
    ],
    tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (ps) => {
        const i = ps[0].dataIndex, x = d[i];
        if (!x) return "";
        return `<b>${x.feature}</b><br>` +
          `used it: ${pct(x.usersRate)} of ${x.users.toLocaleString()}<br>` +
          `did not: ${pct(x.othersRate)} of ${x.others.toLocaleString()}<br>` +
          `raw gap ${pts(x.rawGap)} &middot; matched ${pts(x.matchedGap)}`;
      } },
  }, true);
}

function drawCurves() {
  const rowsData = curveRows();
  const horizons = state.cube.meta.horizons;
  const bands = [...new Set(rowsData.map((r) => r.n_features))].sort((a, b) => a - b);
  const label = (k) => k >= 5 ? "5+ features" : (k === 1 ? "1 feature" : k + " features");
  const ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab"];
  charts.curves.setOption({
    ...base,
    grid: { left: 52, right: 90, top: 16, bottom: 34 },
    xAxis: { type: "category", data: horizons.map((h) => h + " days"),
             axisLabel: { color: PALETTE.muted }, axisLine, splitLine: { show: false } },
    yAxis: { type: "value", axisLabel: { formatter: (v) => v + "%", color: PALETTE.muted },
             splitLine, axisLine },
    series: bands.map((k, i) => ({
      name: label(k), type: "line", symbolSize: 8, lineStyle: { width: 2 },
      itemStyle: { color: ramp[Math.min(i, ramp.length - 1)] },
      endLabel: { show: true, color: PALETTE.ink2, formatter: label(k) },
      data: horizons.map((h) => {
        const r = rowsData.find((x) => x.n_features === k && x.horizon === h);
        return r && r.n ? +(100 * r.kept / r.n).toFixed(2) : null;
      }),
    })),
    tooltip: { ...base.tooltip, trigger: "axis" },
  }, true);
}

/* ---------- tables ---------- */

function drawPairs() {
  const d = topPairs(8);
  $("#pairs").innerHTML = d.length === 0
    ? '<p class="hint">No pair has enough accounts in this selection.</p>'
    : `<table><tr><th>Pair of features</th><th>Both</th><th>Best one alone</th>
       <th>Lift</th><th>Accounts</th></tr>` +
      d.map((p) => `<tr><td class="name">${p.a} + ${p.b}</td>
        <td>${pct(p.bothRate)}</td><td>${pct(p.bestAlone)}</td>
        <td class="${p.lift >= 0 ? "up" : "down"}">${pts(p.lift)}</td>
        <td>${p.both.toLocaleString()}</td></tr>`).join("") + "</table>";
}

function drawTable() {
  const adopt = new Map(adoptionByFeature().map((a) => [a.feature, a]));
  const freq = new Map(state.cube.frequency.map((f) => [f.feature, f]));
  let d = retentionAll().map((r) => ({
    feature: r.feature,
    accounts: r.users,
    adoption: adopt.get(r.feature) ? adopt.get(r.feature).share : null,
    perDay: freq.get(r.feature) ? freq.get(r.feature).median : null,
    retention: r.usersRate,
    others: r.othersRate,
    raw: r.rawGap,
    matched: r.matchedGap,
  }));
  const { key, dir } = state.sort;
  d.sort((a, b) => ((a[key] ?? -1) - (b[key] ?? -1)) * dir
    || a.feature.localeCompare(b.feature));
  const head = [["feature", "Feature"], ["accounts", "Accounts"],
    ["adoption", "Adoption"], ["perDay", "Per active day"],
    ["retention", "Retention"], ["others", "Everyone else"],
    ["raw", "Raw gap"], ["matched", "Matched gap"]];
  $("#table").innerHTML =
    `<table><tr>${head.map(([k, t]) =>
      `<th data-sort="${k}" class="sortable${k === key ? " on" : ""}">${t}</th>`).join("")}</tr>` +
    d.map((r) => `<tr><td class="name">${r.feature}</td>
      <td>${r.accounts.toLocaleString()}</td><td>${pct(r.adoption)}</td>
      <td>${r.perDay === null ? "—" : r.perDay.toFixed(1)}</td>
      <td>${pct(r.retention)}</td><td>${pct(r.others)}</td>
      <td>${pts(r.raw)}</td>
      <td class="${(r.matched ?? 0) >= 0 ? "up" : "down"}">${pts(r.matched)}</td></tr>`).join("") +
    "</table>";
  $("#table").querySelectorAll("th.sortable").forEach((th) =>
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : -1 };
      drawTable();
    }));
  state.tableRows = d;
}

function downloadCsv() {
  const head = ["feature", "accounts", "adoption", "events_per_active_day",
                "retention", "others_retention", "raw_gap_pts", "matched_gap_pts"];
  const lines = [head.join(",")].concat(state.tableRows.map((r) => [
    `"${r.feature}"`, r.accounts,
    r.adoption === null ? "" : (100 * r.adoption).toFixed(2),
    r.perDay === null ? "" : r.perDay,
    r.retention === null ? "" : (100 * r.retention).toFixed(2),
    r.others === null ? "" : (100 * r.others).toFixed(2),
    r.raw === null ? "" : (100 * r.raw).toFixed(2),
    r.matched === null ? "" : (100 * r.matched).toFixed(2),
  ].join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `github-feature-retention-${state.horizon}d.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- chrome ---------- */

function drawKpis() {
  const a = adoptionByFeature();
  const accounts = a.length ? a[0].accounts : 0;
  const bl = baselineRetention();
  const curve = curveRows().filter((r) => r.horizon === state.horizon);
  const weighted = curve.reduce((s, r) => s + r.n_features * r.n, 0);
  const totalN = curve.reduce((s, r) => s + r.n, 0);
  $("#kpi-accounts").textContent = accounts.toLocaleString();
  $("#kpi-features").textContent = state.cube.meta.features.length;
  $("#kpi-retention").textContent = pct(bl.rate);
  $("#kpi-retention-label").textContent =
    `still active after ${state.horizon} days`;
  $("#kpi-mean").textContent = totalN ? (weighted / totalN).toFixed(1) : "—";
}

function renderAll() {
  drawKpis();
  drawAdoption();
  drawFrequency();
  drawRetention();
  drawCurves();
  drawPairs();
  drawTable();
  $("#matched-note").textContent = state.matched
    ? "Comparing people who were active the same number of days."
    : "Comparing everyone, so part of every gap is just activity.";
}

function chip(text, on, onClick) {
  const el = document.createElement("button");
  el.className = "pill" + (on ? " on" : "");
  el.textContent = text;
  el.addEventListener("click", onClick);
  return el;
}

function buildFilters() {
  const m = state.cube.meta;
  const bandBox = $("#filter-bands");
  const render = () => {
    bandBox.innerHTML = "";
    bandBox.append(chip("All activity", state.bands.size === 0,
      () => { state.bands.clear(); render(); renderAll(); }));
    m.activity_bands.forEach((b) => bandBox.append(chip(b, state.bands.has(b), () => {
      state.bands.has(b) ? state.bands.delete(b) : state.bands.add(b);
      render(); renderAll();
    })));
  };
  render();

  const ageBox = $("#filter-ages");
  const renderAges = () => {
    ageBox.innerHTML = "";
    ageBox.append(chip("Any account age", state.ages.size === 0,
      () => { state.ages.clear(); renderAges(); renderAll(); }));
    m.age_bands.forEach((a) => ageBox.append(chip(a, state.ages.has(a), () => {
      state.ages.has(a) ? state.ages.delete(a) : state.ages.add(a);
      renderAges(); renderAll();
    })));
  };
  renderAges();

  const hBox = $("#filter-horizon");
  const renderH = () => {
    hBox.innerHTML = "";
    m.horizons.forEach((h) => hBox.append(chip(h + " days", state.horizon === h, () => {
      state.horizon = h; renderH(); renderAll();
    })));
  };
  renderH();

  $("#matched").addEventListener("click", () => {
    state.matched = !state.matched;
    $("#matched").classList.toggle("on", state.matched);
    renderAll();
  });
  $("#csv").addEventListener("click", downloadCsv);
}

function highlight(feature) {
  state.feature = state.feature === feature ? null : feature;
  $("#clear-highlight").hidden = !state.feature;
  $("#clear-highlight").textContent = `Showing ${state.feature} · clear`;
  renderAll();
}

async function boot() {
  const res = await fetch("data/features.json");
  state.cube = await res.json();
  const m = state.cube.meta;
  $("#period").textContent = `${m.baseline_start} to ${m.baseline_end}`;

  for (const id of ["adoption", "frequency", "retention", "curves"]) {
    charts[id] = echarts.init($("#chart-" + id), null, { renderer: "canvas" });
    charts[id].on("click", (p) => {
      const name = p.componentType === "series" && p.name && p.seriesType === "scatter"
        ? p.value[1] : p.name;
      if (name && m.features.includes(name)) highlight(name);
    });
  }
  buildFilters();
  renderAll();
  $("#clear-highlight").addEventListener("click", () => highlight(state.feature));
  window.addEventListener("resize", () =>
    Object.values(charts).forEach((c) => c.resize()));
}

boot();
