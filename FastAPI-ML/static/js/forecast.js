let current = null;
let detailChart = null;
let selectedPls = null;

function model() {
  return document.querySelector('input[name="model"]:checked').value;
}

async function loadCities() {
  const cities = await Api.get('/api/cities');
  const sel = document.getElementById('city-select');
  sel.innerHTML = cities.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
  sel.value = localStorage.getItem('ai_city') || cities[0]?.id;
  sel.addEventListener('change', () => {
    localStorage.setItem('ai_city', sel.value);
    selectedPls = null;
    loadForecasts();
  });
}

function horizonCell(house, h) {
  const entry = house.horizons?.[h]?.[model()];
  if (!entry) return '<td class="text-end text-muted">–</td>';
  const cls = freeBadgeClass(entry.free, house.total);
  // Zielzeit in den Tooltip: die Spalte heisst "+1 h", gemeint ist aber immer
  // eine Stunde nach dem Prognosestand - nicht nach jetzt.
  const title = `Prognose für ${fmtTs(entry.target_time)} Uhr`;
  return `<td class="text-end" title="${title}">` +
    `<span class="badge ${cls}">${entry.free}</span></td>`;
}

// Rueckblick: nur die Veraenderung bis jetzt. Der Ist-Wert von damals steht
// im Tooltip, damit die Zeile nicht mit Zahlen zugestellt wird.
function historyCell(house, offset) {
  const entry = house.history?.[offset];
  if (!entry) return '<td class="text-end text-muted">–</td>';
  // delta = frei jetzt minus frei damals:
  //   positiv  -> Autos sind weggefahren, mehr Platz  -> gruen
  //   negativ  -> Autos sind dazugekommen, weniger Platz -> rot
  const d = entry.delta;
  const arrow = d > 0 ? '▲' : (d < 0 ? '▼' : '=');
  const cls = d > 0 ? 'delta-up' : (d < 0 ? 'delta-down' : 'text-muted');
  const title = `vor ${offset} h: ${entry.free} frei (${fmtTs(entry.ts)})`;
  // Klasse am span, nicht am td: Bootstrap setzt die Textfarbe der Zelle
  // selbst und wuerde sie sonst ueberschreiben.
  return `<td class="text-end" title="${title}">` +
    `<span class="${cls}">${arrow}${d === 0 ? '' : Math.abs(d)}</span></td>`;
}

async function loadForecasts() {
  const city = document.getElementById('city-select').value;
  const data = await Api.get(`/api/forecast/current/${city}`);
  current = data;
  // Veraltete Prognosen deutlich kennzeichnen: die Spalten "+1 h" usw. zaehlen
  // ab dem Prognosestand. Ist der alt, zeigen sie einen laengst vergangenen
  // Zeitpunkt neben dem aktuellen Ist-Wert - das liest sich sonst wie ein
  // dramatischer Einbruch, der gar keiner ist.
  const info = document.getElementById('slot-info');
  if (!data.slot) {
    info.className = 'col-auto ms-auto text-danger small';
    info.textContent = 'Noch keine Prognosen vorhanden';
  } else {
    const ageMin = Math.round((Date.now() - new Date(data.slot)) / 60000);
    if (ageMin > 30) {
      info.className = 'col-auto ms-auto text-danger small fw-semibold';
      info.textContent = `⚠️ Prognose veraltet: Stand ${fmtTs(data.slot)} Uhr ` +
        `(${ageMin} Min alt). Die Spalten +1 h bis +8 h zählen ab diesem ` +
        `Zeitpunkt, nicht ab jetzt.`;
    } else {
      info.className = 'col-auto ms-auto text-muted small';
      info.textContent = `Prognosestand: ${fmtTs(data.slot)} Uhr`;
    }
  }
  const rows = data.houses.map(h => `
    <tr data-pls="${h.pls_id}">
      <td>${h.name}${h.group ? `<br><small class="text-muted">${h.group}</small>` : ''}</td>
      ${historyCell(h, 2)}
      ${historyCell(h, 1)}
      <td class="text-end"><strong>${h.free_now}</strong><small class="text-muted">/${h.total}</small></td>
      ${[1, 2, 4, 8].map(hz => horizonCell(h, hz)).join('')}
      <td><small class="text-muted">${fmtTs(h.fetch_ts)}</small></td>
    </tr>`).join('');
  document.getElementById('forecast-table').innerHTML =
    rows || '<tr><td colspan="9">Keine Daten</td></tr>';
  document.querySelectorAll('#forecast-table tr[data-pls]').forEach(tr => {
    tr.addEventListener('click', () => loadDetail(tr.dataset.pls));
  });
  if (selectedPls) loadDetail(selectedPls);
}

async function loadDetail(plsId) {
  selectedPls = plsId;
  const city = document.getElementById('city-select').value;
  const data = await Api.get(`/api/forecast/parkhaus/${city}/${encodeURIComponent(plsId)}`, { hours: 24 });
  const house = current?.houses.find(h => h.pls_id === plsId);
  document.getElementById('detail-title').textContent =
    `${house?.name || plsId} – Ist-Verlauf (24 h) und Prognose`;

  const actual = data.actual.map(a => ({ x: a.ts, y: a.free }));
  const datasets = [{
    label: 'Ist (frei)', data: actual, borderColor: '#0d6efd',
    pointRadius: 0, borderWidth: 2, tension: 0.2,
  }];
  const colors = { ml: '#198754', baseline: '#fd7e14' };
  for (const [mt, horizons] of Object.entries(data.forecasts)) {
    const points = Object.values(horizons).flat()
      .map(p => ({ x: p.ts, y: p.free }))
      .sort((a, b) => a.x.localeCompare(b.x));
    datasets.push({
      label: mt === 'ml' ? 'Prognose KI' : 'Prognose Basis',
      data: points, borderColor: colors[mt] || '#888', showLine: false,
      pointRadius: 3, borderDash: mt === 'baseline' ? [5, 4] : [],
    });
  }
  if (detailChart) detailChart.destroy();
  detailChart = new Chart(document.getElementById('detail-chart'), {
    type: 'line',
    data: { datasets },
    options: {
      scales: {
        x: { type: 'time', time: { unit: 'hour' }, ticks: { maxTicksLimit: 12 } },
        y: { beginAtZero: true, title: { display: true, text: 'freie Plätze' } },
      },
      plugins: { legend: { position: 'bottom' } },
    },
  });

  const wx = data.weather.filter(w => new Date(w.ts) >= new Date(Date.now() - 3600e3)).slice(0, 8);
  document.getElementById('detail-weather').innerHTML =
    '<strong class="small">Wetter (nächste Stunden)</strong><br>' +
    (wx.length ? wx.map(w =>
      `<span class="me-3 small">${fmtTs(w.ts)} ${w.precipitation > 0.5 ? '🌧️' : '☀️'} ${Math.round(w.temperature)}°</span>`
    ).join('') : '<span class="small text-muted">keine Daten</span>');

  document.getElementById('detail-events').innerHTML =
    '<strong class="small">Events heute/morgen</strong><br>' +
    (data.events.length ? data.events.map(e =>
      `<div class="small">${e.affects_this ? '⚠️ ' : ''}${e.title} – ${e.venue} (${fmtTs(e.start)}–${fmtTs(e.end)})</div>`
    ).join('') : '<span class="small text-muted">keine Veranstaltungen erfasst</span>');
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadCities();
  await loadForecasts();
  document.querySelectorAll('input[name="model"]').forEach(r =>
    r.addEventListener('change', loadForecasts));
  setInterval(loadForecasts, 5 * 60 * 1000);
});
