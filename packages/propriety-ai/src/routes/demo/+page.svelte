<script lang="ts">
	import { resolve } from '$app/paths';
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

	<div class="relative z-10 flex flex-col items-center gap-12">
		<h1 class="font-sans text-6xl font-bold tracking-tight md:text-8xl text-white">Interactive <span class="font-serif italic font-light">Demo</span></h1>
		<a 
			href={resolve('/demo/playwright')}
			class="group rounded-full border border-white/10 glass px-12 py-5 font-mono text-xs tracking-[0.2em] font-bold text-white transition-all hover:bg-white/5 hover:border-white/30"
		>
			LAUNCH PLAYWRIGHT DEMO
		</a>
	</div>
</section>
