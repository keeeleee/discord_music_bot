import {$, esc} from '../core/dom.js';
import {state} from '../core/store.js';

// Sound modal: "url" or "file" pane.
export function setDeckMode(mode) {
  state.deckMode = mode;
  $('deckSource').dataset.mode = mode;
  document.querySelectorAll('#deckSource .seg').forEach(btn => {
    const on = btn.dataset.mode === mode;
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-selected', String(on));
  });
  document.querySelectorAll('#deckAdd [data-pane]').forEach(pane => pane.classList.toggle('on', pane.dataset.pane === mode));
}

// Track modal: "url" or "file" pane.
export function setTrackMode(mode) {
  state.trackMode = mode;
  $('trackSource').dataset.mode = mode;
  document.querySelectorAll('#trackSource .seg').forEach(btn => {
    const on = btn.dataset.mode === mode;
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-selected', String(on));
  });
  document.querySelectorAll('#addTrackForm [data-tpane]').forEach(pane => pane.classList.toggle('on', pane.dataset.tpane === mode));
  $('btnAddTrack').textContent = 'Add tracks';
}

export function showChosenFile() {
  const file = $('deckFile').files[0];
  $('deckDrop').classList.toggle('has-file', Boolean(file));
  $('dropText').innerHTML = file
    ? `${esc(file.name)}<small>${(file.size / 1048576).toFixed(1)} MB · click to choose another</small>`
    : 'Drop an audio file here, or click to choose one<small>mp3, wav, ogg, opus, m4a, flac, webm · up to 15 MB</small>';
}

export function showChosenTracks() {
  const files = [...$('trackFile').files];
  $('trackDrop').classList.toggle('has-file', files.length > 0);
  const size = files.reduce((sum, f) => sum + f.size, 0) / 1048576;
  $('trackDropText').innerHTML = files.length
    ? `${files.length === 1 ? esc(files[0].name) : files.length + ' files chosen'}<small>${size.toFixed(1)} MB · click to change</small>`
    : 'Drop audio files here, or click to choose<small>several files at once · up to 15 MB each</small>';
}

// Drop handling shared by the track and sound modals.
export function wireDrop(zone, input, onChange) {
  input.addEventListener('change', onChange);
  ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, e => {
    e.preventDefault();
    zone.classList.add('drag');
  }));
  ['dragleave', 'dragend'].forEach(type => zone.addEventListener(type, () => zone.classList.remove('drag')));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag');
    const dropped = e.dataTransfer?.files;
    if (!dropped?.length) return;
    const transfer = new DataTransfer();
    (input.multiple ? [...dropped] : [dropped[0]]).forEach(f => transfer.items.add(f));
    input.files = transfer.files;
    onChange();
  });
}

export function setupDropzone() {
  wireDrop($('deckDrop'), $('deckFile'), showChosenFile);
  wireDrop($('trackDrop'), $('trackFile'), showChosenTracks);
}
