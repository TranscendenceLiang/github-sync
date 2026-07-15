<script>
  import { status } from '../stores/config.js';
</script>

<span id="status-msg" class="status-msg {$status.type}">{$status.msg}</span>
