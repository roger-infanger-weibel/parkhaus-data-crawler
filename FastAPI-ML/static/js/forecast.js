let current = null;
let detailChart = null;
let selectedPls = null;

function persona() {
  return document.querySelector('input[name="persona"]:checked')?.value || 'detail';
}

function applyPersona(mode) {
  document.body.className = `mode-${mode}`;
  document.getElementById('view-simple').classList.toggle('d-none', mode !== 'simple');
  document.getElementById('view-detail').classList.toggle('d-none', mode === 'simple');
  document.getElementById('view-expert-panels').classList.toggle('d-none', mode !== 'expert');
  if (mode === 'simple' && current) zeichneAmpeln();
  if (current) zeichneTabelle();
  if (mode === 'expert' && selectedPls) updateExpertPanels();
}

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
  const rows = gefiltert.map(h => {
    const extras = [];
    if (h.group) extras.push(h.group);
    if (h.price_category) extras.push(h.price_category);
    const links = [];
    if (h.url) links.push(`<a href="${h.url}" target="_blank" onclick="event.stopPropagation()" class="text-muted" title="Webseite">🔗</a>`);
    if (h.lat && h.lon) links.push(`<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" onclick="event.stopPropagation()" class="text-muted" title="Route">📍</a>`);
    const linkStr = links.length ? ' ' + links.join(' ') : '';
    return `
    <tr data-pls="${h.pls_id}">
      <td>${h.name}${linkStr}${extras.length ? `<br><small class="text-muted">${extras.join(' · ')}</small>` : ''}</td>
      ${historyCell(h, 2)}
      ${historyCell(h, 1)}
      <td class="text-end"><strong>${h.free_now}</strong><small class="text-muted">/${h.total}</small></td>
      ${[1, 2, 4, 8].map(hz => horizonCell(h, hz)).join('')}
      <td><small class="text-muted">${fmtTs(h.fetch_ts)}</small></td>
    </tr>`;
  }).join('');
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
  if (persona() === 'simple') zeichneAmpeln();
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
  if (persona() === 'expert') updateExpertPanels();
}

// ===== Einfach-Modus: Ampel-Kacheln =====
function ampelKlasse(free, total) {
  if (!total) return 'ampel-yellow';
  const ratio = free / total;
  if (ratio > 0.3) return 'ampel-green';
  if (ratio > 0.1) return 'ampel-yellow';
  return 'ampel-red';
}

function ampelIcon(free, total) {
  if (!total) return '?';
  const ratio = free / total;
  if (ratio > 0.3) return '✓';
  if (ratio > 0.1) return '⚠';
  if (free > 0) return '✗';
  return '✗';
}

const DATENQUELLEN = {
  luzern:   { label: 'PLS Luzern',   url: 'https://www.pls-luzern.ch/' },
  basel:    { label: 'Parkleitsystem Basel', url: 'https://www.parkleitsystem-basel.ch/' },
  stgallen: { label: 'PLS St. Gallen', url: 'https://www.pls-sg.ch/' },
  zurich:   { label: 'PLS Zürich',   url: 'https://www.pls-zh.ch/' },
  bern:     { label: 'Parking Bern', url: 'https://www.parking-bern.ch/' },
};


const PARKHAUS_TIPPS = {
  'parkhaus flora': '🚫 Eng & schwierig zum Parkieren',
  'hirzenmatt': '🚫 Sehr eng, schwierig zum Manövrieren',
  'am gütsch': '🚫 Abgelegen, schlechte Zufahrt',
  'city-parking': '🚫 Oft Stau bei Ausfahrt',
};

function parkhausTipp(name) {
  const key = name.toLowerCase();
  for (const [k, v] of Object.entries(PARKHAUS_TIPPS)) {
    if (key.includes(k)) return v;
  }
  return null;
}

function ampelText(free, total) {
  if (!total) return 'Keine Daten';
  const ratio = free / total;
  if (ratio > 0.3) return 'Viele Plätze frei';
  if (ratio > 0.1) return 'Wird knapp';
  if (free > 0) return 'Fast voll';
  return 'Voll';
}

function ampelTrend(house) {
  const m = model();
  const horizonte = [1, 2, 4, 8];
  let letzteZeit = null;
  let zusammenfassung = [];

  for (const hz of horizonte) {
    const entry = house.horizons?.[hz]?.[m];
    if (!entry) continue;
    letzteZeit = fmtTs(entry.target_time);
    const diff = entry.free - house.free_now;
    if (Math.abs(diff) >= 5) {
      zusammenfassung.push({ hz, diff, zeit: fmtTs(entry.target_time), free: entry.free });
    }
  }

  if (!zusammenfassung.length) {
    return letzteZeit
      ? `<span class="ampel-trend">→ stabil bis ${letzteZeit}</span>`
      : '';
  }

  const erste = zusammenfassung[0];
  const letzte = zusammenfassung[zusammenfassung.length - 1];

  if (letzte.diff > 0) {
    return `<span class="ampel-trend">↗ ab ${erste.zeit} freier (${letzte.free} um ${letzte.zeit})</span>`;
  }
  if (letzte.diff < 0) {
    return `<span class="ampel-trend">↘ ab ${erste.zeit} voller (${letzte.free} um ${letzte.zeit})</span>`;
  }
  return `<span class="ampel-trend">→ stabil bis ${letzteZeit}</span>`;
}

function zeichneAmpeln() {
  if (!current) return;
  const hideFull = document.getElementById('simple-show-full')?.checked;
  let houses = suchFilter(current.houses);
  if (hideFull) houses = houses.filter(h => h.total > 0 && (h.free_now / h.total) > 0.1);
  houses.sort((a, b) => (b.free_now / (b.total || 1)) - (a.free_now / (a.total || 1)));

  const grid = document.getElementById('ampel-grid');
  if (!houses.length) {
    grid.innerHTML = '<div class="col-12 text-muted">Keine Parkhäuser mit freien Plätzen</div>';
    return;
  }

  const gruppen = {};
  houses.forEach(h => {
    const g = h.group || 'Weitere';
    (gruppen[g] = gruppen[g] || []).push(h);
  });

  const city = document.getElementById('city-select').value;
  const quelle = DATENQUELLEN[city];
  let html = '';
  if (quelle) {
    html += `<div class="col-12"><small class="text-muted">Datenquelle: <a href="${quelle.url}" target="_blank">${quelle.label}</a></small></div>`;
  }
  for (const [gruppe, mitglieder] of Object.entries(gruppen)) {
    const best = mitglieder.reduce((a, b) =>
      (a.free_now / (a.total || 1)) >= (b.free_now / (b.total || 1)) ? a : b);
    html += `<div class="col-12"><h6 class="text-muted mt-2 mb-1">${gruppe}</h6></div>`;
    html += mitglieder.map(h => {
      const isBest = h.pls_id === best.pls_id && mitglieder.length > 1 && h.free_now > 0;
      const tipp = parkhausTipp(h.name);
      const links = [];
      if (h.url) links.push(`<a href="${h.url}" target="_blank" class="ampel-link" title="Parkhaus-Webseite" onclick="event.stopPropagation()">🔗</a>`);
      if (h.lat && h.lon) links.push(`<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" class="ampel-link" title="Route planen" onclick="event.stopPropagation()">📍</a>`);
      const linkHtml = links.length ? ' ' + links.join(' ') : '';
      const preis = h.price_category ? ` · ${h.price_category}` : '';
      return `
      <div class="col-6 col-md-4 col-lg-3">
        <div class="ampel-card ${ampelKlasse(h.free_now, h.total)}${isBest ? ' ampel-best' : ''}" data-pls="${h.pls_id}">
          <div class="d-flex justify-content-between align-items-start">
            <div class="ampel-name">${isBest ? '⭐ ' : ''}${h.name.replace(/^[^:]+:\s*/, '')}${linkHtml}</div>
            ${h.price_category ? `<span class="ampel-price">${h.price_category}</span>` : ''}
          </div>
          <div>
            <div class="ampel-status"><span class="ampel-icon">${ampelIcon(h.free_now, h.total)}</span> ${h.free_now} <small style="font-size:.55em">frei</small></div>
            <div class="ampel-sub">${ampelText(h.free_now, h.total)} · ${h.total} Plätze</div>
            ${tipp ? `<div class="ampel-tipp">${tipp}</div>` : ''}
            ${ampelTrend(h)}
          </div>
        </div>
      </div>`;
    }).join('');
  }
  grid.innerHTML = html;

  grid.querySelectorAll('.ampel-card').forEach(card => {
    card.addEventListener('click', () => {
      const radio = document.getElementById('persona-detail');
      radio.checked = true;
      applyPersona('detail');
      Merker.schreiben('persona', 'detail');
      loadDetail(card.dataset.pls);
    });
  });
}


// ===== Experten-Modus: Zusatzinfos =====
function updateExpertPanels() {
  if (!current || !selectedPls) return;
  const house = current.houses.find(h => h.pls_id === selectedPls);
  if (!house) return;

  // Konfidenz/Details pro Horizont
  const confEl = document.getElementById('expert-confidence');
  const horizons = house.horizons || {};
  const rows = [1, 2, 4, 8].map(hz => {
    const ml = horizons[hz]?.ml;
    const bl = horizons[hz]?.baseline;
    if (!ml && !bl) return null;
    const src = ml || bl;
    let row = `<tr><td>+${hz}h</td><td>${src.free} frei</td><td>${(src.occ * 100).toFixed(0)}%</td>`;
    row += `<td>${src.free_q20 != null ? src.free_q20 : '–'}</td>`;
    row += `<td>${src.full_prob != null ? (src.full_prob * 100).toFixed(0) + '%' : '–'}</td>`;
    row += `<td class="text-muted">${fmtTs(src.target_time)}</td></tr>`;
    return row;
  }).filter(Boolean);

  if (rows.length) {
    confEl.innerHTML = `
      <table class="table table-sm mb-0">
        <thead><tr>
          <th>Horizont</th><th>Prognose</th><th>Auslastung</th>
          <th title="Pessimistisch (20. Perzentil)">Q20</th>
          <th title="Wahrscheinlichkeit komplett voll">P(voll)</th>
          <th>Zielzeit</th>
        </tr></thead>
        <tbody>${rows.join('')}</tbody>
      </table>`;
  } else {
    confEl.textContent = 'Keine Prognosedaten für dieses Parkhaus';
  }

  // Modellvergleich
  const cmpEl = document.getElementById('expert-model-compare');
  const cmpRows = [1, 2, 4, 8].map(hz => {
    const ml = horizons[hz]?.ml;
    const bl = horizons[hz]?.baseline;
    if (!ml && !bl) return null;
    const diff = (ml && bl) ? ml.free - bl.free : null;
    const diffStr = diff != null ? (diff > 0 ? `+${diff}` : `${diff}`) : '–';
    const diffCls = diff != null ? (diff > 0 ? 'skill-pos' : (diff < 0 ? 'skill-neg' : '')) : '';
    return `<tr>
      <td>+${hz}h</td>
      <td>${ml ? ml.free : '–'}</td>
      <td>${bl ? bl.free : '–'}</td>
      <td class="${diffCls}">${diffStr}</td>
    </tr>`;
  }).filter(Boolean);

  if (cmpRows.length) {
    cmpEl.innerHTML = `
      <table class="table table-sm mb-0">
        <thead><tr><th>Horizont</th><th>KI-Modell</th><th>Basis</th><th>Differenz</th></tr></thead>
        <tbody>${cmpRows.join('')}</tbody>
      </table>
      <p class="text-muted mt-1 mb-0" style="font-size:.75rem">Positiv = KI prognostiziert mehr freie Plätze als Basis</p>`;
  } else {
    cmpEl.textContent = 'Kein Modellvergleich verfügbar';
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Persona wiederherstellen
  const gemerktePersona = Merker.lesen('persona', 'detail');
  const personaRadio = document.getElementById('persona-' + gemerktePersona);
  if (personaRadio) personaRadio.checked = true;
  applyPersona(gemerktePersona);

  document.querySelectorAll('input[name="persona"]').forEach(r =>
    r.addEventListener('change', () => {
      Merker.schreiben('persona', persona());
      applyPersona(persona());
    }));

  document.getElementById('simple-show-full')?.addEventListener('change', () => zeichneAmpeln());

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
      if (persona() === 'simple') zeichneAmpeln();
    });
    document.getElementById('such-loeschen')?.addEventListener('click', () => {
      suche.value = '';
      Merker.schreiben('suche', '');
      zeichneTabelle();
      if (persona() === 'simple') zeichneAmpeln();
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
