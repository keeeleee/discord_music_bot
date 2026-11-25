import {$} from '../core/dom.js';
import {api} from '../core/api.js';
import {memory} from '../core/memory.js';
import {showToast} from '../ui/toast.js';
import {updateStatus} from '../player/status.js';

export async function loadGuilds() {
  const guilds = await api('GET', '/guilds');
  if (!guilds) return;
  const sel = $('guildSelect');
  guilds.forEach(g => sel.add(new Option(g.name, g.id)));
}

export async function loadChannels() {
  const guildId = $('guildSelect').value;
  const sel = $('channelSelect');
  sel.length = 1;
  if (!guildId) return;
  const channels = await api('GET', '/guilds/' + encodeURIComponent(guildId) + '/channels');
  channels?.forEach(c => sel.add(new Option('🔊 ' + c.name, c.id)));
}

export async function selectServerAndChannel(guildId, channelId) {
  const guildSel = $('guildSelect');
  if (!guildId || ![...guildSel.options].some(o => o.value === guildId)) return;
  guildSel.value = guildId;
  await loadChannels();
  if (channelId && [...$('channelSelect').options].some(o => o.value === channelId)) {
    $('channelSelect').value = channelId;
  }
}

export async function joinChannel() {
  const guildId = $('guildSelect').value;
  const channelId = $('channelSelect').value;
  if (!guildId || !channelId) { showToast('Select a server and a voice channel', false); return; }
  const r = await api('POST', '/join', {guild_id: guildId, channel_id: channelId});
  if (!r) return;
  showToast(r.message, r.ok);
  if (r.ok) {
    memory.set('guild', guildId);
    memory.set('channel', channelId);
    await updateStatus();
  }
}

export async function leaveChannel() {
  const r = await api('POST', '/leave');
  if (r) showToast(r.ok ? 'Left the channel' : 'Not connected', r.ok);
  await updateStatus();
}
