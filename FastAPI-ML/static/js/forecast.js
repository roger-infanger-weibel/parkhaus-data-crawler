let current = null;
let detailChart = null;
let selectedPls = null;

function persona() {
  return document.querySelector('input[name="persona"]:checked')?.value || 'detail';
}

function syncPersonaRadios(mode) {
  document.querySelectorAll('input[name="persona"]').forEach(r => {
    r.checked = (r.value === mode);
  });
}

function applyPersona(mode) {
  document.body.className = `mode-${mode}`;
  syncPersonaRadios(mode);
  document.getElementById('view-simple').classList.toggle('d-none', mode !== 'simple');
  document.getElementById('view-map').classList.toggle('d-none', mode !== 'map');
  document.getElementById('view-detail').classList.toggle('d-none', mode !== 'detail');
  document.getElementById('view-expert').classList.toggle('d-none', mode !== 'expert');
  if (mode === 'simple' || mode === 'map') {
    const suche = document.getElementById('such-feld');
    if (suche && suche.value) { suche.value = ''; Merker.schreiben('suche', ''); }
  }
  if (mode === 'simple' && current) zeichneAmpeln();
  if (mode === 'map' && current) zeichneKarte();
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

function ampelCell(free, total, tooltip) {
  if (free == null) return '<td class="text-end text-muted">–</td>';
  const pct = total ? Math.round((1 - free / total) * 100) : '?';
  const cls = freeBadgeClass(free, total);
  const icon = ampelIcon(free, total);
  return `<td class="text-end" title="${tooltip}">` +
    `<span class="badge ${cls}">${icon} ${pct}%</span>` +
    `<br><span class="cell-detail">${free}/${total}</span></td>`;
}

function horizonCell(house, h) {
  const entry = house.horizons?.[h]?.[model()];
  if (!entry) return '<td class="text-end text-muted">–</td>';
  return ampelCell(entry.free, house.total, `Prognose ${fmtTs(entry.target_time)} Uhr: ${entry.free} frei von ${house.total}`);
}

function historyCell(house, offset) {
  const entry = house.history?.[offset];
  if (!entry) return '<td class="text-end text-muted">–</td>';
  return ampelCell(entry.free, house.total, `vor ${offset} h: ${entry.free} frei (${fmtTs(entry.ts)})`);
}

function expertRow(h, _showGroup) {
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
    <td class="text-end"><strong>${h.total ? Math.round((1 - h.free_now / h.total) * 100) : '?'}%</strong><br><span class="cell-detail">${h.free_now}/${h.total}</span></td>
    ${[1, 2, 4, 8].map(hz => horizonCell(h, hz)).join('')}
  </tr>`;
}

function detailRow(h, showGroup) {
  const name = h.name.replace(/^[^:]+:\s*/, '');
  const links = [];
  if (h.url) links.push(`<a href="${h.url}" target="_blank" onclick="event.stopPropagation()" class="text-muted" title="Webseite">🔗</a>`);
  if (h.lat && h.lon) links.push(`<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" onclick="event.stopPropagation()" class="text-muted" title="Route">📍</a>`);
  const linkStr = links.length ? ' ' + links.join(' ') : '';
  const groupRow = showGroup && h.group
    ? `<tr class="table-light"><td colspan="8"><strong class="small text-muted">${h.group}</strong></td></tr>` : '';
  return groupRow + `
  <tr data-pls="${h.pls_id}">
    <td>${name}${linkStr}</td>
    ${historyCell(h, 2)}
    ${historyCell(h, 1)}
    ${ampelCell(h.free_now, h.total, `Jetzt: ${h.free_now} frei von ${h.total}`)}
    ${[1, 2, 4, 8].map(hz => horizonCell(h, hz)).join('')}
  </tr>`;
}

function fillTable(tbodyId, rowFn) {
  if (!current) return;
  const gefiltert = suchFilter(current.houses)
    .slice().sort((a, b) => (a.group || '').localeCompare(b.group || ''));
  let lastGroup = null;
  const rows = gefiltert.map(h => {
    const showGroup = h.group !== lastGroup;
    lastGroup = h.group;
    return rowFn(h, showGroup);
  }).join('');
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const cols = tbody.closest('table')?.querySelectorAll('thead th').length || 10;
  tbody.innerHTML = rows ||
    `<tr><td colspan="${cols}" class="text-muted">Kein Parkhaus passt zur Suche</td></tr>`;
  tbody.querySelectorAll('tr[data-pls]').forEach(tr => {
    tr.addEventListener('click', () => loadDetail(tr.dataset.pls));
  });
}

function fillTimeRow(rowId) {
  const row = document.getElementById(rowId);
  if (!row || !current?.slot) return;
  const fetch = current.houses?.[0]?.fetch_ts ? new Date(current.houses[0].fetch_ts) : new Date();
  const slot = new Date(current.slot);
  const fmt = d => d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
  const cols = [
    { label: fmt(new Date(fetch.getTime() - 2 * 3600000)), cls: 'text-secondary' },
    { label: fmt(new Date(fetch.getTime() - 1 * 3600000)), cls: 'text-secondary' },
    { label: fmt(fetch), cls: '' },
    { label: fmt(new Date(slot.getTime() + 1 * 3600000)), cls: '' },
    { label: fmt(new Date(slot.getTime() + 2 * 3600000)), cls: '' },
    { label: fmt(new Date(slot.getTime() + 4 * 3600000)), cls: '' },
    { label: fmt(new Date(slot.getTime() + 8 * 3600000)), cls: '' },
  ];
  const thead = row.closest('thead');
  let catRow = thead.querySelector('.time-cat-row');
  if (!catRow) {
    catRow = document.createElement('tr');
    catRow.className = 'time-cat-row';
    thead.insertBefore(catRow, thead.firstChild);
  }
  catRow.innerHTML = `<th></th>` +
    `<th colspan="3" class="text-center small text-muted">Ist-Daten</th>` +
    `<th colspan="4" class="text-center small text-primary">Prognose</th>`;
  row.innerHTML = `<th>Parkhaus</th>` + cols.map((c, i) =>
    `<th class="text-end ${i >= 3 ? 'text-primary' : c.cls}">${c.label}</th>`).join('');
}

/** Tabellen aus den zuletzt geladenen Daten aufbauen, gefiltert nach Suche. */
function zeichneTabelle() {
  if (!current) return;
  fillTimeRow('detail-time-row');
  fillTimeRow('expert-time-row');
  fillTable('detail-table', detailRow);
  fillTable('expert-table', expertRow);
  const gefiltert = suchFilter(current.houses);
  const treffer = document.getElementById('such-treffer');
  if (treffer) {
    treffer.textContent = gefiltert.length < current.houses.length
      ? `${gefiltert.length} von ${current.houses.length}` : '';
  }
}

function showLoading(on) {
  let el = document.getElementById('loading-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'loading-overlay';
    el.innerHTML = '<div class="loading-spinner"></div><div class="loading-text">Daten werden geladen…</div>';
    document.body.appendChild(el);
  }
  el.classList.toggle('active', on);
}

async function loadForecasts() {
  showLoading(true);
  const city = document.getElementById('city-select').value;
  try {
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
    if (ageMin > 35) {
      info.className = 'col-auto ms-auto text-danger small fw-semibold';
      info.textContent = `⚠️ Prognose veraltet: Stand ${fmtTs(data.slot)} Uhr (${ageMin} Min alt)`;
    } else {
      info.className = 'col-auto ms-auto text-muted small';
      info.textContent = `Prognosestand: ${fmtTs(data.slot)} Uhr`;
    }
  }
  zeichneTabelle();
  if (persona() === 'simple') zeichneAmpeln();
  if (persona() === 'map') zeichneKarte();
  if (selectedPls) loadDetail(selectedPls);
  } finally { showLoading(false); }
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
  if (ratio > 0.1 && free > 15) return 'ampel-green';
  if (ratio > 0.05 && free > 15) return 'ampel-yellow';
  return 'ampel-red';
}

function ampelIcon(free, total) {
  if (!total) return '?';
  const ratio = free / total;
  if (ratio > 0.1 && free > 15) return '✓';
  if (ratio > 0.05 && free > 15) return '⚠';
  return '✗';
}

const DATENQUELLEN = {
  luzern:   { label: 'PLS Luzern',   url: 'https://www.pls-luzern.ch/' },
  basel:    { label: 'Parkleitsystem Basel', url: 'https://www.parkleitsystem-basel.ch/' },
  stgallen: { label: 'PLS St. Gallen', url: 'https://www.pls-sg.ch/' },
  zurich:   { label: 'PLS Zürich',   url: 'https://www.pls-zh.ch/' },
  bern:     { label: 'Parking Bern', url: 'https://www.parking-bern.ch/' },
};



function ampelSub(house) {
  const free = house.free_now;
  const total = house.total;
  if (!total) return 'Keine Daten';
  const pct = Math.max(0, Math.round((1 - free / total) * 100));
  const jetztStatus = ampelKlasse(free, total);
  const m = model();

  let warnZeit = null;
  let warnTyp = null;
  for (const hz of [1, 2, 4, 8]) {
    const entry = house.horizons?.[hz]?.[m];
    if (!entry) continue;
    const status = ampelKlasse(entry.free, total);
    if (!warnTyp && status === 'ampel-yellow' && jetztStatus === 'ampel-green') {
      warnZeit = fmtTs(entry.target_time);
      warnTyp = 'knapp';
    }
    if (status === 'ampel-red' && jetztStatus !== 'ampel-red') {
      warnZeit = fmtTs(entry.target_time);
      warnTyp = 'voll';
      break;
    }
  }

  if (jetztStatus === 'ampel-red') {
    return `<div class="ampel-sub">${pct}% belegt · ${total} Plätze</div>`;
  }
  if (jetztStatus === 'ampel-yellow') {
    if (warnTyp === 'voll') {
      return `<div class="ampel-sub">${pct}% belegt · voll ab ~${warnZeit}</div>`;
    }
    return `<div class="ampel-sub">${pct}% belegt · ${total} Plätze</div>`;
  }
  if (warnTyp === 'voll') {
    return `<div class="ampel-sub">${pct}% belegt · <strong>voll ab ~${warnZeit}</strong></div>`;
  }
  if (warnTyp === 'knapp') {
    return `<div class="ampel-sub">${pct}% belegt · wird knapp ab ~${warnZeit}</div>`;
  }
  return `<div class="ampel-sub">${pct}% belegt · ${total} Plätze</div>`;
}

function zeichneAmpeln() {
  if (!current) return;
  let houses = suchFilter(current.houses);
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
  const slot = current.slot ? new Date(current.slot) : new Date();
  const bis8h = new Date(slot.getTime() + 8 * 3600000)
    .toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
  const m8 = model();
  const garantiertSet = new Set();
  current.houses.forEach(h => {
    if (!h.total || ampelKlasse(h.free_now, h.total) !== 'ampel-green') return;
    for (const hz of [1, 2, 4, 8]) {
      const e = h.horizons?.[hz]?.[m8];
      if (!e || ampelKlasse(e.free, h.total) !== 'ampel-green') return;
    }
    garantiertSet.add(h.pls_id);
  });

  let html = '';
  if (quelle) {
    html += `<div class="col-12"><small class="text-muted">Datenquelle: <a href="${quelle.url}" target="_blank">${quelle.label}</a></small></div>`;
  }
  for (const [gruppe, mitglieder] of Object.entries(gruppen)) {
    html += `<div class="col-12"><h6 class="text-muted mt-2 mb-1">${gruppe}</h6></div>`;
    html += mitglieder.map(h => {
      const isSafe = garantiertSet.has(h.pls_id);
      const links = [];
      if (h.url) links.push(`<a href="${h.url}" target="_blank" class="ampel-link" title="Parkhaus-Webseite" onclick="event.stopPropagation()">🔗</a>`);
      if (h.lat && h.lon) links.push(`<a href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}" target="_blank" class="ampel-link" title="Route planen" onclick="event.stopPropagation()">📍</a>`);
      const linkHtml = links.length ? ' ' + links.join(' ') : '';
      const curClass = ampelKlasse(h.free_now, h.total);
      const effClass = (curClass === 'ampel-green' && !isSafe) ? 'ampel-yellow' : curClass;
      const icon = effClass === 'ampel-green' ? '👍' : effClass === 'ampel-yellow' ? '⚠' : '👎';
      let warnSub = '';
      if (!isSafe && curClass === 'ampel-green') {
        for (const hz of [1, 2, 4, 8]) {
          const e = h.horizons?.[hz]?.[m8];
          if (!e) continue;
          const st = ampelKlasse(e.free, h.total);
          if (st === 'ampel-red') { warnSub = `<div class="ampel-sub">⚠ voll ab ~${fmtTs(e.target_time)}</div>`; break; }
          if (st === 'ampel-yellow') { warnSub = `<div class="ampel-sub">⚠ knapp ab ~${fmtTs(e.target_time)}</div>`; break; }
        }
      }
      return `
      <div class="col-6 col-md-4 col-lg-3">
        <div class="ampel-card ${effClass}" data-pls="${h.pls_id}">
          <div class="d-flex justify-content-between align-items-start">
            <div class="ampel-name">${icon} ${h.name.replace(/^[^:]+:\s*/, '')}${linkHtml}</div>
            ${h.price_category ? `<span class="ampel-price">${h.price_category}</span>` : ''}
          </div>
          ${warnSub}
        </div>
      </div>`;
    }).join('');
  }
  grid.innerHTML = html;

  grid.querySelectorAll('.ampel-card').forEach(card => {
    card.addEventListener('click', () => {
      const plsId = card.dataset.pls;
      const house = current?.houses.find(h => h.pls_id === plsId);
      const radio = document.getElementById('persona-expert');
      radio.checked = true;
      applyPersona('expert');
      Merker.schreiben('persona', 'expert');
      const suche = document.getElementById('such-feld');
      if (suche && house) {
        suche.value = house.name.replace(/^[^:]+:\s*/, '');
        Merker.schreiben('suche', suche.value);
        zeichneTabelle();
      }
      loadDetail(plsId);
    });
  });
}


// ===== Karten-Modus: Leaflet-Karte =====
let parkingMap = null;
let mapMarkers = [];

const CITY_CENTER = {
  basel: [47.5596, 7.5886], bern: [46.9480, 7.4474], luzern: [47.0502, 8.3093],
  stgallen: [47.4245, 9.3767], zurich: [47.3769, 8.5417],
};

function markerColor(free, total) {
  if (!total) return '#6c757d';
  const ratio = free / total;
  if (ratio > 0.1 && free > 15) return '#198754';
  if (ratio > 0.05 && free > 15) return '#fd7e14';
  return '#dc3545';
}

function zeichneKarte() {
  if (!current) return;
  const city = document.getElementById('city-select').value;
  const center = CITY_CENTER[city] || [47.37, 8.54];
  const m = model();

  if (!parkingMap) {
    parkingMap = L.map('parking-map').setView(center, 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 18,
    }).addTo(parkingMap);
  } else {
    parkingMap.setView(center, 14);
  }

  mapMarkers.forEach(mk => parkingMap.removeLayer(mk));
  mapMarkers = [];

  const m8 = model();
  const safeSet = new Set();
  current.houses.forEach(h => {
    if (!h.total || ampelKlasse(h.free_now, h.total) !== 'ampel-green') return;
    for (const hzz of [1, 2, 4, 8]) {
      const e = h.horizons?.[hzz]?.[m8];
      if (!e || ampelKlasse(e.free, h.total) !== 'ampel-green') return;
    }
    safeSet.add(h.pls_id);
  });

  const houses = suchFilter(current.houses);
  houses.forEach(h => {
    if (!h.lat || !h.lon) return;
    const free = h.free_now;
    const pct = h.total ? Math.round((1 - free / h.total) * 100) : '?';
    const isSafe = safeSet.has(h.pls_id);
    const currentClass = ampelKlasse(free, h.total);
    const effectiveClass = (currentClass === 'ampel-green' && !isSafe) ? 'ampel-yellow' : currentClass;
    const color = effectiveClass === 'ampel-green' ? '#198754'
                : effectiveClass === 'ampel-yellow' ? '#fd7e14' : '#dc3545';
    const ai = effectiveClass === 'ampel-green' ? '👍' : effectiveClass === 'ampel-yellow' ? '⚠' : '👎';
    const price = h.price_category || '';
    const badge = price ? `<div style="text-align:center;font-size:.6rem;font-weight:700;white-space:nowrap;margin-top:-2px">${price}</div>` : '';
    const icon = L.divIcon({
      className: 'map-marker',
      html: `<div style="background:${color};color:#fff;border-radius:50%;width:42px;height:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:700;font-size:.7rem;line-height:1.1;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)">${ai}<span>${pct}%</span></div>${badge}`,
      iconSize: [42, 52],
      iconAnchor: [21, 26],
    });
    const marker = L.marker([h.lat, h.lon], { icon }).addTo(parkingMap);
    const name = h.name.replace(/^[^:]+:\s*/, '');
    const priceInfo = price ? `<br>Preis: ${price}` : '';
    let warnInfo = '';
    if (!isSafe && currentClass === 'ampel-green') {
      for (const hzz of [1, 2, 4, 8]) {
        const e = h.horizons?.[hzz]?.[m8];
        if (!e) continue;
        const st = ampelKlasse(e.free, h.total);
        if (st === 'ampel-red') { warnInfo = `<br>⚠ voll ab ~${fmtTs(e.target_time)}`; break; }
        if (st === 'ampel-yellow') { warnInfo = `<br>⚠ knapp ab ~${fmtTs(e.target_time)}`; break; }
      }
    }
    marker.bindPopup(`<strong>${name}</strong><br>${free} frei / ${h.total}<br>${pct}% belegt${priceInfo}${warnInfo}`);
    mapMarkers.push(marker);
  });

  setTimeout(() => parkingMap.invalidateSize(), 100);
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
  applyPersona(gemerktePersona);

  document.querySelectorAll('input[name="persona"]').forEach(r =>
    r.addEventListener('change', () => {
      const mode = persona();
      Merker.schreiben('persona', mode);
      applyPersona(mode);
    }));

  document.getElementById('map-horizon')?.addEventListener('change', () => zeichneKarte());

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

  const cities = await Api.get('/api/cities');
  const sel = document.getElementById('city-select');
  sel.innerHTML = cities.map(c => `<option value="${c.id}">${c.name}</option>`).join('');

  // Willkommens-Dialog beim allerersten Besuch
  if (!localStorage.getItem('ai_onboarded')) {
    const wcSel = document.getElementById('welcome-city');
    wcSel.innerHTML = sel.innerHTML;
    let gewaehltePersona = 'detail';
    document.querySelectorAll('.welcome-persona').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.welcome-persona').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        gewaehltePersona = btn.dataset.value;
      });
    });
    const modal = new bootstrap.Modal(document.getElementById('welcome-modal'));
    modal.show();
    await new Promise(resolve => {
      document.getElementById('welcome-ok').addEventListener('click', () => {
        Merker.schreiben('persona', gewaehltePersona);
        Merker.schreiben('city-select', wcSel.value);
        localStorage.setItem('ai_onboarded', '1');
        applyPersona(gewaehltePersona);
        sel.value = wcSel.value;
        modal.hide();
        resolve();
      });
    });
  }

  Merker.binden('city-select', cities[0]?.id, () => {
    selectedPls = null;
    loadForecasts();
  });

  await loadForecasts();
  document.querySelectorAll('input[name="model"]').forEach(r =>
    r.addEventListener('change', () => {
      Merker.schreiben('model', model());
      loadForecasts();
    }));
  setInterval(loadForecasts, 5 * 60 * 1000);
});
