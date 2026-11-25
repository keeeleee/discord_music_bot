// Remembers the last server, channel and category; storage can be unavailable (private mode).
export const memory = {
  get(key) {
    try { return localStorage.getItem('dmc.' + key); } catch (e) { console.debug('storage unavailable', e); return null; }
  },
  set(key, value) {
    try {
      if (value) localStorage.setItem('dmc.' + key, value);
      else localStorage.removeItem('dmc.' + key);
    } catch (e) { console.debug('storage unavailable', e); }
  },
};
