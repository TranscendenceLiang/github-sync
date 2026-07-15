import { describe, it, expect } from 'vitest';
import {
  parsePreserveFiles,
  serializeEndpoint,
  serializeReleaseFilter,
  buildPayload,
  defaultSettings,
  defaultEndpoint,
} from './serialize.js';

describe('parsePreserveFiles', () => {
  it('splits on comma, trims each entry, drops empties', () => {
    expect(parsePreserveFiles(' .cnb.yml, Dockerfile ')).toEqual([
      '.cnb.yml',
      'Dockerfile',
    ]);
  });

  it('returns null for empty string', () => {
    expect(parsePreserveFiles('')).toBeNull();
  });

  it('returns null for null', () => {
    expect(parsePreserveFiles(null)).toBeNull();
  });

  it('parsePreserveFiles accepts array input', () => {
    expect(parsePreserveFiles(['.cnb.yml', 'Dockerfile'])).toEqual(['.cnb.yml', 'Dockerfile']);
    expect(parsePreserveFiles([])).toBe(null);
    expect(parsePreserveFiles(['  a ', '', 'b'])).toEqual(['a', 'b']);
  });
});

describe('serializeEndpoint', () => {
  it('keeps branch and null branches for single-branch endpoint', () => {
    expect(serializeEndpoint({ branch: 'main', branches: null })).toMatchObject({
      branch: 'main',
      branches: null,
    });
  });

  it('nulls branch and keeps branches for multi-branch endpoint (multi wins)', () => {
    const out = serializeEndpoint({ branch: 'x', branches: ['a', 'b'] });
    expect(out).toMatchObject({ branch: null, branches: ['a', 'b'] });
  });

  it('treats an empty branches array as single-branch', () => {
    const out = serializeEndpoint({ branch: 'main', branches: [] });
    expect(out).toMatchObject({ branch: 'main', branches: null });
  });
});

describe('serializeReleaseFilter', () => {
  it('keeps tags only in tags mode', () => {
    expect(
      serializeReleaseFilter({ mode: 'tags', tags: ['v1', 'v2'] })
    ).toMatchObject({ mode: 'tags', tags: ['v1', 'v2'] });
  });

  it('nulls tags in non-tags mode', () => {
    expect(
      serializeReleaseFilter({ mode: 'all', tags: ['v1'] })
    ).toMatchObject({ mode: 'all', tags: null });
  });

  it('coerces include_drafts to boolean', () => {
    expect(
      serializeReleaseFilter({ mode: 'all', include_drafts: 1 })
    ).toMatchObject({ include_drafts: true });
    expect(
      serializeReleaseFilter({ mode: 'all', include_drafts: 0 })
    ).toMatchObject({ include_drafts: false });
    expect(
      serializeReleaseFilter({ mode: 'all' })
    ).toMatchObject({ include_drafts: false });
  });

  it('returns null for falsy input', () => {
    expect(serializeReleaseFilter(null)).toBeNull();
    expect(serializeReleaseFilter(undefined)).toBeNull();
  });
});

describe('buildPayload', () => {
  const baseSettings = () => ({
    ...defaultSettings(),
    release_filter: {
      mode: 'all',
      latest_count: 1,
      pattern: null,
      tags: null,
      include_drafts: false,
    },
  });

  it('attaches release_filter on entry when sync_releases is true', () => {
    const config = {
      settings: baseSettings(),
      topology: [
        {
          name: 't1',
          source: defaultEndpoint(),
          targets: [defaultEndpoint()],
          mode: null,
          preserve_files: null,
          sync_releases: true,
          release_filter: { mode: 'tags', tags: ['v1', 'v2'], include_drafts: true },
        },
      ],
    };
    const payload = buildPayload(config);
    const entry = payload.topology[0];
    expect(entry.sync_releases).toBe(true);
    expect(entry.release_filter).toMatchObject({
      mode: 'tags',
      tags: ['v1', 'v2'],
      include_drafts: true,
    });
  });

  it('nulls release_filter/sync_releases on entry when sync_releases is null (inherit)', () => {
    const config = {
      settings: baseSettings(),
      topology: [
        {
          name: 't1',
          source: defaultEndpoint(),
          targets: [defaultEndpoint()],
          mode: null,
          preserve_files: null,
          sync_releases: null,
          release_filter: { mode: 'tags', tags: ['v1'] },
        },
      ],
    };
    const entry = buildPayload(config).topology[0];
    expect(entry.sync_releases).toBeNull();
    expect(entry.release_filter).toBeNull();
  });

  it('serializes settings.release_filter', () => {
    const settings = baseSettings();
    settings.release_filter = { mode: 'tags', tags: ['v1'], include_drafts: true };
    const payload = buildPayload({ settings, topology: [] });
    expect(payload.settings.release_filter).toMatchObject({
      mode: 'tags',
      tags: ['v1'],
      include_drafts: true,
    });
  });

  it('round-trips preserve_files via parsePreserveFiles in settings', () => {
    const settings = baseSettings();
    settings.preserve_files = ' .cnb.yml, Dockerfile ';
    const payload = buildPayload({ settings, topology: [] });
    expect(payload.settings.preserve_files).toEqual(['.cnb.yml', 'Dockerfile']);
  });

  it('round-trips preserve_files via parsePreserveFiles on an entry', () => {
    const config = {
      settings: baseSettings(),
      topology: [
        {
          name: 't1',
          source: defaultEndpoint(),
          targets: [defaultEndpoint()],
          mode: null,
          preserve_files: ' a.txt, b.txt ',
          sync_releases: false,
        },
      ],
    };
    const entry = buildPayload(config).topology[0];
    expect(entry.preserve_files).toEqual(['a.txt', 'b.txt']);
  });
});
