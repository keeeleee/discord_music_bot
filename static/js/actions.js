// Event wiring. Every button carries a data-action name; one click listener on the document runs it.
import {$} from './core/dom.js';
import {memory} from './core/memory.js';
import {state, view} from './core/store.js';
import {refreshMenus, closeMenuOnOutsideClick, closeMenuOnScroll} from './ui/menus.js';
import {applyTheme, toggleOption, toggleStyle} from './ui/themes.js';
import {setDeckMode, setTrackMode} from './ui/dialogs.js';
import {joinChannel, leaveChannel, loadChannels} from './voice/voice.js';
import {deleteCategory, selectCategory, showPlaying} from './playlist/categories.js';
import {
  addTrack, bulkCopy, bulkRemove, clearPicks, pickAll, togglePick, openAddTrack, playCategory,
  playTrack, removeTrack, saveTrackEdit, renderTracks,
} from './playlist/tracks.js';
import {
  deleteGroup, deckAdd, deckDelete, deckPlay, openAddSound, renderDeck, saveTileEdit, setAddColor, setTileColor,
} from './soundboard/deck.js';
import {simpleCommand, seekBy, toggleLoop, toggleShuffle} from './player/status.js';
import {addItem, openManage, removeItem, saveRow, setColor, togglePicker} from './ui/manage.js';

// Saves whichever inline edit is open (a track or a sound).
async function saveEdit() {
  if (!state.editing) return;
  if (state.editing.kind === 'track') await saveTrackEdit();
  else await saveTileEdit();
}

const actions = {
  'join': () => joinChannel(),
  'leave': () => leaveChannel(),
  'add-track': () => addTrack(),
  'play-category': () => playCategory(),
  'pause': () => simpleCommand('/pause'),
  'resume': () => simpleCommand('/resume'),
  'deck-add': () => deckAdd(),
  'deck-play': el => deckPlay(Number(el.dataset.index)),
  'deck-delete': el => deckDelete(Number(el.dataset.index)),
  'seek-back': () => seekBy(-10),
  'seek-forward': () => seekBy(10),
  'skip': () => simpleCommand('/skip', 'Skipped'),
  'stop': () => simpleCommand('/stop', 'Stopped'),
  'toggle-loop': () => toggleLoop(),
  'toggle-shuffle': () => toggleShuffle(),
  'menu-toggle': el => { state.openMenu = state.openMenu === el.dataset.key ? null : el.dataset.key; refreshMenus(); },
  'edit-track': el => { state.editing = {kind: 'track', cat: el.dataset.cat, index: Number(el.dataset.index)}; state.openMenu = null; refreshMenus(); },
  'edit-tile': el => { state.editing = {kind: 'tile', index: Number(el.dataset.index)}; state.openMenu = null; refreshMenus(); },
  'save-edit': () => saveEdit(),
  'tile-color': el => setTileColor(el.dataset.color || null),
  'cancel-edit': () => { state.editing = null; state.openMenu = null; refreshMenus(); },
  'deck-mode': el => setDeckMode(el.dataset.mode),
  'style-toggle': () => toggleStyle(),
  'theme': el => applyTheme(el.dataset.theme),
  'option-toggle': el => toggleOption(el.dataset.option),
  'add-color': el => setAddColor(el.dataset.color),
  'deck-filter': el => { state.deckFilter = el.dataset.group; memory.set('deckGroup', state.deckFilter); renderDeck(true); },
  'show-playing': () => showPlaying(),
  'open-add-track': () => openAddTrack(),
  'track-mode': el => setTrackMode(el.dataset.mode),
  'close-add-track': () => $('addTrackForm').close(),
  'open-add-sound': () => openAddSound(),
  'close-add-sound': () => $('deckAdd').close(),
  'pick-track': el => togglePick(Number(el.dataset.index)),
  'bulk-all': () => pickAll(),
  'bulk-clear': () => clearPicks(),
  'bulk-copy': el => bulkCopy(el.dataset.cat),
  'delete-group': el => deleteGroup(el.dataset.group),
  'bulk-remove': () => bulkRemove(),
  'select': el => selectCategory(el.dataset.cat),
  'delete-category': el => deleteCategory(el.dataset.cat),
  'play-track': el => playTrack(el.dataset.cat, Number(el.dataset.index)),
  'remove-track': el => removeTrack(el.dataset.cat, Number(el.dataset.index)),
  'open-manage': el => openManage(el.dataset.kind),
  'clear-track-search': () => { $('trackSearch').value = ''; state.trackQuery = ''; view.tracks(); },
  'close-manage': () => $('manageDialog').close(),
  'manage-save': el => saveRow(el),
  'manage-delete': el => removeItem(el.dataset.name),
  'manage-color': el => setColor(el.dataset.name, el.dataset.color),
  'manage-picker': el => togglePicker(el.dataset.name),
  'manage-add': () => addItem(),
};

async function runAction(el) {
  const closesMenu = state.openMenu !== null && el.dataset.action !== 'menu-toggle';
  if (closesMenu) state.openMenu = null;
  const result = actions[el.dataset.action]?.(el);
  if (closesMenu && !(result instanceof Promise)) refreshMenus();
  if (!(result instanceof Promise) || el.tagName !== 'BUTTON') return;
  el.classList.add('busy');
  el.setAttribute('aria-busy', 'true');
  try {
    await result;
  } finally {
    el.classList.remove('busy');
    el.removeAttribute('aria-busy');
  }
}

// Registers all page-level listeners. Call once at start-up; the order matches the original script.
export function installEvents() {
  document.addEventListener('click', e => {
    closeMenuOnOutsideClick(e);
    const el = e.target.closest('[data-action]');
    if (!el) return;
    e.stopPropagation();
    runAction(el);
  });

  document.addEventListener('scroll', () => closeMenuOnScroll(), true);
  $('trackSearch').addEventListener('input', e => { state.trackQuery = e.target.value; renderTracks(); });
  $('deckSearch').addEventListener('input', e => { state.deckQuery = e.target.value; renderDeck(true); });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && (e.target.id === 'trackSearch' || e.target.id === 'deckSearch')) {
      // Escape in a search box clears it.
      e.target.value = '';
      e.target.dispatchEvent(new Event('input'));
      return;
    }
    if (e.key === 'Escape') {
      if (state.openMenu !== null || state.editing !== null) {
        state.openMenu = null;
        state.editing = null;
        refreshMenus();
      }
      return;
    }
    if (e.key === 'Enter') {
      if (e.target.id === 'editTitle' || e.target.id === 'editUrl') { saveEdit(); return; }
      if (e.target.matches('[role="button"][data-action]')) runAction(e.target);
      else if (e.target.id === 'manageNew') addItem();
      else if (e.target.classList.contains('manage-name')) saveRow(e.target);
      else if (e.target.id === 'deckUrl' || e.target.id === 'deckLabel') deckAdd();
      else if (e.target.id === 'trackTitle' || (e.target.id === 'trackUrl' && (e.metaKey || e.ctrlKey))) runAction($('btnAddTrack'));
      return;
    }

    // Playback shortcuts work anywhere except while typing or on a focused control.
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest('input, select, textarea, button, [role="button"]')) return;
    if (e.key === ' ') {
      e.preventDefault();
      simpleCommand(state.status.is_paused ? '/resume' : '/pause');
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      seekBy(-10);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      seekBy(10);
    } else if (e.key === 'n' || e.key === 'N') {
      simpleCommand('/skip', 'Skipped');
    }
  });

  $('guildSelect').addEventListener('change', loadChannels);
  document.addEventListener('click', e => {
    if (!$('stylePanel').hidden && !e.target.closest('#stylePanel, #gearBtn')) toggleStyle(false);
  });
}
