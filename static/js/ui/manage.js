// "Manage" dialog for playlists and soundboard groups: rename, colour, delete, and add new ones.
// One component serves both; `kind` picks the data and the endpoints.
import {$, colorOf, esc} from '../core/dom.js';
import {api} from '../core/api.js';
import {memory} from '../core/memory.js';
import {state} from '../core/store.js';
import {showToast} from '../ui/toast.js';
import {SWATCHES} from './themes.js';
import {deleteCategory, loadCategories} from '../playlist/categories.js';
import {deckGroups, deleteGroup, loadDeck} from '../soundboard/deck.js';

const KINDS = {
  playlist: {
    title: 'Manage playlists',
    hint: 'Rename, colour or delete a playlist. Its tracks stay with it.',
    placeholder: 'New playlist, e.g. tavern',
    maxLength: 50,
    empty: 'No playlists yet.',
    names: () => Object.keys(state.categories),
    colors: () => state.categoryColors,
    path: name => '/categories/' + encodeURIComponent(name),
    // Same rule as the server: stripped, spaces to underscores, lower case.
    normalise: value => value.trim().replaceAll(' ', '_').toLowerCase(),
    add: name => api('POST', '/categories', {name}),
    added: 'Category added',
  },
  group: {
    title: 'Manage groups',
    hint: 'Rename, colour or delete a group. Its sounds stay on the soundboard.',
    placeholder: 'New group, e.g. tavern',
    maxLength: 30,
    empty: 'No groups yet.',
    names: () => deckGroups(),
    colors: () => state.groupColors,
    path: name => '/deck/groups/' + encodeURIComponent(name),
    normalise: value => value.trim(),
    add: name => api('POST', '/deck/groups', {name}),
    added: 'Group added',
  },
};

let kind = 'playlist';

function current() {
  return KINDS[kind];
}

// Which row's colour palette is open (one at a time), or null.
let pickerFor = null;

function palette(name, color) {
  return `<div class="swatches manage-palette" role="group" aria-label="Colour for ${esc(name)}">
      <button class="swatch auto${color ? '' : ' on'}" data-action="manage-color" data-name="${esc(name)}" data-color="" aria-label="Automatic colour" title="Automatic colour">A</button>
      ${SWATCHES.map(c => `<button class="swatch${color === c ? ' on' : ''}" style="--sw:${c}" data-action="manage-color" data-name="${esc(name)}" data-color="${c}" aria-label="Colour ${c}" title="${c}"></button>`).join('')}
    </div>`;
}

function renderRows() {
  const names = current().names();
  const colors = current().colors();
  $('manageList').innerHTML = names.length
    ? names.map(name => {
        const color = colorOf(colors, name);
        const open = pickerFor === name;
        return `
      <div class="manage-row">
        <div class="manage-line">
          <button class="manage-dot" data-action="manage-picker" data-name="${esc(name)}" style="--c:${color || 'var(--accent)'}"
                  aria-expanded="${open}" aria-label="Colour of ${esc(name)}" title="Colour"></button>
          <input type="text" class="manage-name" value="${esc(name)}" data-name="${esc(name)}" maxlength="${current().maxLength}" aria-label="Name of ${esc(name)}" />
          <button class="btn-primary btn-small" data-action="manage-save" data-name="${esc(name)}">Save</button>
          <button class="btn-danger btn-small" data-action="manage-delete" data-name="${esc(name)}" aria-label="Delete ${esc(name)}" title="Delete">🗑</button>
        </div>
        ${open ? palette(name, color) : ''}
      </div>`;
      }).join('')
    : `<div class="empty"><span class="icon">${kind === 'playlist' ? '🎼' : '🥁'}</span>${current().empty}</div>`;
}

// Opens or closes the colour palette of one row.
export function togglePicker(name) {
  pickerFor = pickerFor === name ? null : name;
  renderRows();
}

export function openManage(which) {
  kind = KINDS[which] ? which : 'playlist';
  pickerFor = null;
  $('manageTitle').textContent = current().title;
  $('manageHint').textContent = current().hint;
  const input = $('manageNew');
  input.value = '';
  input.placeholder = current().placeholder;
  input.maxLength = current().maxLength;
  renderRows();
  const dialog = $('manageDialog');
  if (!dialog.open) dialog.showModal();
}

// Reloads the data behind the open dialog, the same way the rest of the app does.
async function reload() {
  if (kind === 'playlist') await loadCategories();
  else await loadDeck();
}

// Renames from a row's Save button or from Enter in its name box.
export async function saveRow(el) {
  const input = el.closest('.manage-row').querySelector('.manage-name');
  const oldName = input.dataset.name;
  const newName = current().normalise(input.value);
  if (!newName) { input.focus(); return; }
  if (newName === oldName) return;
  const r = await api('PUT', current().path(oldName), {name: newName});
  if (!r) return;
  if (!r.ok) { showToast(r.message ?? 'Could not save', false); return; }
  // Keep the chip you were looking at selected under its new name.
  const stored = current().normalise(newName);
  if (kind === 'playlist' && state.selectedCategory === oldName) {
    state.selectedCategory = stored;
    memory.set('category', stored);
  } else if (kind === 'group' && state.deckFilter === oldName) {
    state.deckFilter = stored;
    memory.set('deckGroup', stored);
  }
  showToast('Saved');
  await reload();
  renderRows();
}

// Sets (or, with an empty colour, clears) the colour of one playlist or group.
export async function setColor(name, color) {
  pickerFor = null;
  const r = await api('PUT', current().path(name), {color: color || null});
  if (!r) return;
  if (!r.ok) { showToast(r.message ?? 'Could not set the colour', false); return; }
  await reload();
  renderRows();
}

// Uses the existing delete functions, so the confirmation and the toast match the ⋮ menus.
export async function removeItem(name) {
  if (kind === 'playlist') await deleteCategory(name);
  else await deleteGroup(name);
  renderRows();
}

export async function addItem() {
  const input = $('manageNew');
  const name = current().normalise(input.value);
  if (!name) { input.focus(); return; }
  const r = await current().add(name);
  if (!r) return;
  if (!r.ok) { showToast(r.message ?? 'Could not add', false); return; }
  input.value = '';
  showToast(current().added);
  await reload();
  renderRows();
  input.focus();
}
