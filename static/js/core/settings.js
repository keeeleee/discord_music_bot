// App-wide settings kept in this browser. Missing key = the default, which is on.
import {memory} from './memory.js';

export function optionOn(key) {
  return memory.get('opt.' + key) !== 'off';
}

export function setOption(key, on) {
  memory.set('opt.' + key, on ? null : 'off');
}
