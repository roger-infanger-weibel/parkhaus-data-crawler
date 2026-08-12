const radarCharts = {};
let tsChart = null;
const CITY_LABELS = { luzern: 'Luzern', basel: 'Basel', bern: 'Bern',
                      zurich: 'Zürich', stgallen: 'St. Gallen' };

function days() { return document.getElementById('days-select').value; }

async function loadSummary() {
  const data = await Api.get('/api/accuracy/summary', { days: days() });
  const global = data.entries.filter(e => e.scope === 'global');

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

async function loadTimeseries() {
  const scope = document.getElementById('ts-scope').value;
  const horizon = document.getElementById('ts-horizon').value;
  const data = await Api.get('/api/accuracy/timeseries', { scope, horizon, days: 60 });
  const daysAxis = [...new Set(Object.values(data.series).flat().map(p => p.day))].sort();
  const colors = { ml: '#198754', baseline: '#fd7e14' };
  const datasets = Object.entries(data.series).map(([mt, points]) => ({
    label: mt === 'ml' ? 'KI-Modell' : 'Basis',
    borderColor: colors[mt], tension: 0.2, pointRadius: 2,
    data: daysAxis.map(d => points.find(p => p.day === d)?.mae_free ?? null),
  }));
  if (tsChart) tsChart.destroy();
  tsChart = new Chart(document.getElementById('ts-chart'), {
    type: 'line',
    data: { labels: daysAxis, datasets },
    options: {
      scales: { y: { beginAtZero: true, title: { display: true, text: 'MAE (Plätze)' } } },
      plugins: { legend: { position: 'bottom' } },
    },
  });
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
  const tsScope = document.getElementById('ts-scope');
  tsScope.innerHTML = '<option value="global" selected>Gesamt</option>' +
    cities.map(c => `<option value="city:${c.id}">${c.name}</option>`).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
  await initCitySelectors();
  // Zuletzt gewaehlte Einstellungen wiederherstellen und kuenftig merken
  Merker.binden('days-select', '14', () => { loadSummary(); loadPerParkhaus(); });
  // Radar-Charts werden direkt in loadSummary gezeichnet
  Merker.binden('ts-scope', 'global', loadTimeseries);
  Merker.binden('ts-horizon', '1', loadTimeseries);
  Merker.binden('city-select', null, loadPerParkhaus);
  Merker.binden('ph-horizon', '1', loadPerParkhaus);

  await Promise.all([loadSummary(), loadTimeseries(), loadPerParkhaus(), loadRuns()]);
});
