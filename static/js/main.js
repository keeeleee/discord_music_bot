// Entry point: wires the modules together, loads the first data and starts the timers.
import {$} from './core/dom.js';
import {memory} from './core/memory.js';
import {state, view} from './core/store.js';
import {applyOptions, applyTheme, renderOptions} from './ui/themes.js';
import {setDeckMode, setTrackMode, setupDropzone} from './ui/dialogs.js';
import {loadGuilds, selectServerAndChannel} from './voice/voice.js';
import {
  PROGRESS_INTERVAL, STATUS_INTERVAL, renderProgress, seekToClick, showSkeletons, updateStatus,
} from './player/status.js';
import {loadCategories, renderCategoryTabs, updateAddForm} from './playlist/categories.js';
import {renderTracks} from './playlist/tracks.js';
import {loadDeck, renderDeck} from './soundboard/deck.js';
import {installEvents} from './actions.js';

// Renderers are registered here, so the data modules never import the UI directly.
Object.assign(view, {
  playlist() { renderCategoryTabs(); renderTracks(); },
  tracks: renderTracks,
  deck: renderDeck,
});

async function init() {
  showSkeletons();
  await loadGuilds();
  await updateStatus();
  if (state.status.connected) await selectServerAndChannel(state.status.guild_id, state.status.channel_id);
  else await selectServerAndChannel(memory.get('guild'), memory.get('channel'));
  state.selectedCategory = memory.get('category');
  state.deckFilter = memory.get('deckGroup') || 'all';
  await loadCategories();
  await loadDeck();
  setInterval(updateStatus, STATUS_INTERVAL);
  setInterval(renderProgress, PROGRESS_INTERVAL);
}

installEvents();
applyTheme(memory.get('theme') || 'default');
applyOptions();
renderOptions();
updateAddForm();
setDeckMode('url');
setTrackMode('url');
setupDropzone();
$('progressBar').addEventListener('click', seekToClick);

await init();
