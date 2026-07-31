// crypto.randomUUID gibt es nur in sicheren Kontexten (HTTPS oder localhost).
// Der Server wird ueber http erreicht - ohne Rueckfall bricht das ganze
// Skript hier ab und der Chat reagiert auf gar nichts mehr.
function neueSessionId() {
  if (window.crypto && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (window.crypto && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  }
  return 'sess-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

const sessionId = sessionStorage.getItem('ai_chat_session') ||
  (() => { const id = neueSessionId(); sessionStorage.setItem('ai_chat_session', id); return id; })();

const win = document.getElementById('chat-window');

function bubble(text, who) {
  const div = document.createElement('div');
  div.className = `chat-bubble chat-${who}`;
  div.textContent = text;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return div;
}

function payloadCard(payload) {
  if (!payload) return;
  let html = '';
  if (payload.type === 'best_parking' && payload.recommendations?.length) {
    html = '<table class="table table-sm mb-0"><tr><th>Parkhaus</th><th class="text-end">Prognose frei</th></tr>' +
      payload.recommendations.map(r =>
        `<tr><td>${r.name}</td><td class="text-end"><span class="badge ${freeBadgeClass(r.predicted_free, r.total)}">${r.predicted_free}</span> / ${r.total}</td></tr>`
      ).join('') + '</table>';
  } else if (payload.type === 'current' && payload.houses?.length) {
    html = '<table class="table table-sm mb-0"><tr><th>Parkhaus</th><th class="text-end">Frei</th></tr>' +
      payload.houses.map(h =>
        `<tr><td>${h.name}</td><td class="text-end"><span class="badge ${freeBadgeClass(h.free, h.total)}">${h.free}</span> / ${h.total}</td></tr>`
      ).join('') + '</table>';
  }
  if (html) {
    const div = document.createElement('div');
    div.className = 'chat-bubble chat-bot payload-card p-2';
    div.innerHTML = html;
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
  }
}

async function send(text) {
  bubble(text, 'user');
  const typing = bubble('…', 'bot');
  try {
    const resp = await Api.post('/api/chat', { message: text, session_id: sessionId });
    typing.textContent = resp.reply;
    payloadCard(resp.payload);
  } catch (err) {
    typing.textContent = 'Fehler: ' + err.message;
  }
}

document.getElementById('chat-form').addEventListener('submit', e => {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  send(text);
});

document.querySelectorAll('.chat-chip').forEach(chip =>
  chip.addEventListener('click', () => send(chip.textContent)));

bubble('Hallo! Ich bin der Parkhaus-Assistent. Frag mich nach freien Plätzen, ' +
  'Prognosen, Empfehlungen, Wetter, Events oder der Prognose-Genauigkeit. ' +
  'Tippe eine Frage oder wähle einen Vorschlag.', 'bot');
