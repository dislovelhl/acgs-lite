<script lang="ts">
	function observe(node: HTMLElement) {
		const observer = new IntersectionObserver(
			(entries) => { entries.forEach((e) => { if (e.isIntersecting) node.classList.add('visible'); }); },
			{ threshold: 0.15 }
		);
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	}

	const tiers = [
		{ name: 'Community', price: 'Free', period: 'forever', desc: 'Full engine, local audit, MACI separation of powers.', items: ['Complete governance engine', 'YAML + code-first rules', 'MACI separation of powers', 'Local tamper-evident audit trail', 'All 11 platform integrations', 'Optional Rust acceleration', 'Community support (GitHub)'], cta: 'pip install acgs', ctaHref: 'https://pypi.org/project/acgs/' },
		{ name: 'Pro', price: '$299', period: '/month', desc: 'Compliance reports, cloud audit, 3 regulatory frameworks.', items: ['Everything in Community', '1M validations/month', '3 compliance frameworks (choose from 9)', 'EU AI Act Article 12 audit logger', 'Risk classification engine', 'Compliance gap report (PDF/JSON)', 'Cloud audit sync (30-day retention)', 'Email support (48h SLA)'], cta: 'Start free trial', ctaHref: '#', highlight: true },
		{ name: 'Team', price: '$999', period: '/month', desc: 'All 9 frameworks, SSO, multi-constitution management.', items: ['Everything in Pro', '10M validations/month', 'All 9 compliance frameworks', 'EU AI Act Articles 12, 13 & 14', 'Multi-constitution (dev/staging/prod)', 'Constitutional change approval workflow', 'Cloud audit (1-year retention)', 'SSO (SAML/OIDC)', 'Priority support (4h SLA)'], cta: 'Start free trial', ctaHref: '#' },
		{ name: 'Enterprise', price: 'Custom', period: '', desc: 'On-prem, unlimited, dedicated compliance engineer.', items: ['Everything in Team', 'Unlimited validations', 'Custom regulatory frameworks', 'On-premise / VPC deployment', '560ns P50 SLA (Rust backend)', 'Dedicated compliance engineer', 'Quarterly constitutional review', 'Audit integration (Splunk, Datadog, ELK)', '99.99% uptime SLA', 'Dedicated support (1h SLA)'], cta: 'Contact sales', ctaHref: 'mailto:hello@acgs.ai' },
	];
</script>

<svelte:head>
	<title>Pricing — ACGS</title>
</svelte:head>

<nav class="border-b border-border px-6 py-4 md:px-12 md:py-5">
	<div class="flex items-center justify-between">
		<a href="/" class="group flex items-center gap-2">
			<span class="font-mono text-xs tracking-widest text-fg-muted">ACGS</span>
			<span class="h-1.5 w-1.5 rounded-full bg-accent transition-transform duration-300 group-hover:scale-150"></span>
		</a>
		<a href="/" class="font-mono text-xs tracking-wider text-fg-muted transition-colors hover:text-fg">&larr; BACK</a>
	</div>
</nav>

<section class="px-8 py-24 md:px-12">
	<div class="fade-in" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">PRICING</p>
		<h1 class="font-sans text-3xl font-light italic md:text-5xl">The Engine Is Free Forever</h1>
		<p class="mt-4 max-w-xl text-sm leading-relaxed text-fg-muted">
			You pay for compliance proof, not governance.
			Enterprise compliance consulting: $50,000+/engagement.
		</p>
	</div>

	<div class="fade-in mt-16 grid gap-px border border-border bg-border md:grid-cols-4" use:observe>
		{#each tiers as tier}
			<div class="relative bg-bg p-8 {tier.highlight ? 'ring-1 ring-accent ring-inset' : ''}">
				{#if tier.highlight}
					<div class="absolute -top-px left-0 right-0 h-px bg-accent"></div>
					<div class="absolute -top-6 left-1/2 -translate-x-1/2 rounded-full bg-accent px-3 py-0.5 font-mono text-[10px] tracking-wider text-white">POPULAR</div>
				{/if}
				<div class="font-mono text-[10px] tracking-widest text-fg-muted">{tier.name.toUpperCase()}</div>
				<div class="mt-3 flex items-baseline gap-1">
					<span class="font-sans text-3xl font-light">{tier.price}</span>
					{#if tier.period}
						<span class="font-mono text-xs text-fg-dim">{tier.period}</span>
					{/if}
				</div>
				<p class="mt-2 text-xs text-fg-dim">{tier.desc}</p>

				<a
					href={tier.ctaHref}
					target={tier.ctaHref.startsWith('http') ? '_blank' : undefined}
					rel={tier.ctaHref.startsWith('http') ? 'noopener' : undefined}
					class="mt-6 block w-full rounded border py-2.5 text-center font-mono text-xs tracking-wider transition-colors duration-300
						{tier.highlight
							? 'border-accent bg-accent text-white hover:bg-accent/80'
							: 'border-border text-fg-muted hover:border-fg-muted hover:text-fg'}"
				>
					{tier.cta}
				</a>

				<ul class="mt-8 space-y-3">
					{#each tier.items as item}
						<li class="flex items-start gap-2 text-xs text-fg-muted">
							<span class="mt-0.5 text-accent">+</span>
							{item}
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>

	<p class="mt-12 text-center font-mono text-xs text-fg-dim">
		All prices in USD. Annual billing: save 15%.
	</p>
</section>
