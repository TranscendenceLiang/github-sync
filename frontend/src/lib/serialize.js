export const PLATFORMS = ['github', 'gitee', 'cnb', 'gitcode'];

export function defaultEndpoint() {
  return {
    platform: 'github', owner: '', repo: '',
    branch: 'main', branches: null,
    auth: 'ssh', auto_create: false, visibility: 'private',
  };
}

export function defaultSettings() {
  return {
    auto_create: false, force_push: false, delete_remote: false,
    mode: 'mirror', preserve_files: null,
    sync_releases: false, release_asset_max_size_mb: 50,
    release_filter: { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false },
  };
}

export function parsePreserveFiles(val) {
  if (!val || !val.trim()) return null;
  return val.split(',').map((s) => s.trim()).filter(Boolean);
}

export function serializeReleaseFilter(rf) {
  if (!rf) return null;
  return {
    mode: rf.mode || 'all',
    latest_count: parseInt(rf.latest_count, 10) || 1,
    pattern: rf.pattern || null,
    tags: rf.mode === 'tags' ? (rf.tags && rf.tags.length ? rf.tags : null) : null,
    include_drafts: !!rf.include_drafts,
  };
}

export function serializeEndpoint(ep) {
  const isMulti = Array.isArray(ep.branches) && ep.branches.length > 0;
  return {
    platform: ep.platform,
    owner: ep.owner,
    repo: ep.repo,
    branch: isMulti ? null : (ep.branch || null),
    branches: isMulti ? ep.branches : null,
    auth: ep.auth,
    auto_create: !!ep.auto_create,
    visibility: ep.visibility,
  };
}

export function serializeEntry(entry, settings) {
  const out = {
    name: (entry.name || '').trim(),
    source: serializeEndpoint(entry.source),
    targets: (entry.targets || []).map(serializeEndpoint),
    mode: entry.mode || null,
    preserve_files: parsePreserveFiles(entry.preserve_files),
    sync_releases: entry.sync_releases === true ? true : null,
    release_filter: null,
  };
  if (entry.sync_releases === true) {
    out.release_filter = serializeReleaseFilter(entry.release_filter || settings.release_filter);
  }
  return out;
}

export function buildPayload(config) {
  const s = config.settings;
  return {
    settings: {
      auto_create: s.auto_create,
      force_push: s.force_push,
      delete_remote: s.delete_remote,
      mode: s.mode,
      preserve_files: parsePreserveFiles(s.preserve_files),
      sync_releases: s.sync_releases,
      release_asset_max_size_mb: parseInt(s.release_asset_max_size_mb, 10) || 50,
      release_filter: serializeReleaseFilter(s.release_filter),
    },
    topology: config.topology.map((e) => serializeEntry(e, s)),
  };
}
