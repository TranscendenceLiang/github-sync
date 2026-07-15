<script>
  import { config, selectedIndex } from '../stores/config.js';
  function select(i) { selectedIndex.set(i); }
</script>

<ul id="entry-items">
  {#each $config.topology as entry, i}
    <li data-index={i} class:active={i === $selectedIndex} onclick={() => select(i)}>
      <strong>{entry.name}</strong><br />
      <span class="entry-summary">{(entry.source && entry.source.platform) || '?'} → {(entry.targets || []).length} 个目标</span>
    </li>
  {/each}
</ul>
