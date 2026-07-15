<script>
  import { config, selectedIndex, dirty } from '../stores/config.js';
  import EndpointForm from './EndpointForm.svelte';
  import ReleaseFilter from './ReleaseFilter.svelte';

  function touch() { config.set($config); dirty.set(true); }

  function addTarget() {
    const entry = $config.topology[$selectedIndex];
    if (!entry.targets) entry.targets = [];
    entry.targets = [...entry.targets, { platform: 'github', owner: '', repo: '', branch: 'main', branches: null, auth: 'ssh', auto_create: false, visibility: 'private' }];
    touch();
  }
  function removeTarget(i) {
    const entry = $config.topology[$selectedIndex];
    entry.targets = entry.targets.filter((_, idx) => idx !== i);
    touch();
  }
  function onSyncReleasesChange(e) {
    const entry = $config.topology[$selectedIndex];
    const checked = e.currentTarget.checked;
    entry.sync_releases = checked ? true : null;
    if (checked && !entry.release_filter) {
      entry.release_filter = { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false };
    }
    touch();
  }
</script>

{#if $config.topology[$selectedIndex]}
  {@const entry = $config.topology[$selectedIndex]}
  <div class="form-group">
    <label>条目名称: <input type="text" bind:value={entry.name} oninput={touch} placeholder="如 github-to-cnb" /></label>
  </div>
  <div class="form-group">
    <label>模式:
      <select bind:value={entry.mode} onchange={touch}>
        <option value="">(继承全局)</option>
        <option value="mirror">mirror</option>
        <option value="rebase">rebase</option>
      </select>
    </label>
  </div>
  <div class="form-group">
    <label>preserve_files: <input type="text" bind:value={entry.preserve_files} oninput={touch} placeholder="逗号分隔, 如 .cnb.yml" /></label>
  </div>

  <EndpointForm endpoint={entry.source} label="源端点" />

  <fieldset>
    <legend>目标端点</legend>
    {#each (entry.targets || []) as t, i}
      <div class="target-card">
        <div class="target-header"><span>目标 {i + 1}</span>
          <button type="button" class="btn-small btn-remove-target" onclick={() => removeTarget(i)}>删除</button>
        </div>
        <EndpointForm endpoint={t} label={'目标 ' + (i + 1)} />
      </div>
    {/each}
    <button type="button" class="btn-secondary" onclick={addTarget}>+ 添加目标</button>
  </fieldset>

  <fieldset>
    <legend>Release 同步设置</legend>
    <label class="checkbox-label"><input type="checkbox" checked={entry.sync_releases === true} onchange={onSyncReleasesChange} /> 启用 Release 同步</label>
    {#if entry.sync_releases === true}
      <ReleaseFilter rf={entry.release_filter || $config.settings.release_filter} />
    {/if}
  </fieldset>
{/if}
