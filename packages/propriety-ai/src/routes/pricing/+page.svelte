<script lang="ts">
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

	const tiers = [
		{
			name: 'Community',
			price: 'Free',
			period: 'forever',
			desc: 'Full engine, local audit, MACI separation of powers.',
			items: [
				'Complete governance engine',
				'YAML + code-first rules',
				'MACI separation of powers',
				'Local tamper-evident audit trail',
				'Real-time CLI watch mode',
				'Optional Rust acceleration',
				'Community support (GitHub)'
			],
			cta: 'pip install acgs',
			ctaHref: 'https://pypi.org/project/acgs/'
		},
		{
			name: 'Pro',
			price: '$299',
			period: '/month',
			desc: 'Compliance reports, cloud audit, 3 regulatory frameworks.',
			items: [
				'Everything in Community',
				'1M validations/month',
				'Real-time observability stream',
				'EU AI Act Article 12 audit logger',
				'Risk classification engine',
				'Compliance gap report (PDF/JSON)',
				'Cloud audit sync (30-day retention)',
				'Email support (48h SLA)'
			],
			cta: 'Start free trial',
			ctaHref: '#',
			highlight: true
		},
		{
			name: 'Team',
			price: '$999',
			period: '/month',
			desc: 'All 9 frameworks, SSO, multi-constitution management.',
			items: [
				'Everything in Pro',
				'10M validations/month',
				'Portable telemetry bundles',
				'OpenTelemetry + Prometheus integration',
				'Multi-constitution (dev/staging/prod)',
				'Constitutional change approval workflow',
				'Cloud audit (1-year retention)',
				'SSO (SAML/OIDC)',
				'Priority support (4h SLA)'
			],
			cta: 'Start free trial',
			ctaHref: '#'
		},
		{
			name: 'Enterprise',
			price: 'Custom',
			period: '',
			desc: 'On-prem, unlimited, dedicated compliance engineer.',
			items: [
				'Everything in Team',
				'Unlimited validations',
				'1.1M RPS throughput SLA',
				'3.9µs P99 latency guarantee',
				'Custom regulatory frameworks',
				'On-premise / VPC deployment',
				'Dedicated compliance engineer',
				'Quarterly constitutional review',
				'Audit integration (Splunk, Datadog, ELK)',
				'Dedicated support (1h SLA)'
			],
			cta: 'Contact sales',
			ctaHref: 'mailto:hello@acgs.ai'
		}
	];
</script>

<svelte:head>
	<title>Pricing — ACGS</title>
</svelte:head>

<section class="py-24 md:py-32 px-8 md:px-12 relative overflow-hidden grid-mesh">
	<!-- 3D Hero Element -->
	<div class="absolute inset-0 z-0 opacity-40 pointer-events-none">
		<Canvas>
			<TrustCrystal />
		</Canvas>
	</div>

	<div class="mx-auto max-w-[1600px] relative z-10">
		<div class="fade-in mb-24 text-center md:text-left" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.4em] text-accent font-bold uppercase">03 — PRICING</p>
			<h1 class="font-sans text-6xl font-bold tracking-tight md:text-9xl text-white">The Engine Is <span class="font-serif italic font-light">Free Forever</span></h1>
			<p class="mt-8 max-w-2xl text-lg leading-relaxed text-fg-muted md:text-xl font-light mx-auto md:mx-0">
				You pay for compliance proof, not governance.<br />
				Enterprise compliance consulting: <span class="text-white">$50,000+/engagement</span>.
			</p>
		</div>

		<div class="fade-in mt-16 grid gap-6 md:grid-cols-2 xl:grid-cols-4" use:observe>
				{#each tiers as tier (tier.name)}
				<div
					class="relative flex flex-col rounded-2xl border bg-[#0a0a0a] p-10 transition-all duration-300 hover:shadow-2xl hover:-translate-y-1
					{tier.highlight
						? 'border-accent shadow-[0_0_40px_rgba(37,99,235,0.15)] ring-1 ring-accent'
						: 'border-border/50 hover:border-border'}"
				>
					{#if tier.highlight}
						<div
							class="absolute -top-4 left-1/2 -translate-x-1/2 rounded-full bg-accent px-4 py-1 font-mono text-[11px] font-medium tracking-widest text-white shadow-lg shadow-accent/30"
						>
							POPULAR
						</div>
					{/if}

					<div
						class="font-mono text-xs tracking-widest {tier.highlight
							? 'text-accent'
							: 'text-fg-muted'}"
					>
						{tier.name.toUpperCase()}
					</div>

					<div class="mt-6 flex items-baseline gap-1">
						<span class="font-sans text-5xl font-light tracking-tight text-white">{tier.price}</span
						>
						{#if tier.period}
							<span class="font-mono text-sm text-fg-dim">{tier.period}</span>
						{/if}
					</div>

					<p class="mt-4 text-sm leading-relaxed text-fg-muted/90">{tier.desc}</p>

						{#if tier.ctaHref === 'https://pypi.org/project/acgs/'}
							<a
								href="https://pypi.org/project/acgs/"
								target="_blank"
								rel="noopener"
								class="mt-10 block w-full rounded-lg border py-3.5 text-center font-mono text-sm tracking-wider transition-all duration-300
									{tier.highlight
									? 'border-accent bg-accent text-white hover:bg-white hover:text-black hover:border-white shadow-lg shadow-accent/20'
									: 'border-border/60 bg-transparent text-fg hover:bg-white/10 hover:border-white/20'}"
							>
								{tier.cta}
							</a>
						{:else if tier.ctaHref === 'mailto:hello@acgs.ai'}
							<a
								href="mailto:hello@acgs.ai"
								class="mt-10 block w-full rounded-lg border py-3.5 text-center font-mono text-sm tracking-wider transition-all duration-300
									{tier.highlight
									? 'border-accent bg-accent text-white hover:bg-white hover:text-black hover:border-white shadow-lg shadow-accent/20'
									: 'border-border/60 bg-transparent text-fg hover:bg-white/10 hover:border-white/20'}"
							>
								{tier.cta}
							</a>
						{:else}
							<a
								href="#"
								class="mt-10 block w-full rounded-lg border py-3.5 text-center font-mono text-sm tracking-wider transition-all duration-300
									{tier.highlight
									? 'border-accent bg-accent text-white hover:bg-white hover:text-black hover:border-white shadow-lg shadow-accent/20'
									: 'border-border/60 bg-transparent text-fg hover:bg-white/10 hover:border-white/20'}"
							>
								{tier.cta}
							</a>
						{/if}

					<div class="mt-10 border-t border-border/30 pt-8 flex-grow">
						<ul class="space-y-4">
								{#each tier.items as item (item)}
								<li class="flex items-start gap-3 text-sm text-fg-muted">
									<svg
										class="mt-0.5 h-4 w-4 shrink-0 {tier.highlight ? 'text-accent' : 'text-fg-dim'}"
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
									>
										<path
											fill-rule="evenodd"
											d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
											clip-rule="evenodd"
										/>
									</svg>
									{item}
								</li>
							{/each}
						</ul>
					</div>
				</div>
			{/each}
		</div>

		<div class="mt-20 border-t border-border/30 pt-10 text-center">
			<p class="font-mono text-xs tracking-wider text-fg-dim">
				All prices in USD. Annual billing: save 15%.
			</p>
		</div>
	</div>
</section>
