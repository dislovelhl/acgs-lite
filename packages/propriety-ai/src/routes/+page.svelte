<script lang="ts">
	// Propriety.ai landing page placeholder
	import { Button } from '$lib';
</script>

<svelte:head>
	<title>Propriety.ai | HTTPS for AI</title>
</svelte:head>

<div class="flex min-h-[80vh] flex-col items-center justify-center space-y-8 text-center">
	<div class="space-y-4">
		<h1 class="text-5xl font-extrabold tracking-tight sm:text-6xl">
			<span class="block">Propriety.ai</span>
			<span class="block text-blue-600 dark:text-blue-400">HTTPS for AI</span>
		</h1>
		<p class="mx-auto max-w-2xl text-xl text-gray-500 dark:text-gray-400">
			The constitutional governance and compliance layer for enterprise AI agents. Fast,
			deterministic validation with a verifiable audit trail.
		</p>
	</div>

	<div class="flex gap-4">
		<Button onclick={() => (window.location.href = '/demo')} variant="primary">View Demo</Button>
		<Button
			onclick={() => window.open('https://github.com/acgs-clean', '_blank')}
			variant="outline"
		>
			Documentation
		</Button>
	</div>
</div>
