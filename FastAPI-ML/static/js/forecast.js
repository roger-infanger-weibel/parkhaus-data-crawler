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
  Merker.binden('city-select', cities[0]?.id, () => {
    selectedPls = null;
    loadForecasts();
  });
}

/** Suchbegriff auf Name und Gruppe anwenden; leer = alles zeigen. */
function suchFilter(haeuser) {
  const begriff = (document.getElementById('such-feld')?.value || '')
    .trim().toLowerCase();
  if (!begriff) return haeuser;
  // Mehrere Wörter: alle müssen irgendwo vorkommen ("bahnhof p3")
  const teile = begriff.split(/\s+/);
  return haeuser.filter(h => {
    const heuhaufen = `${h.name} ${h.group || ''} ${h.pls_id}`.toLowerCase();
    return teile.every(t => heuhaufen.includes(t));
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

/** Tabelle aus den zuletzt geladenen Daten aufbauen, gefiltert nach Suche. */
function zeichneTabelle() {
  if (!current) return;
  const gefiltert = suchFilter(current.houses);
  const rows = gefiltert.map(h => `
    <tr data-pls="${h.pls_id}">
      <td>${h.name}${h.group ? `<br><small class="text-muted">${h.group}</small>` : ''}</td>
      ${historyCell(h, 2)}
      ${historyCell(h, 1)}
      <td class="text-end"><strong>${h.free_now}</strong><small class="text-muted">/${h.total}</small></td>
      ${[1, 2, 4, 8].map(hz => horizonCell(h, hz)).join('')}
      <td><small class="text-muted">${fmtTs(h.fetch_ts)}</small></td>
    </tr>`).join('');
  document.getElementById('forecast-table').innerHTML = rows ||
    '<tr><td colspan="9" class="text-muted">Kein Parkhaus passt zur Suche</td></tr>';
  document.querySelectorAll('#forecast-table tr[data-pls]').forEach(tr => {
    tr.addEventListener('click', () => loadDetail(tr.dataset.pls));
  });
  const treffer = document.getElementById('such-treffer');
  if (treffer) {
    treffer.textContent = gefiltert.length < current.houses.length
      ? `${gefiltert.length} von ${current.houses.length}` : '';
  }
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
  zeichneTabelle();
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

  const evBox = document.getElementById('detail-events');
  if (!data.events.length) {
    evBox.innerHTML = '<strong class="small">Events heute / morgen</strong><br>' +
      '<span class="small text-muted">keine Veranstaltungen erfasst</span>';
  } else {
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    const tom = new Date(now); tom.setDate(tom.getDate() + 1);
    const tomStr = tom.toISOString().slice(0, 10);
    const heute = data.events.filter(e => e.start?.slice(0, 10) === todayStr);
    const morgen = data.events.filter(e => e.start?.slice(0, 10) === tomStr);
    const fmtEv = ev => ev.map(e =>
      `<div class="small">${e.affects_this ? '⚠️ ' : ''}${e.title} – ${e.venue} (${fmtTs(e.start)}–${fmtTs(e.end)})</div>`
    ).join('');
    let html = '';
    if (heute.length) html += `<strong class="small">Events heute (${todayStr.slice(5).replace('-','.')}.):</strong><br>${fmtEv(heute)}`;
    if (morgen.length) html += `${heute.length ? '<br>' : ''}<strong class="small">Events morgen (${tomStr.slice(5).replace('-','.')}.):</strong><br>${fmtEv(morgen)}`;
    if (!html) html = '<strong class="small">Events heute / morgen</strong><br><span class="small text-muted">keine Veranstaltungen erfasst</span>';
    evBox.innerHTML = html;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Modellwahl wiederherstellen (KI oder Basis)
  const gemerktesModell = Merker.lesen('model', 'ml');
  const radio = document.getElementById('model-' + gemerktesModell);
  if (radio) radio.checked = true;

  // Suchbegriff wiederherstellen - ohne Neuladen, nur die Tabelle filtern
  const suche = document.getElementById('such-feld');
  if (suche) {
    suche.value = Merker.lesen('suche', '');
    suche.addEventListener('input', () => {
      Merker.schreiben('suche', suche.value);
      zeichneTabelle();
    });
    document.getElementById('such-loeschen')?.addEventListener('click', () => {
      suche.value = '';
      Merker.schreiben('suche', '');
      zeichneTabelle();
    });
  }

  await loadCities();
  await loadForecasts();
  document.querySelectorAll('input[name="model"]').forEach(r =>
    r.addEventListener('change', () => {
      Merker.schreiben('model', model());
      loadForecasts();
    }));
  setInterval(loadForecasts, 5 * 60 * 1000);
});
