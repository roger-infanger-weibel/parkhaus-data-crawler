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

// Navbar: env-Select initialisieren (Element mit id="env-select")
document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('env-select');
  if (sel) {
    sel.value = Api.env();
    sel.addEventListener('change', () => { Api.setEnv(sel.value); location.reload(); });
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
