<script>
  import { onMount } from 'svelte';
  let { message, onConfirm, onCancel } = $props();
  let dlg;
  onMount(() => { if (dlg) dlg.showModal(); });
</script>

<dialog bind:this={dlg}>
  <p>{message}</p>
  <div class="dialog-actions">
    <button class="btn-danger" onclick={onConfirm}>确认</button>
    <button class="btn-secondary" onclick={onCancel}>取消</button>
  </div>
</dialog>
