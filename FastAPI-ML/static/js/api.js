// Gemeinsamer Fetch-Wrapper, Umgebungswahl, gemerkte Auswahl, Fusszeile

const Api = {
  // PROD ist der Normalfall. Test nur, wenn ausdruecklich umgeschaltet wurde.
  env() { return localStorage.getItem('ai_env') === 'test' ? 'test' : 'prod'; },
  setEnv(env) {
    if (env === 'test') localStorage.setItem('ai_env', 'test');
    else localStorage.removeItem('ai_env');
  },
  async get(path, params = {}) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('env', this.env());
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, v);
    }
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
    return resp.json();
  },
  async post(path, body) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set('env', this.env());
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
    return resp.json();
  },
};

// Zuletzt gewaehlte Einstellungen merken (Stadt, Modell, Zeitraum, Horizont).
// Bewusst localStorage statt Cookie: bleibt im Browser und wird nie an den
// Server geschickt.
const Merker = {
  lesen(name, standard) { return localStorage.getItem('ai_' + name) || standard; },
  schreiben(name, wert) {
    if (wert === null || wert === undefined || wert === '') localStorage.removeItem('ai_' + name);
    else localStorage.setItem('ai_' + name, wert);
    hinweisSpeicherung();
  },
  /** Select-Element an den Merker binden: Wert setzen und Aenderungen sichern. */
  binden(id, standard, beiAenderung) {
    const el = document.getElementById(id);
    if (!el) return null;
    const gemerkt = this.lesen(id, standard);
    if (gemerkt && [...el.options].some(o => o.value === gemerkt)) el.value = gemerkt;
    el.addEventListener('change', () => {
      this.schreiben(id, el.value);
      if (beiAenderung) beiAenderung(el.value);
    });
    return el.value;
  },
};

// Einmaliger Hinweis, dass Einstellungen lokal gespeichert werden
function hinweisSpeicherung() {
  if (localStorage.getItem('ai_hinweis_gesehen')) return;
  if (document.getElementById('speicher-hinweis')) return;
  const box = document.createElement('div');
  box.id = 'speicher-hinweis';
  box.className = 'alert alert-secondary alert-dismissible position-fixed shadow';
  box.style.cssText = 'bottom:1rem; right:1rem; max-width:26rem; z-index:1080;';
  box.innerHTML =
    '<strong>Hinweis:</strong> Deine Auswahl (Stadt, Modell, Zeitraum) wird ' +
    'lokal in deinem Browser gespeichert, damit sie beim nächsten Besuch ' +
    'erhalten bleibt. Es werden keine Daten an Dritte übermittelt.' +
    '<button type="button" class="btn-close" aria-label="Verstanden"></button>';
  document.body.appendChild(box);
  box.querySelector('.btn-close').addEventListener('click', () => {
    localStorage.setItem('ai_hinweis_gesehen', '1');
    box.remove();
  });
}

// Externe Links - hier zentral gepflegt, das Menue steht auf allen Seiten
const EXTERNAL_LINKS = [
  { label: 'Google AI Studio Dashboard', url: 'https://parkhaus-belegungsprognose-1027643494096.europe-west2.run.app/' },
  { label: 'Flask Dashboard', url: 'http://87.106.222.137:80' },
  { label: 'Dokumentation', url: 'https://github.com/roger-infanger-weibel/parkhaus-data-crawler/blob/main/README.md' },
  { label: 'Monitoring', url: 'https://parkhaus-data-crawler.ai.studio/' },
];

async function fusszeileFuellen() {
  const el = document.getElementById('app-footer');
  if (!el) return;
  try {
    const v = await Api.get('/api/version');
    const umgebung = Api.env() === 'test'
      ? ' | <span class="text-danger fw-semibold">TEST-Umgebung</span>' : '';
    el.innerHTML = `© ${new Date().getFullYear()} ${v.titel} | Version: ${v.version} ` +
      `| Contact: <a href="mailto:${v.kontakt}">${v.kontakt}</a>${umgebung}`;
  } catch {
    el.textContent = 'Swiss Parking Monitor';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // Umgebungswahl ist normalerweise unsichtbar - PROD ist der Normalfall.
  // Sichtbar wird sie mit ?admin am Ende der Adresse; die Freischaltung
  // bleibt danach gemerkt. Ausschalten: ?admin=0
  const params = new URLSearchParams(window.location.search);
  if (params.has('admin')) {
    if (params.get('admin') === '0') {
      localStorage.removeItem('ai_admin');
      Api.setEnv('prod');
    } else {
      localStorage.setItem('ai_admin', '1');
    }
  }
  const adminModus = localStorage.getItem('ai_admin') === '1';

  const sel = document.getElementById('env-select');
  if (sel) {
    const box = sel.closest('.env-box') || sel;
    if (adminModus) {
      box.classList.remove('d-none');
      sel.value = Api.env();
      sel.addEventListener('change', () => { Api.setEnv(sel.value); location.reload(); });
    } else {
      box.classList.add('d-none');
    }
  }

  const menu = document.getElementById('link-menu');
  if (menu) {
    menu.innerHTML = EXTERNAL_LINKS.map(l =>
      `<li><a class="dropdown-item" href="${l.url}" target="_blank" rel="noopener">${l.label}</a></li>`
    ).join('');
  }

  fusszeileFuellen();
});

function freeBadgeClass(free, total) {
  if (!total) return 'bg-secondary';
  const ratio = free / total;
  if (ratio > 0.1 && free > 15) return 'badge-free-high';
  if (ratio > 0.05 && free > 15) return 'badge-free-mid';
  return 'badge-free-low';
}

function fmtTs(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
}
