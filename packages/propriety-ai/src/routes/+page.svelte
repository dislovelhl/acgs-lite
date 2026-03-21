<script lang="ts">
	import { onMount } from 'svelte';

	const daysUntil = Math.ceil(
		(new Date('2026-08-02').getTime() - Date.now()) / (1000 * 60 * 60 * 24)
	);

	// Intersection observer for scroll animations
	function observe(node: HTMLElement) {
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

	// Live clock
	let time = $state('');
	onMount(() => {
		const tick = () => {
			const now = new Date();
			time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
		};
		tick();
		const iv = setInterval(tick, 1000);
		return () => clearInterval(iv);
	});

	// Scroll state for nav
	let scrolled = $state(false);
	onMount(() => {
		const handler = () => { scrolled = window.scrollY > 50; };
		window.addEventListener('scroll', handler, { passive: true });
		return () => window.removeEventListener('scroll', handler);
	});

	const frameworks = [
		{ name: 'EU AI Act', jurisdiction: 'EU (27 states)', penalty: '7% global revenue', coverage: '5/9', hot: true },
		{ name: 'GDPR Art. 22', jurisdiction: 'EU', penalty: '4% global revenue', coverage: '10/12', hot: false },
		{ name: 'NIST AI RMF', jurisdiction: 'US (federal)', penalty: 'Procurement gate', coverage: '7/16', hot: false },
		{ name: 'SOC 2 + AI', jurisdiction: 'International', penalty: 'Lost contracts', coverage: '10/16', hot: false },
		{ name: 'ISO/IEC 42001', jurisdiction: 'International', penalty: 'Audit failure', coverage: '9/18', hot: false },
		{ name: 'HIPAA + AI', jurisdiction: 'US (healthcare)', penalty: '$1.5M/violation', coverage: '9/15', hot: false },
		{ name: 'ECOA/FCRA', jurisdiction: 'US (finance)', penalty: 'Unlimited damages', coverage: '6/12', hot: false },
		{ name: 'NYC LL 144', jurisdiction: 'New York City', penalty: '$1,500/day', coverage: '6/12', hot: false },
		{ name: 'OECD AI', jurisdiction: '46 countries', penalty: 'Baseline standard', coverage: '10/15', hot: false },
	];

	const marqueeTop = [
		'EU AI ACT', 'NIST AI RMF', 'ISO 42001', 'GDPR', 'SOC 2', 'HIPAA',
		'ECOA/FCRA', 'NYC LL 144', 'OECD AI', 'MACI', 'AUDIT CHAIN', 'CONSTITUTIONAL HASH',
	];
	const marqueeBottom = [
		'OPENAI', 'ANTHROPIC', 'LANGCHAIN', 'LITELLM', 'GOOGLE GENAI', 'LLAMAINDEX',
		'AUTOGEN', 'CREWAI', 'MCP', 'A2A', 'GITLAB CI/CD', 'RUST ACCELERATION',
	];

	function copyInstall() {
		navigator.clipboard.writeText('pip install acgs');
	}
</script>

<svelte:head>
	<title>ACGS — HTTPS for AI</title>
</svelte:head>

<!-- ─── NAV ─── -->
<header
	class="fixed top-0 left-0 right-0 z-50 transition-all duration-500
		{scrolled ? 'bg-bg/80 backdrop-blur-md border-b border-border' : ''}"
>
	<nav class="flex items-center justify-between px-6 py-4 md:px-12 md:py-5">
		<a href="/" class="group flex items-center gap-2">
			<span class="font-mono text-xs tracking-widest text-fg-muted">ACGS</span>
			<span class="h-1.5 w-1.5 rounded-full bg-accent transition-transform duration-300 group-hover:scale-150"></span>
		</a>

		<ul class="hidden items-center gap-8 md:flex">
			{#each [['Frameworks', '#frameworks'], ['How It Works', '#works'], ['Pricing', '/pricing']] as [label, href], i}
				<li>
					<a {href} class="group relative font-mono text-xs tracking-wider text-fg-muted transition-colors duration-300 hover:text-fg">
						<span class="mr-1 text-accent">0{i + 1}</span>
						{label.toUpperCase()}
						<span class="absolute -bottom-1 left-0 h-px w-0 bg-fg transition-all duration-300 group-hover:w-full"></span>
					</a>
				</li>
			{/each}
		</ul>

		<div class="hidden items-center gap-3 md:flex">
			<span class="relative flex h-2 w-2">
				<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber opacity-75"></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-amber"></span>
			</span>
			<span class="font-mono text-xs tracking-wider text-fg-muted">{daysUntil} DAYS TO EU AI ACT</span>
		</div>
	</nav>
</header>

<!-- ─── HERO ─── -->
<section class="relative flex h-screen w-full flex-col justify-between overflow-hidden p-8 md:p-12 md:py-20">
	<!-- Ambient glow -->
	<div class="pointer-events-none absolute inset-0">
		<div
			class="absolute left-1/2 top-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-20"
			style="background: radial-gradient(circle, {`var(--color-accent-glow)`} 0%, transparent 70%); animation: sphere-drift 20s ease-in-out infinite;"
		></div>
	</div>

	<!-- Top left -->
	<div class="fade-in relative z-10" use:observe>
		<p class="mb-2 font-mono text-xs tracking-[0.3em] text-fg-muted">01 — GOVERNANCE</p>
		<h2 class="font-sans text-4xl font-light tracking-tight md:text-6xl lg:text-7xl">
			HTTPS
			<br />
			<span class="italic">for AI</span>
		</h2>
	</div>

	<!-- Center CTA -->
	<div class="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2">
		<button
			onclick={copyInstall}
			class="group relative rounded-full border border-white/20 bg-transparent px-8 py-4 font-mono text-sm tracking-widest uppercase backdrop-blur-sm transition-colors duration-500 hover:bg-fg hover:text-bg"
		>
			pip install acgs
			<span class="absolute -right-1 -top-1 h-2 w-2 animate-pulse rounded-full bg-accent"></span>
		</button>
	</div>

	<!-- Bottom right -->
	<div class="fade-in relative z-10 self-end text-right" use:observe>
		<p class="mb-2 font-mono text-xs tracking-[0.3em] text-fg-muted">02 — COMPLIANCE</p>
		<h2 class="font-sans text-4xl font-light tracking-tight md:text-6xl lg:text-7xl">
			NINE
			<br />
			<span class="italic">Frameworks</span>
		</h2>
	</div>

	<!-- Scroll indicator -->
	<div class="absolute bottom-8 left-1/2 z-10 -translate-x-1/2">
		<div class="flex flex-col items-center gap-2">
			<span class="font-mono text-[10px] uppercase tracking-widest text-fg-muted">Scroll</span>
			<div class="h-8 w-px bg-gradient-to-b from-white/50 to-transparent"></div>
		</div>
	</div>
</section>

<!-- ─── BLEND ─── -->
<div class="pointer-events-none relative z-10 -mt-20 h-40">
	<div class="absolute inset-0 h-1/2" style="background: linear-gradient(to bottom, transparent, #050505)"></div>
	<div class="absolute inset-0 top-1/2 h-1/2" style="background: linear-gradient(to bottom, #050505, transparent)"></div>
</div>

<!-- ─── PROBLEM ─── -->
<section class="relative overflow-hidden py-20 md:py-0">
	<div class="fade-in mb-0 px-8 py-20 md:px-12" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">03 — THE PROBLEM</p>
		<h2 class="font-sans text-3xl font-light italic md:text-5xl">The Missing Layer</h2>
	</div>

	<!-- Horizontal scroll statements -->
	<div class="relative flex h-16 items-center gap-0 overflow-hidden py-0">
		<div class="animate-marquee-left flex gap-16 whitespace-nowrap px-8 md:gap-24 md:px-12" style="width: fit-content;">
			{#each ['Most AI deployments have zero governance.', 'EU AI Act: 7% of global revenue.', 'No audit trail. No appeal. No accountability.', 'Deployment without governance is uninsurable.', 'Most AI deployments have zero governance.', 'EU AI Act: 7% of global revenue.', 'No audit trail. No appeal. No accountability.', 'Deployment without governance is uninsurable.'] as statement, i}
				<p
					class="font-sans text-4xl font-light tracking-tight md:text-6xl lg:text-7xl"
					style="{i % 2 === 0 ? 'color: rgba(255,255,255,0.9)' : `-webkit-text-stroke: 1px rgba(255,255,255,0.3); color: transparent`}"
				>
					{statement}
				</p>
			{/each}
		</div>
	</div>

	<div class="gradient-line mx-8 mt-16 md:mx-12"></div>
</section>

<!-- ─── CODE ─── -->
<section id="works" class="relative px-8 py-32 md:px-12 md:py-24">
	<div class="fade-in mb-24" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">04 — HOW IT WORKS</p>
		<h2 class="font-sans text-3xl font-light italic md:text-5xl">Five Lines of Code</h2>
	</div>

	<!-- Code steps as project list -->
	<div>
		{#each [
			{ step: 'Define', title: 'Constitution', code: `rules:\n  - id: SAFE-001\n    text: No financial advice\n    severity: critical\n    keywords: [invest, buy stocks]`, tag: 'YAML' },
			{ step: 'Govern', title: 'Your Agent', code: `from acgs import Constitution, GovernedAgent\n\nconstitution = Constitution.from_yaml("rules.yaml")\nagent = GovernedAgent(my_agent, constitution=constitution)\nresult = agent.run("process this request")`, tag: 'PYTHON' },
			{ step: 'Audit', title: 'Every Decision', code: `ALLOW  "check weather"       hash: a3f8..c291\nDENY   "invest in crypto"    rule: SAFE-001\n                              hash: b7e2..d104`, tag: 'OUTPUT' },
		] as item, i}
			<div class="fade-in border-t border-border py-8 md:py-12" use:observe>
				<div class="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
					<div class="flex-1">
						<span class="font-mono text-xs tracking-widest text-fg-muted">{item.step.toUpperCase()}</span>
						<h3 class="mt-2 font-sans text-4xl font-light tracking-tight md:text-6xl lg:text-7xl">
							{item.title}
						</h3>
					</div>
					<div class="w-full md:w-1/2">
						<div class="flex items-center justify-between border-b border-border px-4 py-2">
							<span class="font-mono text-[10px] tracking-wider text-fg-muted">{item.tag}</span>
							<span class="font-mono text-[10px] tracking-wider text-fg-dim">0{i + 1}</span>
						</div>
						<pre class="overflow-x-auto bg-bg-card p-4 font-mono text-xs leading-relaxed text-fg/80">{item.code}</pre>
					</div>
				</div>
			</div>
		{/each}
		<div class="border-t border-border"></div>
	</div>
</section>

<!-- ─── COMPLIANCE RECEIPT ─── -->
<section class="relative px-8 py-24 md:px-12">
	<div class="fade-in" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">05 — VALUE</p>
		<h2 class="font-sans text-3xl font-light italic md:text-5xl">The Compliance Receipt</h2>
		<p class="mt-6 max-w-2xl text-sm leading-relaxed text-fg-muted">
			Every decision produces a verifiable, timestamped proof that your AI was constitutionally
			compliant — mapped to the specific regulatory article, with constitutional hash chain.
			Hand it to your auditor. Hand it to your regulator. It speaks for itself.
		</p>
	</div>

	<div class="mt-12 grid gap-px border border-border bg-border md:grid-cols-4">
		{#each [
			{ label: 'Validation', value: '560ns', sub: 'P50 latency' },
			{ label: 'Frameworks', value: '9', sub: 'regulatory bodies' },
			{ label: 'Tests', value: '3,133', sub: 'passing' },
			{ label: 'Checklist', value: '72/125', sub: 'auto-populated' },
		] as stat}
			<div class="bg-bg p-8 text-center">
				<div class="font-mono text-[10px] tracking-widest text-fg-muted">{stat.label.toUpperCase()}</div>
				<div class="mt-2 font-sans text-4xl font-light">{stat.value}</div>
				<div class="mt-1 font-mono text-[10px] text-fg-dim">{stat.sub}</div>
			</div>
		{/each}
	</div>
</section>

<!-- ─── FRAMEWORKS TABLE ─── -->
<section id="frameworks" class="relative px-8 py-32 md:px-12 md:py-24">
	<div class="fade-in mb-16" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">06 — REGULATORY COVERAGE</p>
		<h2 class="font-sans text-3xl font-light italic md:text-5xl">Nine Frameworks, One Library</h2>
	</div>

	<div class="fade-in overflow-x-auto" use:observe>
		<table class="w-full text-left">
			<thead>
				<tr class="border-b border-border font-mono text-[10px] tracking-widest text-fg-muted">
					<th class="pb-4 pr-6 font-medium">FRAMEWORK</th>
					<th class="pb-4 pr-6 font-medium">JURISDICTION</th>
					<th class="pb-4 pr-6 font-medium">PENALTY</th>
					<th class="pb-4 font-medium">COVERAGE</th>
				</tr>
			</thead>
			<tbody>
				{#each frameworks as fw}
					<tr class="group border-b border-border/50 transition-colors duration-300 hover:bg-white/[0.02]">
						<td class="py-4 pr-6 font-sans text-base font-light {fw.hot ? 'text-amber' : 'text-fg'}">
							{fw.name}
						</td>
						<td class="py-4 pr-6 font-mono text-xs text-fg-muted">{fw.jurisdiction}</td>
						<td class="py-4 pr-6 font-mono text-xs text-fg-muted">{fw.penalty}</td>
						<td class="py-4">
							<span class="rounded-full border border-accent/30 bg-accent-glow px-3 py-1 font-mono text-[10px] tracking-wider text-accent">
								{fw.coverage}
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<!-- ─── MARQUEE ─── -->
<section class="relative overflow-hidden py-24 md:py-32">
	<div class="fade-in mb-16 px-8 md:px-12" use:observe>
		<p class="font-mono text-xs tracking-[0.3em] text-fg-muted">07 — TECHNICAL ARSENAL</p>
	</div>

	<div class="space-y-4">
		<!-- Frameworks row -->
		<div class="relative overflow-hidden py-4">
			<div class="animate-marquee-left flex gap-8" style="width: fit-content;">
				{#each [...marqueeTop, ...marqueeTop, ...marqueeTop, ...marqueeTop] as item}
					<span
						class="cursor-default whitespace-nowrap font-sans text-5xl font-light tracking-tight transition-all duration-300 md:text-7xl lg:text-8xl"
						style="-webkit-text-stroke: 1px rgba(255,255,255,0.3); color: transparent;"
						onmouseenter={(e) => { const t = e.currentTarget; t.style.color = 'white'; t.style.webkitTextStroke = 'none'; }}
						onmouseleave={(e) => { const t = e.currentTarget; t.style.color = 'transparent'; t.style.webkitTextStroke = '1px rgba(255,255,255,0.3)'; }}
					>
						{item}<span class="mx-8 text-white/20">&bull;</span>
					</span>
				{/each}
			</div>
		</div>

		<!-- Integrations row -->
		<div class="relative overflow-hidden py-4">
			<div class="animate-marquee-right flex gap-8" style="width: fit-content;">
				{#each [...marqueeBottom, ...marqueeBottom, ...marqueeBottom, ...marqueeBottom] as item}
					<span
						class="cursor-default whitespace-nowrap font-sans text-5xl font-light tracking-tight transition-all duration-300 md:text-7xl lg:text-8xl"
						style="-webkit-text-stroke: 1px rgba(255,255,255,0.3); color: transparent;"
						onmouseenter={(e) => { const t = e.currentTarget; t.style.color = 'white'; t.style.webkitTextStroke = 'none'; }}
						onmouseleave={(e) => { const t = e.currentTarget; t.style.color = 'transparent'; t.style.webkitTextStroke = '1px rgba(255,255,255,0.3)'; }}
					>
						{item}<span class="mx-8 text-white/20">&bull;</span>
					</span>
				{/each}
			</div>
		</div>
	</div>
</section>

<!-- ─── FEATURES ─── -->
<section class="relative px-8 py-24 md:px-12">
	<div class="fade-in mb-16" use:observe>
		<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">08 — ARCHITECTURE</p>
		<h2 class="font-sans text-3xl font-light italic md:text-5xl">Constitutional Guarantees</h2>
	</div>

	<div class="grid gap-px border border-border bg-border md:grid-cols-2">
		{#each [
			{ title: 'MACI Separation of Powers', desc: 'Prove to regulators that no single agent controls decisions. Four roles with enforced boundaries. Self-validation prevention built in.' },
			{ title: 'Tamper-Evident Audit Chain', desc: 'Show your auditor exactly what your AI decided and why. SHA-256 chain verification. Constitutional hash: cdd01ef066bc6cf2.' },
			{ title: 'Zero Performance Impact', desc: 'Rule-based, not LLM-based. Aho-Corasick single-pass scanning. Optional Rust acceleration. Governance that vanishes into the critical path.' },
			{ title: 'Pass Your Next Audit', desc: '125 compliance checklist items. 72 auto-populated. Enterprise compliance consulting costs $50K+. ACGS: pip install.' },
		] as feature}
			<div class="fade-in bg-bg p-8 md:p-12" use:observe>
				<h3 class="font-sans text-xl font-light">{feature.title}</h3>
				<p class="mt-4 text-sm leading-relaxed text-fg-muted">{feature.desc}</p>
			</div>
		{/each}
	</div>
</section>

<!-- ─── PRICING TEASER ─── -->
<section id="pricing" class="relative px-8 py-24 md:px-12">
	<div class="fade-in flex flex-col items-center gap-6 text-center md:flex-row md:justify-between md:text-left" use:observe>
		<div>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">09 — PRICING</p>
			<h2 class="font-sans text-3xl font-light italic md:text-5xl">The Engine Is Free Forever</h2>
			<p class="mt-4 text-sm text-fg-muted">You pay for compliance proof. Not governance.</p>
		</div>
		<a
			href="/pricing"
			class="group inline-flex items-center gap-3 rounded-full border border-border px-8 py-4 font-mono text-sm tracking-widest uppercase transition-colors duration-500 hover:bg-fg hover:text-bg"
		>
			View pricing
			<svg class="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
		</a>
	</div>
</section>

<!-- ─── FOOTER CTA ─── -->
<footer class="relative">
	<a
		href="https://pypi.org/project/acgs/"
		target="_blank"
		rel="noopener"
		class="group relative block overflow-hidden border-t border-border"
	>
		<div class="absolute inset-0 translate-y-full bg-accent transition-transform duration-500 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] group-hover:translate-y-0"></div>
		<div class="relative flex flex-col items-center justify-between gap-8 px-8 py-16 transition-colors duration-300 md:flex-row md:px-12 md:py-24">
			<h2 class="font-sans text-4xl font-light tracking-tight group-hover:text-bg md:text-6xl lg:text-8xl">
				pip install <span class="italic">acgs</span>
			</h2>
			<svg class="h-12 w-12 transition-all duration-300 group-hover:rotate-45 group-hover:text-bg md:h-16 md:w-16" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M7 17L17 7M17 7H7M17 7v10" />
			</svg>
		</div>
	</a>

	<div class="flex flex-col items-center justify-between gap-4 border-t border-border px-8 py-8 md:flex-row md:px-12">
		<div class="font-mono text-xs tracking-widest text-fg-muted">
			<span class="mr-2">CONSTITUTIONAL HASH</span>
			<span class="tabular-nums text-fg">cdd01ef066bc6cf2</span>
		</div>
		<div class="flex gap-8">
			{#each [['PyPI', 'https://pypi.org/project/acgs/'], ['GitHub', 'https://github.com/acgs-ai/acgs-lite']] as [label, href]}
				<a {href} target="_blank" rel="noopener" class="font-mono text-xs tracking-widest text-fg-muted transition-colors duration-300 hover:text-fg">
					{label}
				</a>
			{/each}
		</div>
		<div class="font-mono text-xs tracking-widest text-fg-muted">
			<span class="mr-2">LOCAL TIME</span>
			<span class="tabular-nums text-fg">{time}</span>
		</div>
	</div>
</footer>
