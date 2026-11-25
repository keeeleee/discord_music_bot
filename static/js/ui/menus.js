import {esc} from '../core/dom.js';
import {state, view} from '../core/store.js';
import {MORE_ICON} from './icons.js';

export function attrs(data) {
  return Object.entries(data).map(([k, v]) => ` data-${k}="${esc(v)}"`).join('');
}

// A "⋯" button that opens a small menu. `key` identifies which menu is open.
export function moreMenu(key, items) {
  const open = state.openMenu === key;
  const menu = open
    ? `<div class="menu" role="menu">${items.map(item => `
          <button role="menuitem" class="${item.danger ? 'danger' : ''}" data-action="${item.action}"${attrs(item.data)}>${item.label}</button>`).join('')}
        </div>`
    : '';
  return `<div class="more-wrap">
      <button class="btn-ghost btn-icon more" data-action="menu-toggle" data-key="${esc(key)}" aria-haspopup="menu" aria-expanded="${open}" aria-label="More actions" title="More actions">${MORE_ICON}</button>
      ${menu}
    </div>`;
}

// Menus are position: fixed beside their ⋯ button, so the scrolling columns cannot cut them off.
export function placeMenu() {
  const btn = document.querySelector('.more[aria-expanded="true"]');
  const menu = document.querySelector('.menu');
  if (!btn || !menu) return;
  const r = btn.getBoundingClientRect();
  const left = Math.max(8, Math.min(r.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - 8));
  menu.style.position = 'fixed';
  menu.style.left = left + 'px';
  menu.style.right = 'auto';
  menu.style.top = (r.bottom + 6) + 'px';
  menu.style.zIndex = 60;
}

// Redraws everything that can show an open menu, then places the menu beside its button.
export function refreshMenus() {
  view.tracks();
  view.deck(true);
  placeMenu();
}

// A click outside every ⋯ menu closes the open one.
export function closeMenuOnOutsideClick(e) {
  if (state.openMenu !== null && !e.target.closest('.more-wrap')) {
    state.openMenu = null;
    refreshMenus();
  }
}

// A menu that is open when the page scrolls would drift away from its button, so it closes.
export function closeMenuOnScroll() {
  if (state.openMenu !== null) { state.openMenu = null; refreshMenus(); }
}
