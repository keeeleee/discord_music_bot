import {showToast} from '../ui/toast.js';

// Returns the parsed JSON answer, or null when the request fails (a toast says so).
export async function api(method, path, body) {
  const options = {method};
  if (method !== 'GET') {
    // The server requires JSON on every state-changing request (CSRF protection).
    options.headers = {'Content-Type': 'application/json'};
    options.body = JSON.stringify(body ?? {});
  }
  try {
    const res = await fetch('/api' + path, options);
    return await res.json();
  } catch (e) {
    console.error(`API ${method} ${path} failed`, e);
    showToast('Network error: is the bot running?', false);
    return null;
  }
}

// Multipart uploads need the panel header: it is the server's CSRF check for uploads.
export async function uploadTo(path, form) {
  try {
    const res = await fetch('/api' + path, {method: 'POST', headers: {'X-Requested-With': 'panel'}, body: form});
    return await res.json();
  } catch (e) {
    console.error('Upload failed', e);
    showToast('Upload failed: network error', false);
    return null;
  }
}

export function uploadTile(form) {
  return uploadTo('/deck/upload', form);
}
