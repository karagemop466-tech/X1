/* X1 site: shared navigation + JSON-driven table rendering.
 *
 * Every table on the site is rendered from a file under /data/. Each rendered
 * row ends with a "Source" cell linking to the official page the values were
 * read from. A value the official source does not publish is rendered as an
 * em dash and the row is flagged, never filled in from memory.
 */

const NAV = [
  { group: 'Overview', items: [
    { href: 'index.html', label: 'Executive Summary' },
    { href: 'repo-review.html', label: 'Repo Review' },
  ]},
  { group: 'Plan', items: [
    { href: 'requirements.html', label: 'Requirements' },
    { href: 'questions.html', label: 'Open Questions' },
    { href: 'suggestions.html', label: 'Suggestions' },
  ]},
  { group: 'Model', items: [
    { href: 'strategy-lab.html', label: 'Strategy Lab' },
    { href: 'correlations.html', label: 'Correlations' },
    { href: 'lines.html', label: 'Originated Lines' },
  ]},
  { group: 'Data', items: [
    { href: 'standings.html', label: 'Standings' },
    { href: 'team-stats.html', label: 'Team Stats' },
    { href: 'injuries.html', label: 'Injuries & Deficiency' },
    { href: 'depth-charts.html', label: 'Depth Charts' },
    { href: 'data.html', label: 'Data & Verification' },
  ]},
  { group: 'Governance', items: [
    { href: 'flagged.html', label: 'Flagged for Review' },
    { href: 'sources.html', label: 'Sources' },
  ]},
];

/* ------------------------------------------------------------------ nav */
function renderNav() {
  const here = (location.pathname.split('/').pop() || 'index.html');
  const host = document.getElementById('nav');
  if (!host) return;
  let html = '';
  for (const section of NAV) {
    html += '<span class="navgroup">';
    for (const item of section.items) {
      const current = item.href === here ? ' aria-current="page"' : '';
      html += `<a href="${item.href}"${current}>${item.label}</a>`;
    }
    html += '</span>';
  }
  host.innerHTML = html;
}

/* ---------------------------------------------------------------- tables */
const MISSING = '<span class="missing" title="Not published by the official source">&mdash;</span>';

function cell(value) {
  if (value === null || value === undefined || value === '') return MISSING;
  if (typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.length ? value.join(', ') : MISSING;
  return String(value);
}

function sourceCell(row) {
  const urls = row._source_urls && row._source_urls.length ? row._source_urls : [row._source_url];
  if (!urls || !urls[0]) return MISSING;
  const label = row._source_org || 'source';
  const links = urls.map((u, i) =>
    `<a class="src" href="${u}" target="_blank" rel="noopener">${label}${urls.length > 1 ? ' ' + (i + 1) : ''} &#8599;</a>`
  ).join(' ');
  const flag = row._verified ? '' :
    ` <a class="badge warn" href="flagged.html" title="Row flagged for review">flag</a>`;
  return links + flag;
}

function titleCaseHeader(key) {
  const known = {
    W: 'W', L: 'L', T: 'T', PCT: 'PCT', PF: 'PF', PA: 'PA', NET_PTS: 'Net Pts',
    HOME: 'Home', ROAD: 'Road', DIV: 'Div', DIV_PCT: 'Div %', CONF: 'Conf',
    CONF_PCT: 'Conf %', NON_CONF: 'Non-Conf', STRK: 'Streak', LAST_5: 'Last 5',
    team_name: 'Team', player: 'Player', position: 'Pos', injuries: 'Injury',
    practice_status: 'Practice', game_status: 'Game Status', game_date: 'Game Day',
    kickoff_et: 'Kickoff (ET)', broadcast: 'TV', unit: 'Unit', depth: 'String',
    starter: 'Starter', starter_on_report: 'On Injury Report',
    starter_game_status: 'Starter Status',
    starter_practice_status: 'Starter Practice', replacement: 'Next Up',
    replacement_depth: 'Next Up String', replacement_game_status: 'Next Up Status',
    severity: 'Severity', depth_listed: 'Depth Listed',
  };
  if (known[key]) return known[key];
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function getRows(payload, tableName) {
  if (!tableName) return payload.rows || [];
  const found = (payload.tables || []).find((t) => t.id === tableName);
  return found ? found.rows || [] : [];
}

function getColumns(payload, tableName, declared) {
  if (declared) return declared.split(',').map((s) => s.trim());
  if (tableName) {
    const found = (payload.tables || []).find((t) => t.id === tableName);
    if (found) return found.columns.filter((c) => c !== 'team_name').length
      ? found.columns : Object.keys((found.rows || [])[0] || {}).filter((k) => !k.startsWith('_'));
  }
  if (payload.columns && payload.columns.length) return payload.columns;
  return Object.keys((payload.rows || [])[0] || {}).filter((k) => !k.startsWith('_'));
}

const state = {};

function render(table, payload) {
  const id = table.id;
  const cfg = state[id];
  let rows = getRows(payload, table.dataset.table);
  const columns = getColumns(payload, table.dataset.table, table.dataset.columns);

  if (cfg.query) {
    const q = cfg.query.toLowerCase();
    rows = rows.filter((r) => columns.concat(['team_name', 'player']).some((c) =>
      String(r[c] ?? '').toLowerCase().includes(q)));
  }
  if (cfg.flaggedOnly) rows = rows.filter((r) => !r._verified);
  if (cfg.status && cfg.status !== 'all') {
    rows = rows.filter((r) => String(r.game_status || 'not listed').toLowerCase() === cfg.status);
  }
  if (cfg.team && cfg.team !== 'all') rows = rows.filter((r) => r.team_abbrev === cfg.team);

  const total = rows.length;
  const per = Number(table.dataset.page || 60);
  const pages = Math.max(1, Math.ceil(total / per));
  if (cfg.page > pages) cfg.page = pages;
  const start = (cfg.page - 1) * per;
  const slice = rows.slice(start, start + per);

  let html = '<thead><tr>';
  for (const col of columns) {
    const cls = ['W', 'L', 'T', 'PCT', 'PF', 'PA', 'NET_PTS', 'depth', 'severity'].includes(col) ? ' class="num"' : '';
    html += `<th${cls}>${titleCaseHeader(col)}</th>`;
  }
  html += '<th>Source</th></tr></thead><tbody>';

  for (const row of slice) {
    html += row._verified ? '<tr>' : '<tr class="flagged">';
    for (const col of columns) {
      const cls = ['W', 'L', 'T', 'PCT', 'PF', 'PA', 'NET_PTS', 'depth', 'severity'].includes(col) ? ' class="num"' : '';
      const wrap = ['question', 'answer', 'suggestion', 'rationale', 'hypothesis', 'note',
                    'requirement', 'missing_information', 'method', 'description',
                    'impact', 'gate', 'finding', 'detail', 'recommendation', 'next_step',
                    'definition', 'why_it_matters', 'path_options'].includes(col) ? ' class="wrap-ok"' : (cls || '');
      html += `<td${wrap}>${cell(row[col])}</td>`;
    }
    html += `<td>${sourceCell(row)}</td></tr>`;
  }
  if (!slice.length) {
    html += `<tr><td colspan="${columns.length + 1}" class="missing">No rows match this filter.</td></tr>`;
  }
  html += '</tbody>';
  table.innerHTML = html;

  const count = document.querySelector(`[data-count-for="${id}"]`);
  if (count) {
    count.textContent = total
      ? `Showing ${start + 1}–${Math.min(start + per, total)} of ${total}`
      : 'No rows';
  }
  const pager = document.querySelector(`[data-pager-for="${id}"]`);
  if (pager) {
    pager.innerHTML = `
      <button data-page-step="-1" ${cfg.page <= 1 ? 'disabled' : ''}>Prev</button>
      <span>Page ${cfg.page} of ${pages}</span>
      <button data-page-step="1" ${cfg.page >= pages ? 'disabled' : ''}>Next</button>`;
    pager.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        cfg.page += Number(btn.dataset.pageStep);
        render(table, state[id].payload);
      });
    });
  }
  const flagged = rows.filter((r) => !r._verified).length;
  const badge = document.querySelector(`[data-badge-for="${id}"]`);
  if (badge) {
    badge.innerHTML = flagged
      ? `<span class="badge ok">${rows.length - flagged} verified</span> <span class="badge warn">${flagged} flagged</span>`
      : `<span class="badge ok">${rows.length} verified</span>`;
  }
}

async function boot() {
  renderNav();
  const tables = document.querySelectorAll('table[data-src]');
  for (const table of tables) {
    const id = table.id;
    state[id] = { query: '', flaggedOnly: false, page: 1, status: 'all', team: 'all' };
    try {
      const res = await fetch(table.dataset.src, { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const payload = await res.json();
      state[id].payload = payload;
      if (table.dataset.autofill === 'team' && payload.rows) {
        fillTeamFilter(id, payload.rows);
      }
      render(table, payload);
      const meta = document.querySelector(`[data-meta-for="${id}"]`);
      if (meta && payload.generated_at) {
        meta.textContent = `Official source data pulled ${payload.generated_at.replace('T', ' ').replace('+00:00', ' UTC')}`;
      }
    } catch (err) {
      table.innerHTML = `<tbody><tr><td class="missing">Could not load ${table.dataset.src} — ${err.message}. Run the data-refresh workflow to populate it.</td></tr></tbody>`;
    }
  }

  document.querySelectorAll('input[data-filter-for]').forEach((input) => {
    input.addEventListener('input', () => {
      const id = input.dataset.filterFor;
      state[id].query = input.value.trim();
      state[id].page = 1;
      const table = document.getElementById(id);
      if (table && state[id].payload) render(table, state[id].payload);
    });
  });
  document.querySelectorAll('input[data-flagged-for]').forEach((box) => {
    box.addEventListener('change', () => {
      const id = box.dataset.flaggedFor;
      state[id].flaggedOnly = box.checked;
      state[id].page = 1;
      const table = document.getElementById(id);
      if (table && state[id].payload) render(table, state[id].payload);
    });
  });
  document.querySelectorAll('select[data-status-for]').forEach((sel) => {
    sel.addEventListener('change', () => {
      const id = sel.dataset.statusFor;
      state[id].status = sel.value;
      state[id].page = 1;
      const table = document.getElementById(id);
      if (table && state[id].payload) render(table, state[id].payload);
    });
  });
  document.querySelectorAll('select[data-team-for]').forEach((sel) => {
    sel.addEventListener('change', () => {
      const id = sel.dataset.teamFor;
      state[id].team = sel.value;
      state[id].page = 1;
      const table = document.getElementById(id);
      if (table && state[id].payload) render(table, state[id].payload);
    });
  });
}

function fillTeamFilter(id, rows) {
  const sel = document.querySelector(`select[data-team-for="${id}"]`);
  if (!sel) return;
  const seen = new Map();
  for (const row of rows) {
    if (row.team_abbrev && row.team_name) seen.set(row.team_abbrev, row.team_name);
  }
  const sorted = [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  sel.innerHTML = '<option value="all">All teams</option>' +
    sorted.map(([ab, name]) => `<option value="${ab}">${name}</option>`).join('');
}

// Exposed so a page can switch which table inside a dataset it is showing
// (team-stats has nine) and re-render without reloading the page.
window.__x1Reload = function (id) {
  const table = document.getElementById(id);
  if (table && state[id] && state[id].payload) render(table, state[id].payload);
};
window.__x1Rows = function (id) {
  const table = document.getElementById(id);
  if (!table || !state[id] || !state[id].payload) return [];
  return getRows(state[id].payload, table.dataset.table);
};

document.addEventListener('DOMContentLoaded', boot);
