<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import '../app.css';
	let { children } = $props();

	const daysUntil = Math.ceil(
		(new Date('2026-08-02').getTime() - Date.now()) / (1000 * 60 * 60 * 24)
	);

	let time = $state('');
	let scrolled = $state(false);

	onMount(() => {
		const tick = () => {
			const now = new Date();
			time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
		};
		tick();
		const iv = setInterval(tick, 1000);

		const handler = () => {
			scrolled = window.scrollY > 50;
		};
		window.addEventListener('scroll', handler, { passive: true });

		return () => {
			clearInterval(iv);
			window.removeEventListener('scroll', handler);
		};
	});
</script>

<div class="noise-overlay"></div>

<header
	class="fixed top-0 left-0 right-0 z-50 transition-all duration-500
		{scrolled ? 'bg-bg/80 backdrop-blur-md border-b border-border' : ''}"
>
	<nav class="flex items-center justify-between px-6 py-4 md:px-12 md:py-5 max-w-[1600px] mx-auto">
			<a href={resolve('/')} class="group flex items-center gap-3">
			<span class="font-mono text-sm tracking-[0.4em] text-white font-bold">ACGS</span>
			<span
				class="h-1.5 w-1.5 rounded-full bg-accent transition-all duration-300 group-hover:scale-150 group-hover:shadow-[0_0_10px_rgba(59,130,246,0.8)]"
			></span>
			</a>

			<ul class="hidden items-center gap-10 md:flex">
					<li>
						<a
							href={resolve('/#frameworks')}
							class="group relative font-mono text-[10px] tracking-[0.3em] text-fg-muted transition-colors duration-300 hover:text-white"
						>
						FRAMEWORKS
						<span
							class="absolute -bottom-1 left-0 h-px w-0 bg-accent transition-all duration-300 group-hover:w-full"
						></span>
					</a>
				</li>
					<li>
						<a
							href={resolve('/#works')}
							class="group relative font-mono text-[10px] tracking-[0.3em] text-fg-muted transition-colors duration-300 hover:text-white"
						>
						HOW IT WORKS
						<span
							class="absolute -bottom-1 left-0 h-px w-0 bg-accent transition-all duration-300 group-hover:w-full"
						></span>
					</a>
				</li>
				<li>
					<a
						href={resolve('/pricing')}
						class="group relative font-mono text-[10px] tracking-[0.3em] text-fg-muted transition-colors duration-300 hover:text-white"
					>
						PRICING
						<span
							class="absolute -bottom-1 left-0 h-px w-0 bg-accent transition-all duration-300 group-hover:w-full"
						></span>
					</a>
				</li>
				<li>
					<a
						href={resolve('/resources')}
						class="group relative font-mono text-[10px] tracking-[0.3em] text-fg-muted transition-colors duration-300 hover:text-white"
					>
						RESOURCES
						<span
							class="absolute -bottom-1 left-0 h-px w-0 bg-accent transition-all duration-300 group-hover:w-full"
						></span>
					</a>
				</li>
			</ul>

		<div class="hidden items-center gap-4 md:flex">
			<span class="relative flex h-2 w-2">
				<span
					class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber opacity-75"
				></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-amber"></span>
			</span>
			<span class="font-mono text-[10px] tracking-[0.2em] text-fg-muted uppercase font-medium"
				>{daysUntil} DAYS TO EU AI ACT</span
			>
		</div>
	</nav>
</header>

<div class="min-h-screen bg-bg text-fg flex flex-col justify-between pt-[76px]">
	<main class="flex-grow">
		{@render children()}
	</main>

	<!-- Global Footer -->
	<footer class="relative mt-auto">
		<a
			href="https://pypi.org/project/acgs/"
			target="_blank"
			rel="noopener"
			class="group relative block overflow-hidden border-t border-border"
		>
			<div
				class="absolute inset-0 translate-y-full bg-accent transition-transform duration-500 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] group-hover:translate-y-0"
			></div>
			<div
				class="relative flex flex-col items-center justify-between gap-8 px-8 py-16 transition-colors duration-300 md:flex-row md:px-12 md:py-24 max-w-[1600px] mx-auto"
			>
				<h2
					class="font-sans text-4xl font-light tracking-tight group-hover:text-bg md:text-6xl lg:text-7xl"
				>
					pip install <span class="italic">acgs</span>
				</h2>
				<svg
					class="h-12 w-12 transition-all duration-300 group-hover:rotate-45 group-hover:text-bg md:h-16 md:w-16"
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="1.5"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M7 17L17 7M17 7H7M17 7v10" />
				</svg>
			</div>
		</a>

		<div
			class="flex flex-col items-center justify-between gap-4 border-t border-border px-8 py-8 md:flex-row md:px-12 max-w-[1600px] mx-auto"
		>
			<div class="font-mono text-xs tracking-widest text-fg-muted">
				<span class="mr-2">CONSTITUTIONAL HASH</span>
				<span class="tabular-nums text-fg">cdd01ef066bc6cf2</span>
			</div>
				<div class="flex gap-8">
					<a
						href="https://pypi.org/project/acgs/"
						target="_blank"
						rel="noopener"
						class="font-mono text-xs tracking-widest text-fg-muted transition-colors duration-300 hover:text-fg"
					>
						PyPI
					</a>
					<a
						href="https://github.com/acgs-ai/acgs-lite"
						target="_blank"
						rel="noopener"
						class="font-mono text-xs tracking-widest text-fg-muted transition-colors duration-300 hover:text-fg"
					>
						GitHub
					</a>
				</div>
			<div class="font-mono text-xs tracking-widest text-fg-muted">
				<span class="mr-2">LOCAL TIME</span>
				<span class="tabular-nums text-fg">{time}</span>
			</div>
		</div>
	</footer>
</div>
