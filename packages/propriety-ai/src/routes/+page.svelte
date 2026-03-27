<script lang="ts">
	import { resolve } from '$app/paths';
	import { Canvas } from '@threlte/core';
	import TrustCrystal from '$lib/components/TrustCrystal.svelte';

	// Intersection observer for scroll animations
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

	const frameworks = [
		{
			name: 'EU AI Act',
			jurisdiction: 'EU (27 states)',
			penalty: '7% global revenue',
			coverage: '5/9',
			hot: true
		},
		{
			name: 'GDPR Art. 22',
			jurisdiction: 'EU',
			penalty: '4% global revenue',
			coverage: '10/12',
			hot: false
		},
		{
			name: 'NIST AI RMF',
			jurisdiction: 'US (federal)',
			penalty: 'Procurement gate',
			coverage: '7/16',
			hot: false
		},
		{
			name: 'SOC 2 + AI',
			jurisdiction: 'International',
			penalty: 'Lost contracts',
			coverage: '10/16',
			hot: false
		},
		{
			name: 'ISO/IEC 42001',
			jurisdiction: 'International',
			penalty: 'Audit failure',
			coverage: '9/18',
			hot: false
		},
		{
			name: 'HIPAA + AI',
			jurisdiction: 'US (healthcare)',
			penalty: '$1.5M/violation',
			coverage: '9/15',
			hot: false
		},
		{
			name: 'ECOA/FCRA',
			jurisdiction: 'US (finance)',
			penalty: 'Unlimited damages',
			coverage: '6/12',
			hot: false
		},
		{
			name: 'NYC LL 144',
			jurisdiction: 'New York City',
			penalty: '$1,500/day',
			coverage: '6/12',
			hot: false
		},
		{
			name: 'OECD AI',
			jurisdiction: '46 countries',
			penalty: 'Baseline standard',
			coverage: '10/15',
			hot: false
		}
	];

	const marqueeTop = [
		'EU AI ACT',
		'NIST AI RMF',
		'ISO 42001',
		'GDPR',
		'SOC 2',
		'HIPAA',
		'ECOA/FCRA',
		'NYC LL 144',
		'OECD AI',
		'MACI',
		'AUDIT CHAIN',
		'CONSTITUTIONAL HASH'
	];
	const marqueeBottom = [
		'OPENAI',
		'ANTHROPIC',
		'LANGCHAIN',
		'LITELLM',
		'GOOGLE GENAI',
		'LLAMAINDEX',
		'AUTOGEN',
		'CREWAI',
		'MCP',
		'A2A',
		'GITLAB CI/CD',
		'RUST ACCELERATION'
	];

	function copyInstall() {
		navigator.clipboard.writeText('pip install acgs');
	}
</script>

<svelte:head>
	<title>ACGS — HTTPS for AI</title>
</svelte:head>

<!-- ─── HERO ─── -->
<section
	class="relative flex h-[100vh] w-full flex-col items-center justify-center overflow-hidden px-8 md:px-12 grid-mesh"
>
	<!-- 3D Hero Element -->
	<div class="absolute inset-0 z-0 opacity-80 pointer-events-none">
		<Canvas>
			<TrustCrystal />
		</Canvas>
	</div>

	<div class="relative z-10 flex max-w-[1400px] flex-col items-center text-center">
		<div class="fade-in mb-10 inline-flex items-center gap-3 glass-accent px-5 py-2.5 rounded-full" use:observe>
			<span class="relative flex h-2 w-2">
				<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75"></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
			</span>
			<span class="font-mono text-[10px] tracking-[0.4em] text-accent uppercase font-medium">v2.4.0 — PROD READY</span>
		</div>

		<h1 class="fade-in font-sans text-7xl font-bold tracking-tight md:text-9xl lg:text-[11rem] leading-[0.85] text-white" use:observe>
			HTTPS<br />FOR <span class="font-serif italic font-light text-white/90">AI</span>
		</h1>

		<p class="fade-in mt-12 max-w-2xl text-lg leading-relaxed text-fg-muted md:text-xl font-light" use:observe>
			Constitutional governance infrastructure for AI agents. 
			<span class="text-white font-medium">1.1M RPS. 3.9µs P99.</span> 
			9 regulatory frameworks. Tamper-evident audit trails. 
			The missing safety layer between your LLM and production.
		</p>

		<div class="fade-in mt-14 flex flex-col gap-6 sm:flex-row items-center" use:observe>
			<button
				onclick={copyInstall}
				class="group relative overflow-hidden rounded-full bg-white px-12 py-5 font-mono text-xs tracking-[0.2em] font-bold text-black transition-all hover:scale-105 active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.2)]"
			>
				<span class="relative z-10">PIP INSTALL ACGS</span>
			</button>
			<a
				href={resolve('/resources')}
				class="group rounded-full border border-white/10 glass px-12 py-5 font-mono text-xs tracking-[0.2em] font-bold text-white transition-all hover:bg-white/5 hover:border-white/30"
			>
				EXPLORE RESOURCES
			</a>
		</div>
	</div>

	<!-- Scroll indicator -->
	<div class="absolute bottom-10 left-1/2 -translate-x-1/2 opacity-30">
		<div class="flex flex-col items-center gap-4">
			<span class="font-mono text-[9px] uppercase tracking-[0.5em] text-fg-muted">Scroll</span>
			<div class="h-16 w-px bg-gradient-to-b from-white to-transparent"></div>
		</div>
	</div>
</section>

<!-- ─── BLEND ─── -->
<div class="pointer-events-none relative z-10 -mt-20 h-40">
	<div
		class="absolute inset-0 h-1/2"
		style="background: linear-gradient(to bottom, transparent, #050505)"
	></div>
	<div
		class="absolute inset-0 top-1/2 h-1/2"
		style="background: linear-gradient(to bottom, #050505, transparent)"
	></div>
</div>

<!-- ─── PROBLEM ─── -->
<section class="relative overflow-hidden py-24 md:py-32">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-12 px-8 md:px-12" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">03 — THE PROBLEM</p>
			<h2 class="font-sans text-4xl font-light italic md:text-6xl">The Missing Layer</h2>
		</div>

		<!-- Horizontal scroll statements -->
		<div class="relative flex h-24 items-center gap-0 overflow-hidden">
			<div
				class="animate-marquee-left flex gap-16 whitespace-nowrap px-8 md:gap-24 md:px-12"
				style="width: fit-content;"
			>
					{#each ['Most AI deployments have zero governance.', 'EU AI Act: 7% of global revenue.', 'No audit trail. No appeal. No accountability.', 'Deployment without governance is uninsurable.', 'Most AI deployments have zero governance.', 'EU AI Act: 7% of global revenue.', 'No audit trail. No appeal. No accountability.', 'Deployment without governance is uninsurable.'] as statement, i (`${statement}-${i}`)}
					<p
						class="font-sans text-5xl font-light tracking-tight md:text-7xl lg:text-8xl"
						style={i % 2 === 0
							? 'color: rgba(255,255,255,0.95)'
							: '-webkit-text-stroke: 1px rgba(255,255,255,0.25); color: transparent'}
					>
						{statement}
					</p>
				{/each}
			</div>
		</div>

		<div class="gradient-line mx-8 mt-24 md:mx-12"></div>
	</div>
</section>

<!-- ─── CODE ─── -->
<section id="works" class="relative py-24 md:py-32 px-8 md:px-12">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-24" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">04 — HOW IT WORKS</p>
			<h2 class="font-sans text-4xl font-light italic md:text-6xl">Five Lines of Code</h2>
		</div>

		<!-- Code steps as project list -->
		<div class="flex flex-col gap-12">
				{#each [{ step: 'Define', title: 'Constitution', code: `rules:\n  - id: SAFE-001\n    text: No financial advice\n    severity: critical\n    keywords: [invest, buy stocks]`, tag: 'YAML' }, { step: 'Govern', title: 'Your Agent', code: `from acgs import Constitution, GovernedAgent\n\nconstitution = Constitution.from_yaml("rules.yaml")\nagent = GovernedAgent(my_agent, constitution=constitution)\nresult = agent.run("process this request")`, tag: 'PYTHON' }, { step: 'Audit', title: 'Every Decision', code: `ALLOW  "check weather"       hash: a3f8..c291\nDENY   "invest in crypto"    rule: SAFE-001\n                              hash: b7e2..d104`, tag: 'OUTPUT' }] as item (item.title)}
				<div class="fade-in border-t border-border/50 pt-12 md:pt-16" use:observe>
					<div class="flex flex-col gap-10 lg:flex-row lg:items-start lg:justify-between">
						<div class="flex-1 lg:max-w-md">
							<span class="font-mono text-xs tracking-widest text-fg-muted"
								>{item.step.toUpperCase()}</span
							>
							<h3 class="mt-4 font-sans text-5xl font-light tracking-tight md:text-6xl">
								{item.title}
							</h3>
						</div>
						<div class="w-full lg:w-7/12">
							<div
								class="rounded-xl border border-border/60 bg-[#0a0a0a] shadow-2xl overflow-hidden"
							>
								<div
									class="flex items-center justify-between border-b border-border/60 bg-black/40 px-5 py-3"
								>
									<div class="flex items-center gap-2">
										<div class="h-2.5 w-2.5 rounded-full bg-red/80"></div>
										<div class="h-2.5 w-2.5 rounded-full bg-amber/80"></div>
										<div class="h-2.5 w-2.5 rounded-full bg-emerald/80"></div>
									</div>
									<span class="font-mono text-[10px] tracking-wider text-fg-muted">{item.tag}</span>
								</div>
								<pre
									class="overflow-x-auto p-6 font-mono text-sm leading-relaxed text-fg/90">{item.code}</pre>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</section>

<!-- ─── VIDEO ─── -->
<section class="relative py-24 md:py-32 px-8 md:px-12">
	<div class="mx-auto max-w-[1000px]">
		<div class="fade-in mb-12 text-center" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">GOVERNANCE WATCH</p>
		</div>
		<div class="fade-in aspect-video w-full overflow-hidden rounded-xl border border-border/50 shadow-2xl" use:observe>
			<iframe
				src="https://www.youtube-nocookie.com/embed/uWacmC3CbYg"
				title="ACGS — Governance Watch & Constitutional AI"
				frameborder="0"
				allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
				allowfullscreen
				class="h-full w-full"
				loading="lazy"
			></iframe>
		</div>
	</div>
</section>

<!-- ─── COMPLIANCE RECEIPT ─── -->
<section class="relative py-24 md:py-32 px-8 md:px-12 bg-[#080808]">
	<div class="mx-auto max-w-[1400px]">
		<div
			class="fade-in flex flex-col md:flex-row md:items-end md:justify-between gap-8 mb-16"
			use:observe
		>
			<div class="max-w-xl">
				<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted uppercase">05 — VALUE</p>
				<h2 class="font-sans text-5xl font-bold md:text-7xl leading-tight">The Compliance <span class="font-serif italic font-light">Receipt</span></h2>
			</div>
			<p class="max-w-md text-base leading-relaxed text-fg-muted/90">
				Every decision produces a verifiable, timestamped proof that your AI was constitutionally
				compliant — mapped to the specific regulatory article, with constitutional hash chain.
			</p>
		</div>

		<div
			class="grid gap-px border border-border/50 bg-border/50 lg:grid-cols-4 rounded-xl overflow-hidden shadow-2xl"
		>
				{#each [{ label: 'Validation', value: '560ns', sub: 'P50 latency' }, { label: 'Frameworks', value: '9', sub: 'regulatory bodies' }, { label: 'Tests', value: '3,133', sub: 'passing' }, { label: 'Checklist', value: '72/125', sub: 'auto-populated' }] as stat (stat.label)}
				<div class="bg-[#0a0a0a] p-10 text-center transition-colors hover:bg-[#0c0c0c]">
					<div class="font-mono text-xs tracking-widest text-accent">
						{stat.label.toUpperCase()}
					</div>
					<div class="mt-4 font-sans text-5xl font-light tracking-tight text-white">
						{stat.value}
					</div>
					<div class="mt-3 font-mono text-[11px] uppercase tracking-wider text-fg-dim">
						{stat.sub}
					</div>
				</div>
			{/each}
		</div>
	</div>
</section>

<!-- ─── OBSERVABILITY ─── -->
<section id="observability" class="relative py-24 md:py-32 px-8 md:px-12 bg-[#050505]">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-16" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">06 — OBSERVABILITY</p>
			<h2 class="font-sans text-4xl font-light italic md:text-6xl">Governance Watch</h2>
		</div>

		<div class="grid gap-12 lg:grid-cols-2 lg:items-center">
			<div class="fade-in space-y-8" use:observe>
				<div class="space-y-4">
					<h3 class="font-sans text-3xl font-light text-white">Stop "Regex-Hell" Latency</h3>
					<p class="text-lg leading-relaxed text-fg-muted/90">
						Brittle Python scripts and 2-second regex checks kill production performance. 
						ACGS-2 moves validation to the edge with a WASM-backed engine that streams 
						telemetry in real-time.
					</p>
				</div>

				<div class="space-y-6">
					{#each [
						{ title: 'Live Stream', desc: 'acgs observe --watch: View governance decisions as they happen with microsecond precision.' },
						{ title: 'Portable Bundles', desc: 'Generate auditor-ready telemetry bundles containing Prometheus metrics and OTel traces.' },
						{ title: 'Fail-Closed Edge', desc: 'Deploy as a Cloudflare Worker proxy. Intercept jailbreaks at the edge before they hit your model.' }
					] as point (point.title)}
						<div class="flex gap-5">
							<div class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent shadow-[0_0_10px_rgba(37,99,235,0.5)]"></div>
							<div>
								<h4 class="font-mono text-sm font-medium text-white">{point.title}</h4>
								<p class="mt-1 text-sm text-fg-muted leading-relaxed">{point.desc}</p>
							</div>
						</div>
					{/each}
				</div>
			</div>

			<div class="fade-in" use:observe>
				<div class="rounded-xl border border-border/60 bg-[#0a0a0a] shadow-2xl overflow-hidden">
					<div class="flex items-center justify-between border-b border-border/60 bg-black/40 px-5 py-3">
						<div class="flex items-center gap-2">
							<div class="h-2.5 w-2.5 rounded-full bg-red/80"></div>
							<div class="h-2.5 w-2.5 rounded-full bg-amber/80"></div>
							<div class="h-2.5 w-2.5 rounded-full bg-emerald/80"></div>
						</div>
						<span class="font-mono text-[10px] tracking-wider text-fg-muted">TERMINAL</span>
					</div>
					<pre class="overflow-x-auto p-6 font-mono text-[13px] leading-relaxed text-fg/90">
$ acgs observe --watch --interval 1

--- Snapshot 1 ---
&#123;
  "total_decisions": 1142,
  "compliance_rate": 0.9982,
  "latency_p99_ms": 0.0039,
  "top_violation": "GL-004 (Destructive Ops)"
&#125;

<span class="text-accent animate-pulse">▋</span> Streaming telemetry to telemetry-bundle/</pre>
				</div>
			</div>
		</div>
	</div>
</section>

<!-- ─── FRAMEWORKS TABLE ─── -->
<section id="frameworks" class="relative py-24 md:py-32 px-8 md:px-12">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-16" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">07 — REGULATORY COVERAGE</p>
			<h2 class="font-sans text-4xl font-light italic md:text-6xl">Nine Frameworks, One Library</h2>
		</div>

		<div
			class="fade-in overflow-x-auto rounded-xl border border-border/50 bg-[#0a0a0a] p-1 shadow-2xl"
			use:observe
		>
			<table class="w-full text-left border-collapse">
				<thead>
					<tr class="font-mono text-[11px] tracking-widest text-fg-muted bg-black/40">
						<th class="py-5 pl-8 pr-6 font-medium uppercase border-b border-border/50">Framework</th
						>
						<th class="py-5 pr-6 font-medium uppercase border-b border-border/50">Jurisdiction</th>
						<th class="py-5 pr-6 font-medium uppercase border-b border-border/50">Penalty</th>
						<th class="py-5 pr-8 font-medium uppercase border-b border-border/50 text-right"
							>Coverage</th
						>
					</tr>
				</thead>
				<tbody>
						{#each frameworks as fw (fw.name)}
						<tr class="group transition-colors duration-300 hover:bg-white/[0.03]">
							<td
								class="py-5 pl-8 pr-6 font-sans text-lg font-light border-b border-border/20 {fw.hot
									? 'text-amber'
									: 'text-fg'}"
							>
								{fw.name}
							</td>
							<td class="py-5 pr-6 font-mono text-sm text-fg-muted border-b border-border/20"
								>{fw.jurisdiction}</td
							>
							<td class="py-5 pr-6 font-mono text-sm text-fg-muted border-b border-border/20"
								>{fw.penalty}</td
							>
							<td class="py-5 pr-8 border-b border-border/20 text-right">
								<span
									class="inline-flex rounded-full border border-accent/30 bg-accent/10 px-3 py-1 font-mono text-[11px] tracking-wider text-accent shadow-[0_0_10px_rgba(37,99,235,0.1)]"
								>
									{fw.coverage}
								</span>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</section>

<!-- ─── MARQUEE ─── -->
<section class="relative overflow-hidden py-24 md:py-32">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-16 px-8 md:px-12" use:observe>
			<p class="font-mono text-xs tracking-[0.3em] text-fg-muted">08 — TECHNICAL ARSENAL</p>
		</div>
	</div>

	<div class="space-y-6">
		<!-- Frameworks row -->
		<div class="relative overflow-hidden py-2">
			<div class="animate-marquee-left flex gap-12" style="width: fit-content;">
					{#each [...marqueeTop, ...marqueeTop, ...marqueeTop, ...marqueeTop] as item, i (`top-${item}-${i}`)}
					<span
						role="presentation"
						class="cursor-default whitespace-nowrap font-sans text-6xl font-light tracking-tight transition-all duration-300 md:text-8xl"
						style="-webkit-text-stroke: 1px rgba(255,255,255,0.2); color: transparent;"
						onmouseenter={(e) => {
							const t = e.currentTarget;
							t.style.color = 'white';
							t.style.webkitTextStroke = 'none';
						}}
						onmouseleave={(e) => {
							const t = e.currentTarget;
							t.style.color = 'transparent';
							t.style.webkitTextStroke = '1px rgba(255,255,255,0.2)';
						}}
					>
						{item}<span class="mx-12 text-white/10">&bull;</span>
					</span>
				{/each}
			</div>
		</div>

		<!-- Integrations row -->
		<div class="relative overflow-hidden py-2">
			<div class="animate-marquee-right flex gap-12" style="width: fit-content;">
					{#each [...marqueeBottom, ...marqueeBottom, ...marqueeBottom, ...marqueeBottom] as item, i (`bottom-${item}-${i}`)}
					<span
						role="presentation"
						class="cursor-default whitespace-nowrap font-sans text-6xl font-light tracking-tight transition-all duration-300 md:text-8xl"
						style="-webkit-text-stroke: 1px rgba(255,255,255,0.2); color: transparent;"
						onmouseenter={(e) => {
							const t = e.currentTarget;
							t.style.color = 'white';
							t.style.webkitTextStroke = 'none';
						}}
						onmouseleave={(e) => {
							const t = e.currentTarget;
							t.style.color = 'transparent';
							t.style.webkitTextStroke = '1px rgba(255,255,255,0.2)';
						}}
					>
						{item}<span class="mx-12 text-white/10">&bull;</span>
					</span>
				{/each}
			</div>
		</div>
	</div>
</section>

<!-- ─── FEATURES ─── -->
<section class="relative py-24 md:py-32 px-8 md:px-12 bg-[#080808]">
	<div class="mx-auto max-w-[1400px]">
		<div class="fade-in mb-16 text-center md:text-left" use:observe>
			<p class="mb-4 font-mono text-xs tracking-[0.3em] text-fg-muted">09 — ARCHITECTURE</p>
			<h2 class="font-sans text-4xl font-light italic md:text-6xl">Constitutional Guarantees</h2>
		</div>

		<div class="grid gap-6 md:grid-cols-2">
				{#each [{ title: 'MACI Separation of Powers', desc: 'Prove to regulators that no single agent controls decisions. Four roles with enforced boundaries. Self-validation prevention built in.' }, { title: 'Tamper-Evident Audit Chain', desc: 'Show your auditor exactly what your AI decided and why. SHA-256 chain verification. Constitutional hash: cdd01ef066bc6cf2.' }, { title: 'Zero Performance Impact', desc: 'Rule-based, not LLM-based. Aho-Corasick single-pass scanning. Optional Rust acceleration. Governance that vanishes into the critical path.' }, { title: 'Pass Your Next Audit', desc: '125 compliance checklist items. 72 auto-populated. Enterprise compliance consulting costs $50K+. ACGS: pip install.' }] as feature (feature.title)}
				<div
					class="fade-in group rounded-xl border border-border/50 bg-[#0a0a0a] p-10 transition-all duration-300 hover:bg-[#0f0f0f] hover:border-border hover:shadow-2xl"
					use:observe
				>
					<h3
						class="font-sans text-2xl font-light text-white group-hover:text-accent transition-colors"
					>
						{feature.title}
					</h3>
					<p class="mt-5 text-base leading-relaxed text-fg-muted/90">{feature.desc}</p>
				</div>
			{/each}
		</div>
	</div>
</section>

<!-- ─── PRICING TEASER ─── -->
<section id="pricing" class="relative py-24 md:py-32 px-8 md:px-12">
	<div class="mx-auto max-w-[1400px]">
		<div
			class="fade-in flex flex-col items-center gap-10 rounded-2xl border border-border/50 bg-gradient-to-b from-[#0a0a0a] to-[#050505] p-12 md:flex-row md:justify-between md:p-16 shadow-2xl"
			use:observe
		>
			<div class="text-center md:text-left">
				<p class="mb-4 font-mono text-xs tracking-[0.3em] text-accent">10 — PRICING</p>
				<h2 class="font-sans text-4xl font-light italic text-white md:text-6xl">
					The Engine Is Free Forever
				</h2>
				<p class="mt-5 text-lg text-fg-muted max-w-xl">
					You pay for compliance proof. Not governance.
				</p>
			</div>
				<a
					href={resolve('/pricing')}
					class="group relative overflow-hidden inline-flex items-center gap-4 rounded-full border border-border px-10 py-5 font-mono text-sm tracking-widest uppercase transition-all duration-500 hover:border-white hover:bg-white hover:text-black"
				>
				<span class="relative z-10">View pricing</span>
				<svg
					class="relative z-10 h-5 w-5 transition-transform duration-300 group-hover:translate-x-1"
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
					><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg
				>
			</a>
		</div>
	</div>
</section>
