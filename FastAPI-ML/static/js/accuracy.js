const radarCharts = {}, tsCharts = {}, trendCharts = {};
const CITY_LABELS = { luzern: 'Luzern', basel: 'Basel', bern: 'Bern',
                      zurich: 'Zürich', stgallen: 'St. Gallen' };

function days() { return document.getElementById('days-select').value; }
function scope() { return document.getElementById('scope-select').value; }

async function loadSummary() {
  const data = await Api.get('/api/accuracy/summary', { days: days(), scope: scope() });
  const global = data.entries.filter(e => e.scope === 'global' || e.scope === scope());

  [1, 2, 4, 8].forEach(h => {
    const ml = global.find(e => e.model_type === 'ml' && e.horizon_h === h);
    const base = global.find(e => e.model_type === 'baseline' && e.horizon_h === h);
    const el = document.getElementById('kpi-' + h);
    if (!el) return;
    if (!ml && !base) { el.innerHTML = '<span class="text-muted small">Keine Daten</span>'; return; }
    const skill = ml?.skill;
    el.innerHTML = `
      <div class="kpi-label">Prognose +${h} h</div>
      <div class="kpi-value">±${(ml || base).mae_free.toFixed(1)}</div>
      <div class="small text-muted">
        Basis: ±${base ? base.mae_free.toFixed(1) : '–'}
        ${skill != null ? ` · <span class="${skill >= 0 ? 'skill-pos' : 'skill-neg'}">${(skill * 100).toFixed(0)} % besser</span>` : ''}
      </div>
      <div class="small text-muted">${(ml || base).n} Auswertungen</div>`;
  });

  drawRadarCharts(data.entries);
}

function drawRadarCharts(entries) {
  const cities = [...new Set(entries.filter(e => e.scope !== 'global').map(e => e.scope))];
  const labels = cities.map(c => CITY_LABELS[c] || c);

  [1, 2, 4, 8].forEach(h => {
    const canvas = document.getElementById('radar-' + h);
    if (!canvas) return;

    const mlData = cities.map(c => {
      const e = entries.find(x => x.scope === c && x.model_type === 'ml' && x.horizon_h === h);
      return e ? e.mae_free : null;
    });
    const baseData = cities.map(c => {
      const e = entries.find(x => x.scope === c && x.model_type === 'baseline' && x.horizon_h === h);
      return e ? e.mae_free : null;
    });

    if (radarCharts[h]) radarCharts[h].destroy();
    radarCharts[h] = new Chart(canvas, {
      type: 'radar',
      data: {
        labels,
        datasets: [
          {
            label: 'Basis',
            data: baseData,
            borderColor: '#fd7e14',
            backgroundColor: 'rgba(253, 126, 20, 0.15)',
            borderWidth: 1.5,
            pointRadius: 2,
          },
          {
            label: 'KI-Modell',
            data: mlData,
            borderColor: '#198754',
            backgroundColor: 'rgba(25, 135, 84, 0.15)',
            borderWidth: 1.5,
            pointRadius: 2,
          },
        ],
      },
      options: {
        scales: {
          r: {
            beginAtZero: true,
            ticks: { display: false },
            pointLabels: { font: { size: 10 } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ±${ctx.parsed.r.toFixed(1)}`,
            },
          },
        },
      },
    });
  });
}

// --- Hilfsfunktion: 7-Tage gleitender Durchschnitt ---

function movingAvg(data, window) {
  return data.map((_, i) => {
    const start = Math.max(0, i - window + 1);
    const slice = data.slice(start, i + 1).filter(v => v != null);
    return slice.length >= Math.min(3, window) ? slice.reduce((a, b) => a + b) / slice.length : null;
  });
}

// --- Übersicht: kleine Timeseries ---

async function loadAllTimeseries() {
  const sc = scope();
  const tsScope = sc === 'global' ? 'global' : 'city:' + sc;

  for (const h of [1, 2, 4, 8]) {
    const canvas = document.getElementById('ts-' + h);
    if (!canvas) continue;

    const data = await Api.get('/api/accuracy/timeseries', { scope: tsScope, horizon: h, days: days() });
    const daysAxis = [...new Set(Object.values(data.series).flat().map(p => p.day))].sort();
    const mlData = daysAxis.map(d => (data.series.ml || []).find(p => p.day === d)?.mae_free ?? null);
    const baseData = daysAxis.map(d => (data.series.baseline || []).find(p => p.day === d)?.mae_free ?? null);
    const datasets = [
      { label: 'Basis', borderColor: '#fd7e14', tension: 0.2, pointRadius: 0, borderWidth: 1, borderDash: [3, 2], data: baseData },
      { label: 'KI', borderColor: 'rgba(25, 135, 84, 0.3)', tension: 0.2, pointRadius: 0, borderWidth: 1, data: mlData },
      { label: 'KI Trend', borderColor: '#198754', tension: 0.3, pointRadius: 0, borderWidth: 2.5, data: movingAvg(mlData, 7) },
    ];

    if (tsCharts[h]) tsCharts[h].destroy();
    tsCharts[h] = new Chart(canvas, {
      type: 'line',
      data: { labels: daysAxis, datasets },
      options: {
        scales: {
          x: { display: false },
          y: { beginAtZero: true, ticks: { font: { size: 10 } } },
        },
        plugins: {
          legend: { display: false },
          title: { display: true, text: `+${h} h`, font: { size: 11 }, padding: 2 },
        },
      },
    });
  }
}

// --- Trend-Tab: kompakte Charts mit Trendlinie ---

let trendAllChart = null;

function trendChartOpts(title) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        ticks: { maxTicksLimit: 5, font: { size: 8 }, callback(val) {
          const d = this.getLabelForValue(val);
          return d ? d.slice(5).replace('-', '.') : '';
        }},
        grid: { display: false },
      },
      y: { beginAtZero: true, ticks: { font: { size: 8 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
    },
    plugins: {
      legend: { display: false },
      title: { display: true, text: title, font: { size: 10, weight: 'bold' }, padding: { top: 2, bottom: 4 } },
      tooltip: { callbacks: {
        title(items) { const d = items[0]?.label; if (!d) return ''; const [y,m,dd] = d.split('-'); return `${dd}.${m}.${y}`; },
        label(ctx) { return `${ctx.dataset.label}: ±${ctx.parsed.y?.toFixed(1) ?? '–'}`; },
      }},
    },
  };
}

async function loadTrend() {
  const trendDays = parseInt(document.getElementById('trend-days').value);
  const sc = scope();
  const tsScope = sc === 'global' ? 'global' : 'city:' + sc;

  // Daten fuer alle Horizonte laden
  let allDays = new Set();
  const mlByDay = {}, baseByDay = {};
  const perHorizon = {};
  for (const h of [1, 2, 4, 8]) {
    const data = await Api.get('/api/accuracy/timeseries', { scope: tsScope, horizon: h, days: trendDays });
    perHorizon[h] = data.series;
    for (const p of (data.series.ml || [])) {
      allDays.add(p.day);
      (mlByDay[p.day] = mlByDay[p.day] || []).push(p.mae_free);
    }
    for (const p of (data.series.baseline || [])) {
      (baseByDay[p.day] = baseByDay[p.day] || []).push(p.mae_free);
    }
  }
  const daysAxis = [...allDays].sort();
  const avgArr = obj => daysAxis.map(d => {
    const vals = obj[d];
    return vals?.length ? vals.reduce((a, b) => a + b) / vals.length : null;
  });

  // 1. Kombiniertes Chart: Ø aller Horizonte
  const allCanvas = document.getElementById('trend-all');
  if (allCanvas) {
    const mlAvg = avgArr(mlByDay);
    const baseAvg = avgArr(baseByDay);
    if (trendAllChart) trendAllChart.destroy();
    trendAllChart = new Chart(allCanvas, {
      type: 'line',
      data: { labels: daysAxis, datasets: [
        { label: 'Basis', borderColor: '#fd7e14', borderWidth: 1, borderDash: [3, 2], pointRadius: 0, tension: 0.2, data: baseAvg },
        { label: 'KI', borderColor: 'rgba(25, 135, 84, 0.3)', borderWidth: 1, pointRadius: 0, tension: 0.2, data: mlAvg },
        { label: 'KI Trend', borderColor: '#198754', borderWidth: 2.5, pointRadius: 0, tension: 0.3, data: movingAvg(mlAvg, 7) },
      ]},
      options: trendChartOpts('Ø Gesamt'),
    });
  }

  // 2. Pro Horizont
  for (const h of [1, 2, 4, 8]) {
    const canvas = document.getElementById('trend-' + h);
    if (!canvas) continue;
    const series = perHorizon[h] || {};
    const mlData = daysAxis.map(d => (series.ml || []).find(p => p.day === d)?.mae_free ?? null);
    const baseData = daysAxis.map(d => (series.baseline || []).find(p => p.day === d)?.mae_free ?? null);

    if (trendCharts[h]) trendCharts[h].destroy();
    trendCharts[h] = new Chart(canvas, {
      type: 'line',
      data: { labels: daysAxis, datasets: [
        { label: 'Basis', borderColor: '#fd7e14', borderWidth: 1, borderDash: [3, 2], pointRadius: 0, tension: 0.2, data: baseData },
        { label: 'KI', borderColor: 'rgba(25, 135, 84, 0.3)', borderWidth: 1, pointRadius: 0, tension: 0.2, data: mlData },
        { label: 'KI Trend', borderColor: '#198754', borderWidth: 2.5, pointRadius: 0, tension: 0.3, data: movingAvg(mlData, 7) },
      ]},
      options: trendChartOpts(`+${h} h`),
    });
  }

  // Runs-Tabelle im Trend-Tab
  const runs = await Api.get('/api/accuracy/runs');
  const mlRuns = runs.filter(r => r.model_type === 'ml');
  document.getElementById('trend-runs-table').innerHTML = mlRuns.map(r => {
    const cvMae = r.cv_mae_occ != null ? r.cv_mae_occ.toFixed(1) + ' pp' : '–';
    const holdMae = r.cv_mae_free != null ? '±' + r.cv_mae_free.toFixed(1) : '–';
    const r2 = r.cv_r2 != null ? r.cv_r2.toFixed(3) : '–';
    return `<tr${r.is_active ? ' class="table-success"' : ''}>
      <td>${new Date(r.trained_at).toLocaleString('de-CH', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
      <td>+${r.horizon_h} h</td>
      <td class="text-end">${holdMae}</td>
      <td class="text-end">${cvMae}</td>
      <td class="text-end">${r2}</td>
      <td>${r.is_active ? '✅' : ''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="text-muted">Keine ML-Läufe</td></tr>';
}

async function loadPerParkhaus() {
  const city = document.getElementById('city-select').value;
  if (!city) return;
  const horizon = document.getElementById('ph-horizon').value;
  const data = await Api.get(`/api/accuracy/parkhaus/${city}`, { days: days(), horizon });
  const byHouse = {};
  for (const e of data.entries) {
    const g = byHouse[e.scope] = byHouse[e.scope] || { name: e.name };
    g[e.model_type] = e;
  }
  const rows = Object.values(byHouse)
    .sort((a, b) => (a.ml?.mae_free ?? 1e9) - (b.ml?.mae_free ?? 1e9))
    .map(g => {
      const skill = g.ml?.skill;
      const better = skill != null && skill < 0;
      return `<tr class="${better ? 'table-warning' : ''}">
        <td>${g.name}</td>
        <td class="text-end">${g.ml ? '±' + g.ml.mae_free.toFixed(1) : '–'}</td>
        <td class="text-end">${g.baseline ? '±' + g.baseline.mae_free.toFixed(1) : '–'}</td>
        <td class="text-end">${skill != null
          ? `<span class="${skill >= 0 ? 'skill-pos' : 'skill-neg'}">${(skill * 100).toFixed(0)} %</span>` : '–'}</td>
        <td class="text-end">${g.ml?.n ?? g.baseline?.n ?? 0}</td>
      </tr>`;
    }).join('');
  document.getElementById('ph-table').innerHTML =
    rows || '<tr><td colspan="5" class="text-muted">Keine Daten</td></tr>';
}

async function loadRuns() {
  const runs = await Api.get('/api/accuracy/runs');
  document.getElementById('runs-table').innerHTML = runs.slice(0, 15).map(r => `
    <tr>
      <td class="small">${new Date(r.trained_at).toLocaleString('de-CH')}</td>
      <td class="small">${r.model_type === 'ml' ? 'KI +' + r.horizon_h + ' h' : 'Basis'}</td>
      <td class="text-end small">${r.cv_mae_free != null ? '±' + r.cv_mae_free.toFixed(1) : '–'}</td>
      <td>${r.is_active ? '✅' : ''}</td>
    </tr>`).join('');
}

async function initCitySelectors() {
  const cities = await Api.get('/api/cities');
  document.getElementById('city-select').innerHTML =
    cities.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
  const scopeSel = document.getElementById('scope-select');
  scopeSel.innerHTML = '<option value="global" selected>Gesamt</option>' +
    cities.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
}

function loadOverview() {
  loadSummary();
  loadAllTimeseries();
}

document.addEventListener('DOMContentLoaded', async () => {
  await initCitySelectors();
  Merker.binden('scope-select', 'global', () => { loadOverview(); loadTrend(); });
  Merker.binden('days-select', '14', () => { loadOverview(); loadPerParkhaus(); });
  Merker.binden('city-select', null, loadPerParkhaus);
  Merker.binden('ph-horizon', '1', loadPerParkhaus);

  const trendDaysSel = document.getElementById('trend-days');
  if (trendDaysSel) {
    trendDaysSel.addEventListener('change', loadTrend);
  }

  // Trend-Tab beim ersten Anklicken laden
  const trendTab = document.getElementById('tab-trend');
  if (trendTab) {
    let trendLoaded = false;
    trendTab.addEventListener('shown.bs.tab', () => {
      if (!trendLoaded) { trendLoaded = false; }
      loadTrend();
    });
  }

  await Promise.all([loadOverview(), loadPerParkhaus(), loadRuns()]);
});
