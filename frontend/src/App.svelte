<script>
  import { onMount } from 'svelte';
  import { getConfig, saveConfig, validateConfig } from './api/config.js';
  import { buildPayload } from './lib/serialize.js';
  import { config, selectedIndex, dirty, status, newEntry } from './stores/config.js';
  import EntryList from './components/EntryList.svelte';
  import EntryEditor from './components/EntryEditor.svelte';
  import SettingsPanel from './components/SettingsPanel.svelte';
  import YamlPreview from './components/YamlPreview.svelte';
  import ConfirmDialog from './components/ConfirmDialog.svelte';
  import StatusBar from './components/StatusBar.svelte';

  let showSettings = $state(false);
  let yamlPayload = $state(null);
  let confirmMsg = $state('');
  let pendingConfirm = null;

  function setStatus(msg, type) {
    status.set({ msg, type });
    if (type !== 'error') setTimeout(() => status.set({ msg: '', type: '' }), 3000);
  }

  const DEFAULT_SETTINGS = {
    auto_create: false, force_push: false, delete_remote: false,
    mode: 'mirror', preserve_files: null, sync_releases: false,
    release_asset_max_size_mb: 50,
    release_filter: { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false },
  };

  async function loadConfig() {
    try {
      const data = await getConfig();
      if (!data.settings) data.settings = { ...DEFAULT_SETTINGS };
      if (!data.topology) data.topology = [];
      if (Array.isArray(data.settings.preserve_files)) data.settings.preserve_files = data.settings.preserve_files.join(', ');
      (data.topology || []).forEach((e) => {
        if (Array.isArray(e.preserve_files)) e.preserve_files = e.preserve_files.join(', ');
      });
      config.set(data);
      selectedIndex.set(data.topology.length > 0 ? 0 : -1);
      dirty.set(false);
    } catch (e) {
      setStatus('加载配置失败: ' + (e.message || e), 'error');
    }
  }

  onMount(loadConfig);

  $effect(() => {
    const d = $dirty;
    const handler = (e) => {
      if (d) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  });

  function addEntry() {
    const name = window.prompt('输入新条目名称:');
    if (!name || !name.trim()) return;
    config.update((c) => {
      const t = [...c.topology, newEntry()];
      t[t.length - 1].name = name.trim();
      return { ...c, topology: t };
    });
    selectedIndex.set($config.topology.length - 1);
    dirty.set(true);
  }

  function deleteEntry() {
    if ($selectedIndex < 0) return;
    const nm = $config.topology[$selectedIndex]?.name ?? '';
    openConfirm(`确定删除条目「${nm}」？`, () => {
      config.update((c) => {
        const t = [...c.topology];
        t.splice($selectedIndex, 1);
        return { ...c, topology: t };
      });
      selectedIndex.set(-1);
      dirty.set(true);
      setStatus('条目已删除（未保存）', '');
    });
  }

  function openConfirm(msg, onYes) { confirmMsg = msg; pendingConfirm = onYes; }
  function onConfirmYes() { const fn = pendingConfirm; pendingConfirm = null; confirmMsg = ''; if (fn) fn(); }
  function onConfirmNo() { pendingConfirm = null; confirmMsg = ''; }

  function refresh() {
    if ($dirty) openConfirm('有未保存的修改，确定刷新？', loadConfig);
    else loadConfig();
  }

  function validate() {
    try {
      const payload = buildPayload($config);
      validateConfig(payload)
        .then(() => setStatus('配置校验通过', 'success'))
        .catch((e) => setStatus('校验失败: ' + (e.message || e), 'error'));
    } catch (e) { setStatus('校验失败: ' + (e.message || e), 'error'); }
  }

  function save() {
    try {
      yamlPayload = buildPayload($config);
    } catch (e) { setStatus('保存失败: ' + (e.message || e), 'error'); }
  }
  async function onYamlConfirm() {
    const payload = yamlPayload; yamlPayload = null;
    try { await saveConfig(payload); dirty.set(false); setStatus('配置已保存', 'success'); }
    catch (e) { setStatus('保存失败: ' + (e.message || e), 'error'); }
  }
  function onYamlCancel() { yamlPayload = null; }
</script>

<header>
  <h1>Git Multi-Sync Center · 配置管理</h1>
  <div class="header-actions">
    <button class="btn-icon" title="全局设置" onclick={() => (showSettings = !showSettings)}>&#9881;</button>
    <button class="btn-primary" onclick={addEntry}>+ 新增同步条目</button>
  </div>
</header>

{#if showSettings}
  <SettingsPanel />
{/if}

<div class="main-layout">
  <aside id="entry-list">
    <h3>同步条目</h3>
    <EntryList />
  </aside>
  <main id="entry-editor">
    {#if $selectedIndex >= 0}
      <EntryEditor />
    {:else}
      <div class="editor-placeholder"><p>选择左侧条目进行编辑，或点击「+ 新增同步条目」创建新条目。</p></div>
    {/if}
  </main>
</div>

<footer class="action-bar">
  <button class="btn-secondary" onclick={validate}>&#10003; 校验配置</button>
  <button class="btn-primary" onclick={save}>&#128190; 保存</button>
  <button class="btn-secondary" onclick={refresh}>&#8635; 刷新</button>
  <button class="btn-danger" onclick={deleteEntry}>删除此条目</button>
  <StatusBar />
</footer>

{#if yamlPayload}
  <YamlPreview payload={yamlPayload} onConfirm={onYamlConfirm} onCancel={onYamlCancel} />
{/if}
{#if confirmMsg}
  <ConfirmDialog message={confirmMsg} onConfirm={onConfirmYes} onCancel={onConfirmNo} />
{/if}
