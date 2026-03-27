<script lang="ts">
	import { resolve } from '$app/paths';
	import { Canvas } from '@threlte/core';
	import TrustCrystal from '$lib/components/TrustCrystal.svelte';

	function observe(node: HTMLElement) {
		if (typeof IntersectionObserver === 'undefined') {
			node.classList.add('visible');
			return { destroy: () => {} };
		}

		const observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((e) => {
					if (e.isIntersecting) node.classList.add('visible');
				});
			},
			{ threshold: 0.15 }
		);
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	}

	const resources = [
		{
			category: 'Videos',
			items: [
				{
					title: 'Compiling the Law',
					subtitle: 'Engineering HTTPS for AI',
					description: 'A deep dive into the technical implementation of executable constitutional governance.',
					file: 'Compiling_the_Law__Engineering__HTTPS_for_AI_.mp4',
					type: 'Video (MP4)'
				},
				{
					title: 'Architecting Constraints',
					subtitle: 'Building the MACI Governance System',
					description: 'Exploring the Montesquieu-Inspired architecture for multi-agent separation of powers.',
					file: 'Architecting_Constraints__Building_the_MACI_Governance_System.mp4',
					type: 'Video (MP4)'
				}
			]
		},
		{
			category: 'Presentations',
			items: [
				{
					title: 'ACGS Cryptographic Infrastructure',
					subtitle: 'Hash Chains & Audit Integrity',
					description: 'Technical overview of the SHA-256 tamper-evident audit ledger and constitutional binding.',
					file: 'ACGS_Cryptographic_Infrastructure.pptx',
					type: 'Presentation (PPTX)'
				},
				{
					title: 'Architecting Machine Trust',
					subtitle: 'Alignment through Infrastructure',
					description: 'Strategic vision for the transition from model-centric to system-centric AI safety.',
					file: 'Architecting_Machine_Trust.pptx',
					type: 'Presentation (PPTX)'
				}
			]
		}
	];
</script>

<svelte:head>
	<title>Resources — ACGS</title>
</svelte:head>

<section class="py-24 md:py-32 px-8 md:px-12 relative overflow-hidden grid-mesh">
	<!-- 3D Hero Element -->
	<div class="absolute inset-0 z-0 opacity-40 pointer-events-none">
		<Canvas>
			<TrustCrystal />
		</Canvas>
	</div>

	<div class="mx-auto max-w-[1400px] relative z-10">
		<div class="fade-in mb-24 text-center md:text-left" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.4em] text-accent font-bold uppercase">04 — RESOURCES</p>
			<h1 class="font-sans text-6xl font-bold tracking-tight md:text-9xl text-white">Technical <span class="font-serif italic font-light">Arsenal</span></h1>
			<p class="mt-8 max-w-2xl text-lg leading-relaxed text-fg-muted md:text-xl font-light mx-auto md:mx-0">
				Deep dives, architectural blueprints, and demonstration materials for the Advanced Constitutional Governance System.
			</p>
		</div>

		<div class="space-y-24">
			{#each resources as group (group.category)}
				<div class="fade-in" use:observe>
					<h2 class="font-mono text-xs tracking-[0.3em] text-fg-muted uppercase mb-12 border-b border-border/30 pb-4">
						{group.category}
					</h2>
					
					<div class="grid gap-8 md:grid-cols-2">
						{#each group.items as item (item.title)}
							<div class="group relative flex flex-col rounded-2xl border border-border/50 bg-[#0a0a0a] p-10 transition-all duration-300 hover:border-border hover:shadow-2xl hover:-translate-y-1">
								<div class="flex justify-between items-start">
									<div>
										<h3 class="font-sans text-3xl font-light text-white group-hover:text-accent transition-colors">
											{item.title}
										</h3>
										<p class="mt-2 font-mono text-xs tracking-wider text-fg-dim italic">
											{item.subtitle}
										</p>
									</div>
									<span class="font-mono text-[10px] tracking-widest text-fg-dim uppercase border border-border/50 px-2 py-1 rounded">
										{item.type}
									</span>
								</div>
								
								<p class="mt-6 text-sm leading-relaxed text-fg-muted/90 flex-grow">
									{item.description}
								</p>

								<a
									href={resolve(`/resources/${item.file}`)}
									download={item.file}
									class="mt-10 inline-flex items-center justify-between w-full rounded-lg border border-border/60 bg-transparent px-6 py-4 font-mono text-xs tracking-widest uppercase transition-all duration-300 hover:bg-white hover:text-black hover:border-white"
								>
									Download Resource
									<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
									</svg>
								</a>
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>

		<div class="mt-24 pt-12 border-t border-border/30 text-center">
			<p class="font-mono text-xs tracking-wider text-fg-dim">
				For custom architectural reviews or implementation support, contact <a href="mailto:hello@acgs.ai" class="text-accent hover:underline">hello@acgs.ai</a>
			</p>
		</div>
	</div>
</section>
