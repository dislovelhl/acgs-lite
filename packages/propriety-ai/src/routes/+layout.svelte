<script>
	import '../app.css';
	let { children } = $props();
</script>

<div class="noise-overlay"></div>
<div class="min-h-screen bg-bg text-fg">
	{@render children()}
</div>
