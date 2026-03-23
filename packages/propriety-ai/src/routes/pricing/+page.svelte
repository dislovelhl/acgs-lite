<script lang="ts">
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
				'All 11 platform integrations',
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
				'3 compliance frameworks (choose from 9)',
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
				'All 9 compliance frameworks',
				'EU AI Act Articles 12, 13 & 14',
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
				'Custom regulatory frameworks',
				'On-premise / VPC deployment',
				'560ns P50 SLA (Rust backend)',
				'Dedicated compliance engineer',
				'Quarterly constitutional review',
				'Audit integration (Splunk, Datadog, ELK)',
				'99.99% uptime SLA',
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

<section class="py-24 md:py-32 px-8 md:px-12 relative overflow-hidden">
	<!-- Subtle background glow -->
	<div
		class="pointer-events-none absolute top-0 right-0 -mr-40 -mt-40 h-[600px] w-[600px] rounded-full opacity-10 blur-[100px]"
		style="background: radial-gradient(circle, var(--color-accent) 0%, transparent 70%);"
	></div>

	<div class="mx-auto max-w-[1600px] relative z-10">
		<div class="fade-in mb-16 text-center md:text-left" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-accent">PRICING</p>
			<h1 class="font-sans text-5xl font-light italic md:text-7xl">The Engine Is Free Forever</h1>
			<p class="mt-6 max-w-2xl text-lg leading-relaxed text-fg-muted/90 mx-auto md:mx-0">
				You pay for compliance proof, not governance.<br />
				Enterprise compliance consulting: $50,000+/engagement.
			</p>
		</div>

		<div class="fade-in mt-16 grid gap-6 md:grid-cols-2 xl:grid-cols-4" use:observe>
			{#each tiers as tier}
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

					<a
						href={tier.ctaHref}
						target={tier.ctaHref.startsWith('http') ? '_blank' : undefined}
						rel={tier.ctaHref.startsWith('http') ? 'noopener' : undefined}
						class="mt-10 block w-full rounded-lg border py-3.5 text-center font-mono text-sm tracking-wider transition-all duration-300
							{tier.highlight
							? 'border-accent bg-accent text-white hover:bg-white hover:text-black hover:border-white shadow-lg shadow-accent/20'
							: 'border-border/60 bg-transparent text-fg hover:bg-white/10 hover:border-white/20'}"
					>
						{tier.cta}
					</a>

					<div class="mt-10 border-t border-border/30 pt-8 flex-grow">
						<ul class="space-y-4">
							{#each tier.items as item}
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
