// The one place where the panel's UI state lives. Modules read and write these fields directly.
export const state = {
  status: {},               // last /api/status answer
  statusReceivedAt: 0,      // Date.now() when that status arrived (for the progress timer)
  waveformKey: null,        // track whose waveform is drawn (file or url)
  waveformPeaks: null,      // its bar heights, 0..1
  categories: {},           // playlists: name -> tracks
  categoryColors: {},       // playlist name -> #rrggbb (missing = automatic)
  groupColors: {},          // soundboard group name -> #rrggbb (missing = automatic)
  selectedCategory: null,   // playlist shown in the track list
  deck: [],                 // soundboard tiles
  deckGroupsStored: [],     // groups created by the user, also those without tiles yet
  deckKey: '',              // last render key of the soundboard, to skip redundant renders
  openMenu: null,           // which ⋯ menu is open, e.g. 'track:combat_music:2'
  editing: null,            // {kind:'track', cat, index} or {kind:'tile', index}
  picked: new Set(),        // selected track indices in the current playlist
  trackMode: 'url',         // 'url' or 'file' in the track modal
  deckMode: 'url',          // 'url' or 'file' in the sound modal
  deckFilter: 'all',        // 'all', '' (no group) or a group name
  trackQuery: '',           // search text for the playlist
  deckQuery: '',            // search text for the soundboard
  scrolledTo: null,         // playing track we last scrolled to
};

// Render functions are registered by main.js. Data and player modules call these
// instead of importing the renderers, which keeps the module graph free of cycles.
export const view = {
  playlist() {},  // category tabs and track list
  tracks() {},    // track list only
  deck() {},      // soundboard (uses its own change check unless forced)
};
