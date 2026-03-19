<script>
  import '../app.css';
  let { children } = $props();
</script>

<main class="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <div class="p-4">
    {@render children()}
  </div>
</main>
