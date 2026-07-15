<script>
  let { payload, onConfirm, onCancel } = $props();
</script>
<dialog open>
  <h3>YAML 预览</h3>
  <pre>{JSON.stringify(payload, null, 2)}</pre>
  <div class="dialog-actions">
    <button class="btn-primary" onclick={onConfirm}>确认保存</button>
    <button class="btn-secondary" onclick={onCancel}>取消</button>
  </div>
</dialog>
