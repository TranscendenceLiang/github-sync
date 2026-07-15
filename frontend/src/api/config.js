const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  return r.json();
}

async function apiPost(path, data) {
  const r = await fetch(path, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data) });
  const result = await r.json();
  if (!r.ok || result.ok === false) throw new Error(result.error || 'Unknown error');
  return result;
}

export const getConfig = () => apiGet('/api/config');
export const saveConfig = (payload) => apiPost('/api/config', payload);
export const validateConfig = (payload) => apiPost('/api/validate', payload);
export const healthCheck = () => apiGet('/api/health');
