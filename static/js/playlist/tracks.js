import {$, esc, label, matchesQuery} from '../core/dom.js';
import {api, uploadTo} from '../core/api.js';
import {state, view} from '../core/store.js';
import {showToast} from '../ui/toast.js';
import {moreMenu} from '../ui/menus.js';
import {PLAY_ICON} from '../ui/icons.js';
import {setTrackMode, showChosenTracks} from '../ui/dialogs.js';
import {updateStatus} from '../player/status.js';
import {loadCategories, updateAddForm} from './categories.js';

// A track is identified by its link, or by its stored file for uploads.
export function trackKey(t) {
  return t ? (t.url ?? t.file ?? null) : null;
}

export function isPlayingTrack(cat, track) {
  return cat === state.status.current_category && trackKey(state.status.current_track) === trackKey(track);
}

function trackEditor(t) {
  return `
      <div class="track-item editing">
        <div class="edit-grid">
          <input type="text" id="editTitle" value="${esc(t.title || '')}" aria-label="Track title" maxlength="200" placeholder="Title" />
          ${t.file ? '' : `<input type="url" id="editUrl" value="${esc(t.url)}" aria-label="YouTube link" placeholder="YouTube link" />`}
        </div>
        <div class="row">
          <button class="btn-primary btn-small" data-action="save-edit">Save</button>
          <button class="btn-ghost btn-small" data-action="cancel-edit">Cancel</button>
          <span class="hint">Empty title keeps the old one · Enter saves · Esc cancels</span>
        </div>
      </div>`;
}

export function renderTracks() {
  const el = $('trackList');
  const {status, categories, picked, editing} = state;
  const selectedCategory = state.selectedCategory;
  $('btnPlayCategory').classList.toggle('invisible', !selectedCategory || !(categories[selectedCategory]?.length));
  // Same two entries as the soundboard menu: add, then manage.
  $('catMenu').innerHTML = moreMenu('cat:menu', [
    {action: 'open-add-track', label: '＋ Add tracks', data: {}},
    {action: 'open-manage', label: '✎ Manage playlists', data: {kind: 'playlist'}},
  ]);
  $('btnShowPlaying').classList.add('invisible');
  updateAddForm();
  if (!selectedCategory) {
    el.innerHTML = state.categories && Object.keys(state.categories).length
      ? '<div class="empty"><span class="icon">🎼</span>Choose a playlist above to see its tracks.</div>'
      : `<div class="empty"><span class="icon">🎼</span>No playlists yet.<div class="empty-actions"><button class="btn-primary btn-small" data-action="open-manage" data-kind="playlist">Create a playlist</button></div></div>`;
    return;
  }
  const tracks = categories[selectedCategory] || [];
  if (!tracks.length) {
    el.innerHTML = `<div class="empty"><span class="icon">🔗</span>No tracks yet in this playlist.<div class="empty-actions"><button class="btn-primary btn-small" data-action="open-add-track">+ Add tracks</button></div></div>`;
    return;
  }
  const cat = selectedCategory;
  const query = state.trackQuery.trim().toLowerCase();
  const rows = tracks.map((t, i) => ({t, i})).filter(({t}) => matchesQuery(query, t.title, t.url));
  if (!rows.length) {
    el.innerHTML = `<div class="empty"><span class="icon">🔎</span>Nothing matches “${esc(state.trackQuery.trim())}” in this playlist.<div class="empty-actions"><button class="btn-ghost btn-small" data-action="clear-track-search">Clear search</button></div></div>`;
    return;
  }
  el.innerHTML = rows.map(({t, i}) => {
    if (editing?.kind === 'track' && editing.cat === cat && editing.index === i) return trackEditor(t);
    const playing = isPlayingTrack(cat, t);
    const name = esc(t.title || t.url);
    const eq = `<span class="eq${status.is_paused ? ' paused' : ''}" aria-label="Playing"><i></i><i></i><i></i></span>`;
    return `
        <div class="track-item ${playing ? 'playing' : ''}">
          <input type="checkbox" class="pick" data-action="pick-track" data-index="${i}" aria-label="Select ${name}" ${picked.has(i) ? 'checked' : ''} />
          <div class="track-num">${playing ? eq : i + 1}</div>
          <div class="track-info">
            <div class="track-name">${name}</div>
            <div class="track-url">${t.url ? esc(t.url) : '📁 Stored file'}</div>
          </div>
          <div class="track-actions">
            <button class="btn-play btn-icon" data-action="play-track" data-cat="${esc(cat)}" data-index="${i}" aria-label="Play ${name}" title="Play now">${PLAY_ICON}</button>
            ${moreMenu(`track:${cat}:${i}`, [
              {action: 'edit-track', label: '✏️ Edit', data: {cat, index: i}},
              {action: 'remove-track', label: '🗑 Remove', danger: true, data: {cat, index: i}},
            ])}
          </div>
        </div>`;
  }).join('');

  // Bulk bar: shows when tracks are selected, with a button per other playlist to copy them into.
  const pickedCount = [...picked].filter(i => i < tracks.length).length;
  $('bulkBar').hidden = pickedCount === 0;
  $('bulkCount').textContent = `${pickedCount} selected`;
  $('bulkTargets').innerHTML = Object.keys(categories).filter(k => k !== cat)
    .map(k => `<button class="tab tab-target" data-action="bulk-copy" data-cat="${esc(k)}">Copy to ${esc(label(k))}</button>`).join('')
    || '<span class="hint">Create another playlist to copy tracks into it.</span>';

  // Keep the track that is playing in view: follow it when the track changes, and offer a button to jump back.
  const playingEl = el.querySelector('.track-item.playing');
  $('btnShowPlaying').classList.toggle('invisible', !status.current_track);
  if (editing?.kind === 'track') {
    $('editTitle')?.focus();
  } else if (playingEl) {
    const key = `${cat}|${trackKey(status.current_track)}`;
    if (key !== state.scrolledTo) {
      state.scrolledTo = key;
      playingEl.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    }
  }
}

export async function saveTrackEdit() {
  const editing = state.editing;
  const body = {title: $('editTitle').value.trim()};
  if ($('editUrl')) body.url = $('editUrl').value.trim();
  const r = await api('PUT', `/categories/${encodeURIComponent(editing.cat)}/tracks/${editing.index}`, body);
  if (!r) return;
  if (!r.ok) { showToast(r.message ?? 'Could not save', false); return; }
  state.editing = null;
  showToast('Track saved');
  await loadCategories();
}

// Track modal: links go to the chosen playlist one by one; files are uploaded one by one.
export async function addTrack() {
  const target = $('addTarget').value;
  if (!target) { showToast('Create a playlist first', false); return; }
  if (state.trackMode === 'file') return addTrackFiles(target);

  const box = $('trackUrl');
  const links = box.value.split('\n').map(line => line.trim()).filter(Boolean);
  const title = $('trackTitle').value.trim();
  if (!links.length) { showToast('Paste a YouTube link first', false); box.focus(); return; }

  const path = '/categories/' + encodeURIComponent(target) + '/tracks';
  const failed = [];
  const errors = [];
  let added = 0;
  for (let i = 0; i < links.length; i++) {
    $('addStatus').textContent = links.length > 1 ? `Reading ${i + 1} of ${links.length} from YouTube…` : 'Reading from YouTube…';
    // A title applies only to a single link; with several links every title comes from YouTube.
    const r = await api('POST', path, {url: links[i], title: links.length === 1 ? title : ''});
    if (r?.ok) {
      added += r.added;
    } else {
      failed.push(links[i]);
      errors.push(r?.message ?? 'network error');
    }
  }
  $('addStatus').textContent = '';

  if (!failed.length) {
    box.value = '';
    $('trackTitle').value = '';
    showToast(added === 1 ? 'Track added' : `${added} tracks added`);
    $('addTrackForm').close();
  } else {
    // Keep the failed links in the box so they can be fixed and sent again.
    box.value = failed.join('\n');
    showToast(`${added} added, ${failed.length} failed: ${errors[0]}`, false);
  }
  await loadCategories();
}

async function addTrackFiles(target) {
  const files = [...$('trackFile').files];
  if (!files.length) { showToast('Choose at least one file', false); $('trackDrop').focus(); return; }
  const title = $('trackTitle').value.trim();
  let ok = 0;
  const errors = [];
  for (let i = 0; i < files.length; i++) {
    $('addStatus').textContent = files.length > 1 ? `Uploading ${i + 1} of ${files.length}…` : 'Uploading…';
    const form = new FormData();
    form.append('file', files[i]);
    form.append('title', files.length === 1 ? title : '');
    const r = await uploadTo('/categories/' + encodeURIComponent(target) + '/upload', form);
    if (r?.ok) ok++; else errors.push(r?.message ?? 'network error');
  }
  $('addStatus').textContent = '';
  if (ok === files.length) {
    $('trackFile').value = '';
    $('trackTitle').value = '';
    showChosenTracks();
    showToast(ok === 1 ? 'Track added' : `${ok} tracks added`);
    $('addTrackForm').close();
  } else {
    showToast(`${ok} added, ${errors.length} failed: ${errors[0]}`, false);
  }
  await loadCategories();
}

// Opens the track modal with the playlist you are looking at already selected.
export function openAddTrack() {
  const sel = $('addTarget');
  sel.innerHTML = Object.keys(state.categories).map(k => `<option value="${esc(k)}">${esc(label(k))} · ${state.categories[k].length}</option>`).join('');
  if (state.selectedCategory && state.categories[state.selectedCategory]) sel.value = state.selectedCategory;
  setTrackMode(state.trackMode);
  const d = $('addTrackForm');
  if (!d.open) d.showModal();
  (state.trackMode === 'file' ? $('trackDrop') : $('trackUrl')).focus();
}

// Copies every selected track into another playlist. A track can therefore sit in several playlists.
export async function bulkCopy(to) {
  const tracks = state.categories[state.selectedCategory] || [];
  const chosen = [...state.picked].sort((a, b) => a - b).map(i => tracks[i]).filter(Boolean);
  let ok = 0;
  for (const t of chosen) {
    const body = t.file ? {file: t.file, title: t.title || ''} : {url: t.url, title: t.title || ''};
    const r = await api('POST', '/categories/' + encodeURIComponent(to) + '/tracks', body);
    if (r?.ok) ok++;
  }
  state.picked = new Set();
  showToast(`Copied ${ok} of ${chosen.length} to ${label(to)}`, ok === chosen.length);
  await loadCategories();
}

// Removes the selected tracks, from the last one up so the remaining indices stay correct.
export async function bulkRemove() {
  const cat = state.selectedCategory;
  const indices = [...state.picked].sort((a, b) => b - a);
  if (!indices.length || !confirm(`Remove ${indices.length} track(s) from this playlist?`)) return;
  for (const i of indices) await api('DELETE', '/categories/' + encodeURIComponent(cat) + '/tracks/' + i);
  state.picked = new Set();
  showToast(`Removed ${indices.length}`);
  await loadCategories();
}

export function togglePick(i) {
  if (state.picked.has(i)) state.picked.delete(i);
  else state.picked.add(i);
  view.tracks();
}

export function pickAll() {
  (state.categories[state.selectedCategory] || []).forEach((_, i) => state.picked.add(i));
  view.tracks();
}

export function clearPicks() {
  state.picked = new Set();
  view.tracks();
}

export async function removeTrack(cat, index) {
  if (!confirm('Remove this track from the playlist?')) return;
  const r = await api('DELETE', '/categories/' + encodeURIComponent(cat) + '/tracks/' + index);
  if (r?.ok) { showToast('Track removed'); await loadCategories(); }
}

export async function playTrack(cat, index) {
  const track = state.categories[cat]?.[index];
  if (!track) { showToast('Track not found', false); return; }
  const r = await api('POST', '/play/track', {category: cat, index});
  if (r) showToast(r.ok ? 'Playing: ' + (track.title || track.url) : r.message, r.ok);
  await updateStatus();
}

export async function playCategory() {
  if (!state.selectedCategory) { showToast('Select a category first', false); return; }
  const r = await api('POST', '/play/category', {category: state.selectedCategory});
  if (r) showToast(r.ok ? 'Playing ' + label(state.selectedCategory) : r.message, r.ok);
  await updateStatus();
}
