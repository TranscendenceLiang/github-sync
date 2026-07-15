<script>
  let { message, onConfirm, onCancel } = $props();
</script>
<dialog open>
  <p>{message}</p>
  <div class="dialog-actions">
    <button class="btn-danger" onclick={onConfirm}>确认</button>
    <button class="btn-secondary" onclick={onCancel}>取消</button>
  </div>
</dialog>
