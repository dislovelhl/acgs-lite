# acgs.ai

SvelteKit frontend for the ACGS public site and interactive product surfaces.

## What Lives Here

`packages/acgs.ai` is the tracked frontend package for the ACGS web experience. It currently
ships:

- the public landing page at `/`
- the pricing page at `/pricing`
- the resources page at `/resources`
- the demo launcher at `/demo`
- the Playwright-backed demo route at `/demo/playwright`

The package is built with SvelteKit, Svelte 5, Tailwind CSS v4, Playwright, and Vitest.

## Running Locally

```bash
cd packages/acgs.ai
npm install
npm run dev
```

Default dev server: `http://localhost:5173`

## Core Scripts

```bash
npm run dev
npm run build
npm run preview
npm run check
npm run lint
npm run test:unit
npm run test:e2e
npm run test
```

`npm run test` runs both unit tests and Playwright end-to-end coverage.

## Route Map

| Route | Purpose |
| --- | --- |
| `/` | Main landing page for ACGS positioning, compliance coverage, and product overview |
| `/pricing` | Four-tier pricing surface (`Community`, `Starter`, `Pro`, `Enterprise`) |
| `/resources` | Download hub for videos and presentation assets |
| `/demo` | Demo landing page with launcher CTA |
| `/demo/playwright` | Interactive demo/testing route used by Playwright coverage |

## Frontend Stack

- **Framework:** SvelteKit with static adapter
- **UI:** Svelte 5, Tailwind CSS v4, Bits UI
- **Visuals:** Threlte / Three.js for hero visuals
- **Testing:** Vitest + Playwright
- **Charts / diagrams:** D3, LayerChart, XYFlow

## Key Files

| Path | Role |
| --- | --- |
| `src/routes/+page.svelte` | Main landing page |
| `src/routes/pricing/+page.svelte` | Pricing page |
| `src/routes/resources/+page.svelte` | Resources page |
| `src/routes/demo/+page.svelte` | Demo launcher |
| `src/routes/demo/playwright/+page.svelte` | Playwright demo surface |
| `src/routes/+layout.svelte` | Shared shell, navigation, and footer |
| `src/routes/page.test.ts` | Route-level unit coverage |
| `playwright.config.ts` | E2E configuration |

## Related Docs

- [Repo docs index](../../docs/README.md)
- [Repo directory map](../../docs/repo-map.md)
- [Autonoma landing-site flows](../../autonoma/AUTONOMA.md)
- [SvelteKit migration plan](../../docs/superpowers/plans/2026-03-19-sveltekit-migration.md)
- [SvelteKit migration design](../../docs/superpowers/specs/2026-03-19-sveltekit-migration-design.md)
