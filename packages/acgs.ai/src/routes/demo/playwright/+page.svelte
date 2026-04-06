<script lang="ts">
	import { Canvas } from '@threlte/core';
	import TrustCrystal from '$lib/components/TrustCrystal.svelte';
</script>

<section class="py-24 md:py-32 px-8 md:px-12 relative overflow-hidden grid-mesh h-screen flex flex-col items-center justify-center">
	<!-- 3D Hero Element -->
	<div class="absolute inset-0 z-0 opacity-40 pointer-events-none">
		<Canvas>
			<TrustCrystal />
		</Canvas>
	</div>

	<div class="relative z-10 flex flex-col items-center gap-12 text-center">
		<h1 class="font-sans text-6xl font-bold tracking-tight md:text-8xl text-white">Playwright <span class="font-serif italic font-light text-white/90">E2E</span></h1>
		<p class="font-mono text-xs tracking-widest text-fg-muted uppercase">Automated Verification Suite</p>
	</div>
</section>
