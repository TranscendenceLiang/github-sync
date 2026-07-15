<script>
  import { config, dirty } from '../stores/config.js';
  import ReleaseFilter from './ReleaseFilter.svelte';

  function touch() { config.set($config); dirty.set(true); }
</script>

<div class="panel">
  <h2>全局设置</h2>
  <div class="settings-grid">
    <label class="checkbox-label"><input type="checkbox" bind:checked={$config.settings.auto_create} onchange={touch} /> auto_create</label>
    <label class="checkbox-label"><input type="checkbox" bind:checked={$config.settings.force_push} onchange={touch} /> force_push</label>
    <label class="checkbox-label"><input type="checkbox" bind:checked={$config.settings.delete_remote} onchange={touch} /> delete_remote</label>
    <label class="checkbox-label"><input type="checkbox" bind:checked={$config.settings.sync_releases} onchange={touch} /> sync_releases</label>
    <label>模式:
      <select bind:value={$config.settings.mode} onchange={touch}>
        <option value="mirror">mirror</option>
        <option value="rebase">rebase</option>
      </select>
    </label>
    <label>preserve_files: <input type="text" bind:value={$config.settings.preserve_files} oninput={touch} placeholder="逗号分隔, 如 .cnb.yml" /></label>
    <label>Release 资源大小上限 (MB): <input type="number" bind:value={$config.settings.release_asset_max_size_mb} oninput={touch} min="1" /></label>
  </div>
  <details>
    <summary>Release 过滤</summary>
    <ReleaseFilter rf={$config.settings.release_filter} />
  </details>
</div>
