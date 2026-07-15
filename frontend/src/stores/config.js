import { writable } from 'svelte/store';
import { defaultSettings, defaultEndpoint } from '../lib/serialize.js';

export const config = writable({ settings: defaultSettings(), topology: [] });
export const selectedIndex = writable(-1);
export const dirty = writable(false);
export const status = writable({ msg: '', type: '' });

export function newEntry() {
  return {
    name: '',
    source: { ...defaultEndpoint() },
    targets: [{ ...defaultEndpoint() }],
    mode: null,
    preserve_files: null,
    sync_releases: null,
    release_filter: null,
  };
}
