import {$, esc, label, tintClass, tintStyle} from '../core/dom.js';
import {api} from '../core/api.js';
import {memory} from '../core/memory.js';
import {state, view} from '../core/store.js';
import {showToast} from '../ui/toast.js';

export function renderCategoryTabs() {
  const status = state.status;
  $('categoryTabs').innerHTML = Object.keys(state.categories).map(k => `
      <button class="tab ${tintClass(state.categoryColors, k)} ${k === state.selectedCategory ? 'active' : ''}" ${tintStyle(state.categoryColors, k)} role="tab" aria-selected="${k === state.selectedCategory}" data-action="select" data-cat="${esc(k)}">${k === status.current_category && status.current_track ? '<span class="eq tab-eq" aria-label="Playing from this category"><i></i><i></i><i></i></span>' : ''}${esc(label(k))} <span class="chip-count">${state.categories[k].length}</span></button>
    `).join('');
}

// Enables the "Add tracks" button only when there is a playlist to add to.
export function updateAddForm() {
  const hasPlaylist = Object.keys(state.categories).length > 0;
  $('btnAddTrack').disabled = !hasPlaylist;
}

export async function loadCategories() {
  const [data, colors] = await Promise.all([api('GET', '/categories'), api('GET', '/categories/colors')]);
  if (!data) return;
  state.categories = data;
  if (colors && typeof colors === 'object') state.categoryColors = colors;
  if (state.selectedCategory && !state.categories[state.selectedCategory]) state.selectedCategory = null;
  renderCategoryTabs();
  view.tracks();
}

export function selectCategory(cat) {
  state.selectedCategory = cat;
  state.picked = new Set();
  memory.set('category', cat);
  renderCategoryTabs();
  view.tracks();
}

// Jumps to the category that is playing (switching if needed) and scrolls to its track.
export function showPlaying() {
  const status = state.status;
  const cat = status.current_category;
  if (!cat || !status.current_track) return;
  if (state.selectedCategory !== cat) selectCategory(cat);
  state.scrolledTo = null;
  document.querySelector('#trackList .track-item.playing')?.scrollIntoView({block: 'center', behavior: 'smooth'});
}

export async function deleteCategory(name) {
  const count = state.categories[name]?.length ?? 0;
  if (!confirm(`Delete category "${label(name)}" with ${count} track(s)?`)) return;
  const r = await api('DELETE', '/categories/' + encodeURIComponent(name));
  if (r?.ok) {
    showToast('Category deleted');
    if (state.selectedCategory === name) {
      state.selectedCategory = null;
      memory.set('category', null);
    }
    await loadCategories();
  }
}
