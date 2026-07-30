// Gemeinsamer Fetch-Wrapper inkl. prod/test-Umschalter (localStorage)
const Api = {
  env() { return localStorage.getItem('ai_env') || 'test'; },
  setEnv(env) { localStorage.setItem('ai_env', env); },
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

// Externe Links - hier zentral gepflegt, das Menue steht auf allen Seiten
const EXTERNAL_LINKS = [
  { label: 'Google AI Studio Dashboard', url: 'https://parkhaus-belegungsprognose-1027643494096.europe-west2.run.app/' },
  { label: 'Flask Dashboard', url: 'http://87.106.222.137:80' },
  { label: 'Dokumentation', url: 'https://github.com/roger-infanger-weibel/parkhaus-data-crawler/blob/main/README.md' },
  { label: 'Monitoring', url: 'https://parkhaus-data-crawler.ai.studio/' },
];

document.addEventListener('DOMContentLoaded', () => {
  // env-Select initialisieren (Element mit id="env-select")
  const sel = document.getElementById('env-select');
  if (sel) {
    sel.value = Api.env();
    sel.addEventListener('change', () => { Api.setEnv(sel.value); location.reload(); });
  }
  // Link-Menue fuellen (Element mit id="link-menu")
  const menu = document.getElementById('link-menu');
  if (menu) {
    menu.innerHTML = EXTERNAL_LINKS.map(l =>
      `<li><a class="dropdown-item" href="${l.url}" target="_blank" rel="noopener">${l.label}</a></li>`
    ).join('');
  }
});

function freeBadgeClass(free, total) {
  if (!total) return 'bg-secondary';
  const ratio = free / total;
  if (ratio > 0.3) return 'badge-free-high';
  if (ratio > 0.1) return 'badge-free-mid';
  return 'badge-free-low';
}

function fmtTs(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
}
