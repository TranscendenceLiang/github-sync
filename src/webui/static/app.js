'use strict';

// ── State ──────────────────────────────────────────
let config = null;          // full config object from API
let selectedIndex = -1;      // index into config.topology
let dirty = false;           // unsaved changes tracker
let currentEntryId = null;   // for tracking which entry is being edited
let targetBranchCounter = 0; // counter for unique target branch radio names

// ── DOM refs ───────────────────────────────────────
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const entryItems = $('#entry-items');
const editorForm = $('#editor-form');
const editorPlaceholder = $('#editor-placeholder');
const settingsPanel = $('#settings-panel');
const statusMsg = $('#status-msg');

// ── API helpers ────────────────────────────────────
async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  return r.json();
}

async function apiPost(path, data) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const result = await r.json();
  if (!r.ok || result.ok === false) throw new Error(result.error || 'Unknown error');
  return result;
}

function setStatus(msg, type) {
  statusMsg.textContent = msg;
  statusMsg.className = 'status-msg' + (type ? ' ' + type : '');
  if (type !== 'error') setTimeout(() => { statusMsg.textContent = ''; statusMsg.className = 'status-msg'; }, 3000);
}

// ── Data helpers ────────────────────────────────────
function getDefaultSettings() {
  return {
    auto_create: false, force_push: false, delete_remote: false,
    mode: 'mirror', preserve_files: null,
    sync_releases: false, release_asset_max_size_mb: 50,
    release_filter: { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false },
  };
}

function getDefaultEndpoint() {
  return {
    platform: 'github', owner: '', repo: '',
    branch: 'main', branches: null,
    auth: 'ssh', auto_create: false, visibility: 'private',
  };
}

// ── Load config ─────────────────────────────────────
async function loadConfig() {
  try {
    config = await apiGet('/api/config');
    if (!config.settings) config.settings = getDefaultSettings();
    if (!config.topology) config.topology = [];
    renderEntryList();
    if (config.topology.length > 0) {
      selectEntry(0);
    } else {
      showPlaceholder();
    }
    dirty = false;
  } catch (e) {
    setStatus('加载配置失败: ' + e.message, 'error');
  }
}

// ── Entry list rendering ────────────────────────────
function renderEntryList() {
  entryItems.innerHTML = '';
  config.topology.forEach((entry, i) => {
    const li = document.createElement('li');
    li.dataset.index = i;
    const src = entry.source || {};
    li.innerHTML = `<strong>${entry.name}</strong><br><span class="entry-summary">${src.platform || '?'} → ${(entry.targets || []).length} 个目标</span>`;
    if (i === selectedIndex) li.classList.add('active');
    li.addEventListener('click', () => selectEntry(i));
    entryItems.appendChild(li);
  });
}

function showPlaceholder() {
  editorForm.classList.add('hidden');
  editorPlaceholder.classList.remove('hidden');
}

function selectEntry(index) {
  selectedIndex = index;
  renderEntryList();
  const entry = config.topology[index];
  if (!entry) { showPlaceholder(); return; }
  editorPlaceholder.classList.add('hidden');
  editorForm.classList.remove('hidden');
  fillEntryForm(entry);
}

// ── Fill entry form ─────────────────────────────────
function fillEntryForm(entry) {
  $('#e-name').value = entry.name || '';
  $('#e-mode').value = entry.mode || '';
  $('#e-preserve-files').value = (entry.preserve_files || []).join(', ');
  fillEndpointForm('source-endpoint', entry.source || getDefaultEndpoint());
  renderTargets(entry.targets || []);
  const sr = entry.sync_releases;
  if (sr === true) {
    $('#e-sync-releases').checked = true;
  } else if (sr === false) {
    $('#e-sync-releases').checked = false;
  } else {
    $('#e-sync-releases').checked = config.settings.sync_releases;
  }
  fillReleaseFilter('e-rf', entry.release_filter || config.settings.release_filter);
}

function fillEndpointForm(containerId, ep) {
  const container = document.getElementById(containerId);
  container.querySelector('.ep-platform').value = ep.platform || 'github';
  container.querySelector('.ep-owner').value = ep.owner || '';
  container.querySelector('.ep-repo').value = ep.repo || '';
  const singleMode = ep.branches === null || ep.branches === undefined;
  const radios = container.querySelectorAll('input[type="radio"]');
  radios.forEach(r => r.checked = (r.value === (singleMode ? 'single' : 'multi')));
  const singleDiv = container.querySelector('.branch-single');
  const multiDiv = container.querySelector('.branch-multi');
  singleDiv.classList.toggle('hidden', !singleMode);
  multiDiv.classList.toggle('hidden', singleMode);
  if (singleMode) {
    container.querySelector('.ep-branch').value = ep.branch || '';
  } else {
    renderBranchTags(container.querySelector('.ep-branches'), ep.branches || []);
  }
  container.querySelector('.ep-auth').value = ep.auth || 'ssh';
  container.querySelector('.ep-auto-create').checked = ep.auto_create || false;
  container.querySelector('.ep-visibility').value = ep.visibility || 'private';
}

function renderBranchTags(container, branches) {
  container.innerHTML = '';
  (branches || []).forEach(b => {
    const tag = document.createElement('span');
    tag.className = 'tag-item';
    tag.innerHTML = `${b} <span class="tag-remove" data-value="${b}">&times;</span>`;
    container.appendChild(tag);
  });
}

function renderTargets(targets) {
  const container = $('#targets-container');
  container.innerHTML = '';
  targets.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'target-card';
    card.innerHTML = `
      <div class="target-header">
        <span>目标 ${i + 1}</span>
        <button class="btn-small btn-remove-target" data-index="${i}">删除</button>
      </div>
      <div class="endpoint-form">
        <label>平台: <select class="ep-platform">${platformOptions(t.platform)}</select></label>
        <label>所有者: <input type="text" class="ep-owner" value="${t.owner || ''}"></label>
        <label>仓库: <input type="text" class="ep-repo" value="${t.repo || ''}"></label>
        <div class="branch-mode">
          <label>分支模式:
            <label><input type="radio" name="target-branch-${targetBranchCounter++}" value="single" ${t.branches ? '' : 'checked'}> 单分支</label>
            <label><input type="radio" name="target-branch-${targetBranchCounter}" value="multi" ${t.branches ? 'checked' : ''}> 多分支</label>
          </label>
        </div>
        <div class="branch-single ${t.branches ? 'hidden' : ''}">
          <label>分支: <input type="text" class="ep-branch" value="${t.branch || ''}"></label>
        </div>
        <div class="branch-multi ${t.branches ? '' : 'hidden'}">
          <label>分支: <div class="tag-list ep-branches"></div>
          <button class="btn-small btn-add-branch">+ 添加分支</button></label>
        </div>
        <div class="form-row">
          <label>认证: <select class="ep-auth"><option value="ssh" ${t.auth === 'ssh' ? 'selected' : ''}>SSH</option><option value="pat" ${t.auth === 'pat' ? 'selected' : ''}>PAT</option></select></label>
          <label class="checkbox-label"><input type="checkbox" class="ep-auto-create" ${t.auto_create ? 'checked' : ''}> auto_create</label>
          <label>可见性: <select class="ep-visibility"><option value="private" ${t.visibility === 'private' ? 'selected' : ''}>private</option><option value="public" ${t.visibility === 'public' ? 'selected' : ''}>public</option></select></label>
        </div>
      </div>`;
    container.appendChild(card);
    const radios = card.querySelectorAll('input[type="radio"]');
    radios.forEach(r => r.addEventListener('change', () => {
      const single = card.querySelector('.branch-single');
      const multi = card.querySelector('.branch-multi');
      single.classList.toggle('hidden', r.value === 'multi');
      multi.classList.toggle('hidden', r.value === 'single');
    }));
    card.querySelector('.btn-add-branch')?.addEventListener('click', () => {
      const tagList = card.querySelector('.ep-branches');
      const val = prompt('输入分支名:');
      if (val && val.trim()) addTag(tagList, val.trim());
    });
    card.querySelector('.btn-remove-target')?.addEventListener('click', () => {
      const idx = parseInt(card.querySelector('.btn-remove-target').dataset.index);
      config.topology[selectedIndex].targets.splice(idx, 1);
      renderTargets(config.topology[selectedIndex].targets);
      dirty = true;
    });
  });
}

function addTag(container, value) {
  const tag = document.createElement('span');
  tag.className = 'tag-item';
  tag.innerHTML = `${value} <span class="tag-remove">&times;</span>`;
  tag.querySelector('.tag-remove').addEventListener('click', () => tag.remove());
  container.appendChild(tag);
}

function platformOptions(selected) {
  const platforms = ['github', 'gitee', 'cnb', 'gitcode'];
  return platforms.map(p => `<option value="${p}" ${p === selected ? 'selected' : ''}>${p}</option>`).join('');
}

// ── Collect form data ────────────────────────────────
function collectEndpointForm(containerId) {
  const container = document.getElementById(containerId);
  const isMulti = container.querySelector('input[type="radio"][value="multi"]')?.checked;
  const branches = [];
  if (isMulti) {
    container.querySelectorAll('.ep-branches .tag-item').forEach(tag => {
      branches.push(tag.textContent.replace('×', '').trim());
    });
  }
  return {
    platform: container.querySelector('.ep-platform').value,
    owner: container.querySelector('.ep-owner').value,
    repo: container.querySelector('.ep-repo').value,
    branch: isMulti ? null : (container.querySelector('.ep-branch').value || null),
    branches: isMulti ? (branches.length > 0 ? branches : null) : null,
    auth: container.querySelector('.ep-auth').value,
    auto_create: container.querySelector('.ep-auto-create').checked,
    visibility: container.querySelector('.ep-visibility').value,
  };
}

function collectReleaseFilter(prefix) {
  const mode = $(`#${prefix}-mode`).value;
  return {
    mode,
    latest_count: parseInt($(`#${prefix}-latest-count`).value) || 1,
    pattern: $(`#${prefix}-pattern`).value || null,
    tags: mode === 'tags' ? collectTags(prefix) : null,
    include_drafts: $(`#${prefix}-include-drafts`).checked,
  };
}

function collectTags(prefix) {
  const tags = [];
  document.querySelectorAll(`#${prefix}-tags .tag-item`).forEach(tag => {
    tags.push(tag.textContent.replace('×', '').trim());
  });
  return tags.length > 0 ? tags : null;
}

function collectFormEntry() {
  const entry = {
    name: $('#e-name').value.trim(),
    source: collectEndpointForm('source-endpoint'),
    targets: collectTargets(),
    mode: $('#e-mode').value || null,
    preserve_files: parsePreserveFiles($('#e-preserve-files').value),
    sync_releases: $('#e-sync-releases').checked ? true : null,
    release_filter: null,
  };
  if ($('#e-sync-releases').checked) {
    entry.release_filter = collectReleaseFilter('e-rf');
  }
  return entry;
}

function collectTargets() {
  const targets = [];
  $$('#targets-container .target-card').forEach(card => {
    const isMulti = card.querySelector('input[type="radio"][value="multi"]')?.checked;
    const branches = [];
    if (isMulti) {
      card.querySelectorAll('.ep-branches .tag-item').forEach(tag => {
        branches.push(tag.textContent.replace('×', '').trim());
      });
    }
    targets.push({
      platform: card.querySelector('.ep-platform').value,
      owner: card.querySelector('.ep-owner').value,
      repo: card.querySelector('.ep-repo').value,
      branch: isMulti ? null : (card.querySelector('.ep-branch').value || null),
      branches: isMulti ? (branches.length > 0 ? branches : null) : null,
      auth: card.querySelector('.ep-auth').value,
      auto_create: card.querySelector('.ep-auto-create').checked,
      visibility: card.querySelector('.ep-visibility').value,
    });
  });
  return targets;
}

function parsePreserveFiles(val) {
  if (!val || !val.trim()) return null;
  return val.split(',').map(s => s.trim()).filter(Boolean);
}

// ── Settings panel ──────────────────────────────────
function fillSettingsPanel(settings) {
  $('#s-auto-create').checked = settings.auto_create || false;
  $('#s-force-push').checked = settings.force_push || false;
  $('#s-delete-remote').checked = settings.delete_remote || false;
  $('#s-sync-releases').checked = settings.sync_releases || false;
  $('#s-mode').value = settings.mode || 'mirror';
  $('#s-preserve-files').value = (settings.preserve_files || []).join(', ');
  $('#s-release-asset-max-size').value = settings.release_asset_max_size_mb || 50;
  fillReleaseFilter('s-rf', settings.release_filter || { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false });
}

function fillReleaseFilter(prefix, rf) {
  if (!rf) rf = { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false };
  $(`#${prefix}-mode`).value = rf.mode || 'all';
  $(`#${prefix}-latest-count`).value = rf.latest_count || 1;
  $(`#${prefix}-pattern`).value = rf.pattern || '';
  $(`#${prefix}-include-drafts`).checked = rf.include_drafts || false;
  const tagContainer = $(`#${prefix}-tags`);
  if (tagContainer) {
    tagContainer.innerHTML = '';
    (rf.tags || []).forEach(t => addTag(tagContainer, t));
  }
}

// ── Save ────────────────────────────────────────────
async function saveConfig() {
  if (selectedIndex >= 0) {
    config.topology[selectedIndex] = collectFormEntry();
  }
  const payload = {
    settings: {
      auto_create: $('#s-auto-create').checked,
      force_push: $('#s-force-push').checked,
      delete_remote: $('#s-delete-remote').checked,
      mode: $('#s-mode').value,
      preserve_files: parsePreserveFiles($('#s-preserve-files').value),
      sync_releases: $('#s-sync-releases').checked,
      release_asset_max_size_mb: parseInt($('#s-release-asset-max-size').value) || 50,
      release_filter: collectReleaseFilter('s-rf'),
    },
    topology: config.topology,
  };
  try {
    await apiPost('/api/config', payload);
    setStatus('配置已保存', 'success');
    dirty = false;
  } catch (e) {
    setStatus('保存失败: ' + e.message, 'error');
  }
}

// ── Validate ────────────────────────────────────────
async function validateConfig() {
  const payload = {
    settings: {
      auto_create: $('#s-auto-create').checked,
      force_push: $('#s-force-push').checked,
      delete_remote: $('#s-delete-remote').checked,
      mode: $('#s-mode').value,
      preserve_files: parsePreserveFiles($('#s-preserve-files').value),
      sync_releases: $('#s-sync-releases').checked,
      release_asset_max_size_mb: parseInt($('#s-release-asset-max-size').value) || 50,
      release_filter: collectReleaseFilter('s-rf'),
    },
    topology: config.topology,
  };
  try {
    await apiPost('/api/validate', payload);
    setStatus('配置校验通过', 'success');
  } catch (e) {
    setStatus('校验失败: ' + e.message, 'error');
  }
}

// ── Event wiring ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();

  $('#btn-settings').addEventListener('click', () => {
    settingsPanel.classList.toggle('hidden');
    if (!settingsPanel.classList.contains('hidden')) fillSettingsPanel(config.settings);
  });

  $('#btn-add-entry').addEventListener('click', () => {
    const name = prompt('输入新条目名称:');
    if (!name || !name.trim()) return;
    config.topology.push({
      name: name.trim(),
      source: { ...getDefaultEndpoint() },
      targets: [{ ...getDefaultEndpoint() }],
      mode: null, preserve_files: null, sync_releases: null, release_filter: null,
    });
    renderEntryList();
    selectEntry(config.topology.length - 1);
    dirty = true;
  });

  $('#btn-delete-entry').addEventListener('click', () => {
    if (selectedIndex < 0) return;
    if (!confirm(`确定删除条目「${config.topology[selectedIndex].name}」？`)) return;
    config.topology.splice(selectedIndex, 1);
    selectedIndex = -1;
    renderEntryList();
    showPlaceholder();
    dirty = true;
    setStatus('条目已删除（未保存）', '');
  });

  $('#btn-add-target').addEventListener('click', () => {
    if (selectedIndex < 0) return;
    if (!config.topology[selectedIndex].targets) config.topology[selectedIndex].targets = [];
    config.topology[selectedIndex].targets.push({ ...getDefaultEndpoint() });
    renderTargets(config.topology[selectedIndex].targets);
    dirty = true;
  });

  $('#btn-save').addEventListener('click', saveConfig);
  $('#btn-validate').addEventListener('click', validateConfig);
  $('#btn-refresh').addEventListener('click', () => {
    if (dirty && !confirm('有未保存的修改，确定刷新？')) return;
    loadConfig();
  });

  document.addEventListener('change', (e) => {
    if (e.target.matches('#source-endpoint input[type="radio"]')) {
      const single = document.querySelector('#source-endpoint .branch-single');
      const multi = document.querySelector('#source-endpoint .branch-multi');
      single.classList.toggle('hidden', e.target.value === 'multi');
      multi.classList.toggle('hidden', e.target.value === 'single');
    }
  });

  document.addEventListener('click', (e) => {
    if (e.target.matches('#source-endpoint .btn-add-branch')) {
      const tagList = document.querySelector('#source-endpoint .ep-branches');
      const val = prompt('输入分支名:');
      if (val && val.trim()) addTag(tagList, val.trim());
    }
    if (e.target.matches('.tag-remove')) {
      e.target.parentElement.remove();
    }
  });

  $('#s-rf-add-tag')?.addEventListener('click', () => {
    const val = prompt('输入标签:');
    if (val && val.trim()) addTag($('#s-rf-tags'), val.trim());
  });

  $('#e-rf-add-tag')?.addEventListener('click', () => {
    const val = prompt('输入标签:');
    if (val && val.trim()) addTag($('#e-rf-tags'), val.trim());
  });

  editorForm.addEventListener('change', () => { dirty = true; });
  editorForm.addEventListener('input', () => { dirty = true; });

  settingsPanel.addEventListener('change', () => { dirty = true; });
  settingsPanel.addEventListener('input', () => { dirty = true; });

  window.addEventListener('beforeunload', (e) => {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
});
