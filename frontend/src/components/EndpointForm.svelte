<script>
  import { config, dirty } from '../stores/config.js';
  import { PLATFORMS } from '../lib/serialize.js';
  let { endpoint, label = '' } = $props();

  function touch() { config.set($config); dirty.set(true); }

  function isMulti(ep) { return Array.isArray(ep.branches) && ep.branches.length > 0; }

  function setMode(mode) {
    if (mode === 'multi') {
      endpoint.branches = (endpoint.branches && endpoint.branches.length) ? endpoint.branches : ['main'];
      endpoint.branch = null;
    } else {
      endpoint.branches = null;
      if (!endpoint.branch) endpoint.branch = 'main';
    }
    touch();
  }

  function addBranch() {
    const v = window.prompt('输入分支名:');
    if (v && v.trim()) {
      endpoint.branches = [...(endpoint.branches || []), v.trim()];
      touch();
    }
  }
  function removeBranch(b) {
    endpoint.branches = (endpoint.branches || []).filter((x) => x !== b);
    touch();
  }
</script>

<fieldset>
  <legend>{label}</legend>
  <label>平台:
    <select bind:value={endpoint.platform} onchange={touch}>
      {#each PLATFORMS as p}<option value={p}>{p}</option>{/each}
    </select>
  </label>
  <label>所有者: <input type="text" bind:value={endpoint.owner} oninput={touch} /></label>
  <label>仓库: <input type="text" bind:value={endpoint.repo} oninput={touch} /></label>
  <div class="branch-mode">
    <label>分支模式:</label>
    <label><input type="radio" name={label + '-mode'} checked={!isMulti(endpoint)} onchange={() => setMode('single')} /> 单分支</label>
    <label><input type="radio" name={label + '-mode'} checked={isMulti(endpoint)} onchange={() => setMode('multi')} /> 多分支</label>
  </div>
  {#if isMulti(endpoint)}
    <div>分支:
      {#each (endpoint.branches || []) as b}
        <span class="tag-item">{b} <button type="button" class="tag-remove" onclick={() => removeBranch(b)}>×</button></span>
      {/each}
      <button type="button" class="btn-small" onclick={addBranch}>+ 添加分支</button>
    </div>
  {:else}
    <label>分支: <input type="text" bind:value={endpoint.branch} oninput={touch} placeholder="main" /></label>
  {/if}
  <div class="form-row">
    <label>认证:
      <select bind:value={endpoint.auth} onchange={touch}>
        <option value="ssh">SSH</option><option value="pat">PAT</option>
      </select>
    </label>
    <label class="checkbox-label"><input type="checkbox" bind:checked={endpoint.auto_create} onchange={touch} /> auto_create</label>
    <label>可见性:
      <select bind:value={endpoint.visibility} onchange={touch}>
        <option value="private">private</option><option value="public">public</option>
      </select>
    </label>
  </div>
</fieldset>
