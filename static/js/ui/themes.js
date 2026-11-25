import {$} from '../core/dom.js';
import {memory} from '../core/memory.js';
import {optionOn, setOption} from '../core/settings.js';

export const SWATCHES = ['#7c6cff', '#ff5d8f', '#3ddc97', '#f5b84b', '#4cc9f0', '#ff6b6b', '#9b5de5', '#06d6a0', '#ef476f', '#118ab2'];

// Colour picker for a form: `action` is the data-action the swatches fire, `current` the chosen #rrggbb or null.
export function colourPicker(current, action) {
  return `<div class="swatches" role="group" aria-label="Button colour">
      <button class="swatch auto${current ? '' : ' on'}" data-action="${action}" data-color="" aria-label="Automatic colour" title="Automatic colour">A</button>
      ${SWATCHES.map(c => `<button class="swatch${current === c ? ' on' : ''}" style="--sw:${c}" data-action="${action}" data-color="${c}" aria-label="Colour ${c}" title="${c}"></button>`).join('')}
    </div>`;
}

export function swatchRow(current) {
  return `<div class="swatches" role="group" aria-label="Button colour">
      <button class="swatch auto${current ? '' : ' on'}" data-action="tile-color" data-color="" aria-label="Automatic colour" title="Automatic colour">A</button>
      ${SWATCHES.map(c => `<button class="swatch${current === c ? ' on' : ''}" style="--sw:${c}" data-action="tile-color" data-color="${c}" aria-label="Colour ${c}" title="${c}"></button>`).join('')}
    </div>`;
}

// Styles: colours for the main buttons, the logo, the progress bar and the background glow.
export const THEMES = {
  default: {name: 'Violet',  a: '#7c6cff', b: '#ff5d8f', soft: '#9a6cff', g1: 'rgba(124,108,255,0.14)', g2: 'rgba(255,93,143,0.09)', bg: '#0b0d14'},
  aurora:  {name: 'Aurora',  a: '#22d3ee', b: '#a78bfa', soft: '#67e8f9', g1: 'rgba(34,211,238,0.16)',  g2: 'rgba(167,139,250,0.12)', bg: '#06101a'},
  sunset:  {name: 'Sunset',  a: '#ff7e5f', b: '#feb47b', soft: '#ffa07a', g1: 'rgba(255,126,95,0.16)',  g2: 'rgba(254,180,123,0.11)', bg: '#140b0c'},
  ocean:   {name: 'Ocean',   a: '#0ea5e9', b: '#2dd4bf', soft: '#38bdf8', g1: 'rgba(14,165,233,0.16)',  g2: 'rgba(45,212,191,0.11)',  bg: '#071018'},
  forest:  {name: 'Forest',  a: '#22c55e', b: '#a3e635', soft: '#4ade80', g1: 'rgba(34,197,94,0.14)',   g2: 'rgba(163,230,53,0.09)',  bg: '#08120c'},
  neon:    {name: 'Neon',    a: '#f0abfc', b: '#facc15', soft: '#e879f9', g1: 'rgba(240,171,252,0.13)', g2: 'rgba(250,204,21,0.09)',  bg: '#0c0712'},
  ember:   {name: 'Ember',   a: '#f97316', b: '#ef4444', soft: '#fb923c', g1: 'rgba(249,115,22,0.16)',  g2: 'rgba(239,68,68,0.11)',   bg: '#120908'},
  // True black background, so OLED pixels switch off; surfaces are near-black and the accents are neon.
  oled:    {name: 'OLED',    a: '#38bdf8', b: '#c084fc', soft: '#7dd3fc', g1: 'rgba(56,189,248,0.07)',  g2: 'rgba(192,132,252,0.06)', bg: '#000000',
            surface: '#050508', surface2: '#0b0b10', surface3: '#131319'},
};

// Surface colours are optional per theme; themes without them fall back to the stylesheet values.
const SURFACE_VARS = {surface: '--surface', surface2: '--surface-2', surface3: '--surface-3'};

export function applyTheme(key) {
  const t = THEMES[key] ? key : 'default';
  const root = document.documentElement.style;
  const theme = THEMES[t];
  root.setProperty('--accent', theme.a);
  root.setProperty('--accent-2', theme.b);
  root.setProperty('--accent-soft', theme.soft);
  root.setProperty('--glow-1', theme.g1);
  root.setProperty('--glow-2', theme.g2);
  root.setProperty('--bg', theme.bg);
  for (const [field, cssVar] of Object.entries(SURFACE_VARS)) {
    if (theme[field]) root.setProperty(cssVar, theme[field]);
    else root.removeProperty(cssVar);
  }
  memory.set('theme', t === 'default' ? null : t);
  $('themeList').innerHTML = Object.entries(THEMES).map(([k, v]) => `
      <button class="theme ${k === t ? 'on' : ''}" data-action="theme" data-theme="${k}" aria-pressed="${k === t}">
        <span class="sw" style="--a:${v.a};--b:${v.b}"></span>${v.name}
      </button>`).join('');
}

// General settings for the whole panel. Each switch is stored in this browser.
const OPTIONS = [
  {key: 'playlistShown', text: 'Show playlist'},
  {key: 'soundboardShown', text: 'Show soundboard'},
];

export function renderOptions() {
  $('optionList').innerHTML = OPTIONS.map(({key, text}) => `
      <button class="tint-option ${optionOn(key) ? 'on' : ''}" data-action="option-toggle" data-option="${key}" aria-pressed="${optionOn(key)}">
        <span class="tint-switch" aria-hidden="true"></span>${text}
      </button>`).join('');
}

// Applies the switches that change the whole page look.
export function applyOptions() {
  document.body.classList.toggle('hide-playlist', !optionOn('playlistShown'));
  document.body.classList.toggle('hide-soundboard', !optionOn('soundboardShown'));
}

export function toggleOption(key) {
  setOption(key, !optionOn(key));
  applyOptions();
  renderOptions();
}

export function toggleStyle(open = $('stylePanel').hidden) {
  $('stylePanel').hidden = !open;
  $('gearBtn').setAttribute('aria-expanded', String(open));
}
