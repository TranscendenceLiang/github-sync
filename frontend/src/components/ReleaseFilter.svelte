<script>
  import { config, dirty } from '../stores/config.js';
  let { rf } = $props();

  function touch() { config.set($config); dirty.set(true); }

  function addTag() {
    const v = window.prompt('输入标签:');
    if (v && v.trim()) {
      rf.tags = [...(rf.tags || []), v.trim()];
      touch();
    }
  }
  function removeTag(t) {
    rf.tags = (rf.tags || []).filter((x) => x !== t);
    touch();
  }
</script>

<div class="release-filter">
  <label>模式:
    <select bind:value={rf.mode} onchange={touch}>
      <option value="all">all</option>
      <option value="latest">latest</option>
      <option value="pattern">pattern</option>
      <option value="tags">tags</option>
    </select>
  </label>
  <label>最新 N 个: <input type="number" bind:value={rf.latest_count} oninput={touch} min="1" /></label>
  <label>正则模式: <input type="text" bind:value={rf.pattern} oninput={touch} placeholder="如 v*" /></label>
  {#if rf.mode === 'tags'}
    <label>标签:
      <div class="tag-list">
        {#each (rf.tags || []) as t}
          <span class="tag-item">{t} <button type="button" class="tag-remove" onclick={() => removeTag(t)}>×</button></span>
        {/each}
      </div>
      <button type="button" class="btn-small" onclick={addTag}>+ 添加标签</button>
    </label>
  {/if}
  <label class="checkbox-label"><input type="checkbox" bind:checked={rf.include_drafts} onchange={touch} /> 包含草稿 release</label>
</div>
