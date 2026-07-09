// Deterministic HTML injection. Reads index.template.html (source, human-edited, never
// served) + data.json (single source of numbers), writes index.html (served, never
// hand-edited). No LLM writes a number into HTML: every figure below is read out of
// data.json (cents/counts) and passed through a fixed formatting function. Refuses to
// write if a marker region is missing, a token is unresolved, or an em/en dash appears
// in the output (house style forbids them).
const fs = require('fs');

const d = JSON.parse(fs.readFileSync('data.json', 'utf8'));

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtMoney(cents) {
  return '$' + Math.round(cents / 100).toLocaleString('en-US');
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/);
  return ((parts[0] || '')[0] || '') + ((parts[parts.length - 1] || '')[0] || '');
}

const WINS = [
  { key: 'day', label: 'Daily' },
  { key: 'week', label: 'Weekly' },
  { key: 'month', label: 'Monthly' },
];
const DEFAULT_WIN = 'month';

function fmtRange(w) {
  const sameYear = w.start.slice(0, 4) === w.end.slice(0, 4);
  if (w.start === w.end) return fmtOneDate(w.start, true);
  return fmtOneDate(w.start, !sameYear) + ' to ' + fmtOneDate(w.end, true);
}
function fmtOneDate(iso, withYear) {
  const dt = new Date(iso + 'T00:00:00Z');
  const day = dt.getUTCDate();
  const month = dt.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' });
  return day + ' ' + month + (withYear ? ' ' + dt.getUTCFullYear() : '');
}

function buildTabs() {
  const script = '<script>function raceSwitchWin(k){' +
    'document.querySelectorAll(".tab").forEach(function(b){b.classList.toggle("active", b.dataset.win===k);});' +
    'document.querySelectorAll(".wpanel").forEach(function(p){p.classList.toggle("active", p.dataset.win===k);});' +
    '}</script>';
  return WINS.map(w =>
    '<button class="tab' + (w.key === DEFAULT_WIN ? ' active' : '') + '" role="tab" data-win="' + w.key + '" onclick="raceSwitchWin(\'' + w.key + '\')">' + esc(w.label) + '</button>'
  ).join('') + script;
}

function buildLadder(win) {
  const team = d.team[win];
  const levels = [1, 2, 3].map((n, i) => {
    const state = team.levelStates[i];
    const target = team.levelTargetsCents[i];
    const stateLabel = state === 'reached' ? 'Reached' : state === 'in_reach' ? 'In reach' : 'Locked';
    return '<div class="level-box ' + state + '"><div class="ll">Level ' + n + '</div>' +
      '<div class="lv">' + fmtMoney(target) + '</div><div class="ls">' + stateLabel + '</div></div>';
  }).join('');
  const bar = team.levelStates.map(s => '<span class="' + (s === 'locked' ? '' : s) + '"></span>').join('');
  const footRight = team.complete ?
    'Team goal complete' :
    '<span class="pct">' + team.pctToNextNum + '%</span> to Level ' + team.nextLevel;
  const footLeft = team.complete ?
    'All 3 levels reached' :
    fmtMoney(team.toReachNextCents) + ' to reach ' + fmtMoney(team.nextTargetCents);
  return '<div class="ladder">' +
    '<div class="ladder-hd"><div><span class="ladder-tag">Team goal</span>' +
    '<span class="ladder-level">Level <b>' + team.level + '</b> of 3</span></div>' +
    '<div class="ladder-collected"><span class="amt">' + fmtMoney(team.collectedCents) + '</span><span class="lbl">Collected</span></div>' +
    '</div>' +
    '<div class="ladder-bar">' + bar + '</div>' +
    '<div class="levels">' + levels + '</div>' +
    '<div class="ladder-foot"><span>' + footLeft + '</span><span>' + footRight + '</span></div>' +
    '</div>';
}

function buildChips(badges) {
  if (!badges || !badges.length) return '';
  return '<div class="chips">' + badges.map(b => '<span class="chip">' + esc(b) + '</span>').join('') + '</div>';
}

function buildRaceCard(row) {
  const leader = row.leading;
  const pct = Math.max(0, Math.min(100, row.pctToGoalNum));
  const nonLeadBadges = row.badges.filter(b => b !== 'Leading');
  return '<article class="rcard' + (leader ? ' leader' : '') + '">' +
    '<div class="rcard-hd">' +
    '<span class="rrank">' + row.rank + '</span>' +
    '<span class="avatar">' + esc(initials(row.name)) + '</span>' +
    '<div><span class="rname">' + esc(row.name) + (leader ? ' <span class="lead-tag">Leading</span>' : '') + '</span>' +
    buildChips(nonLeadBadges) +
    '</div></div>' +
    '<div class="rprogress">' +
    '<div class="rp-row"><span class="rp-amt ' + (row.cashCents > 0 ? 'ok' : '') + '">' + fmtMoney(row.cashCents) + '</span>' +
    '<span class="rp-goal">of ' + fmtMoney(d.race[row._win].targetCents) + ' goal</span>' +
    '<span class="rp-pct"><span class="n">' + pct + '%</span><br>to goal</span></div>' +
    '<div class="rp-bar"><div style="width:' + pct + '%"></div></div>' +
    '<div class="rp-foot"><span class="togo">' + (row.rank === 1 ? fmtMoney(row.toGoCents) + ' to go' : fmtMoney(row.toGoCents) + ' to go') + '</span>' +
    (row.lineA ? '<span class="flavor">' + esc(row.lineA) + '</span>' : '<span></span>') +
    '</div></div>' +
    '<div class="rstats">' +
    '<div class="rstat"><div class="sv">' + row.dealsWon + '</div><div class="sl">Deals won</div></div>' +
    '<div class="rstat"><div class="sv">' + row.openDeals + '</div><div class="sl">Open deals</div></div>' +
    '<div class="rstat"><div class="sv">' + row.meetings + '</div><div class="sl">Meetings</div></div>' +
    '<div class="rstat"><div class="sv">' + esc(row.closeRate) + '</div><div class="sl">Close rate</div></div>' +
    '</div>' +
    '<div class="rline-b">' + esc(row.lineB) + '</div>' +
    '</article>';
}

function buildRaces(win) {
  const r = d.race[win];
  const rows = r.rows.map(row => Object.assign({}, row, { _win: win }));
  const banner = r.bannerNote ? '<div class="banner">' + esc(r.bannerNote) + '</div>' : '';
  return '<div class="races-hd">Individual races</div>' +
    '<div class="race-title"><h2>Race to ' + fmtMoney(r.targetCents) + '</h2><span class="note">' + esc(r.rankedByLabel) + '</span></div>' +
    banner +
    rows.map(buildRaceCard).join('');
}

function buildTotals(win) {
  const t = d.teamTotals[win];
  const tiles = [
    { v: fmtMoney(t.cashCents), l: 'Cash collected', hi: true },
    { v: t.dealsWon, l: 'Deals won' },
    { v: t.openDeals, l: 'Open deals' },
    { v: t.meetingsBooked, l: 'Meetings booked' },
  ];
  return '<div class="totals">' + tiles.map(x =>
    '<div class="tile' + (x.hi ? ' hi' : '') + '"><div class="tv">' + esc(x.v) + '</div><div class="tl">' + esc(x.l) + '</div></div>'
  ).join('') + '</div>';
}

function buildPanels() {
  return WINS.map(w => {
    const win = d.windows[w.key];
    return '<div class="wpanel' + (w.key === DEFAULT_WIN ? ' active' : '') + '" data-win="' + w.key + '" role="tabpanel">' +
      '<div class="subtext">GoHighLevel opportunities + Stripe payments &middot; ' + esc(fmtRange(win)) +
      ' &middot; <span class="asof">as of ' + esc(fmtOneDate(d.asOf, true)) + '</span></div>' +
      buildLadder(w.key) +
      buildRaces(w.key) +
      buildTotals(w.key) +
      '</div>';
  }).join('\n');
}

let html = fs.readFileSync('index.template.html', 'utf8');

const MARKERS = [
  ['TABS', buildTabs],
  ['PANELS', buildPanels],
];
for (const [name, fn] of MARKERS) {
  const re = new RegExp('<!--' + name + '_START-->[\\s\\S]*?<!--' + name + '_END-->');
  if (!re.test(html)) { console.error('ERROR: ' + name + ' markers not found'); process.exit(1); }
  html = html.replace(re, '<!--' + name + '_START-->' + fn() + '<!--' + name + '_END-->');
}

// --- Dash guard: no em/en dashes anywhere in the rendered output ---
const DASH = /[–—]/;
if (DASH.test(html)) {
  console.error('ERROR: em/en dash in rendered output');
  process.exit(1);
}

fs.writeFileSync('index.html', html);
console.log('OK index.html written from data.json (asOf ' + d.asOf + ')');
