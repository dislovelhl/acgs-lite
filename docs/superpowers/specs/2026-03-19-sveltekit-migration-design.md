# SvelteKit Migration Design

## Context
The `propriety-ai` dashboard currently exists as an untracked Vite/React SPA in the root directory. To align with modern practices, improve performance, and establish a clean codebase free of legacy Next.js remnants, we are migrating the frontend entirely to SvelteKit and integrating it formally into the ACGS monorepo under the `packages/` directory.

## Architecture

**Framework**: SvelteKit using Svelte 5.
**Adapter**: `@sveltejs/adapter-static` configured as a Single Page Application (SPA) with a fallback to `index.html`. This ensures compatibility with the existing Python backend APIs without requiring a Node.js runtime for the frontend server.
**Styling**: Tailwind CSS v4, maintaining the current design language but leveraging Svelte's native scoping and component styling.
**Repository Integration**:
  - The new project will live at `packages/propriety-ai`.
  - The old, untracked `propriety-ai/` directory will be renamed to `propriety-ai-legacy/` temporarily to serve as a side-by-side reference during the porting process.
  - The root `.gitignore` will be updated to stop ignoring `propriety-ai/` globally, ensuring `packages/propriety-ai/src/` is tracked, while SvelteKit build artifacts (`.svelte-kit/`, `build/`, `node_modules/`) are properly ignored.

## Components & Ecosystem

To replace React-specific libraries:
- **Graphs/Node Flows**: `@xyflow/svelte` will directly replace `@xyflow/react` for visualizing the MACI and Governance pipelines.
- **Charts**: `layerchart` (or `unovis`) integrated with D3 will replace `recharts` for rendering performance metrics and audit logs.
- **UI Primitives**: Headless UI components will be migrated to `bits-ui` (the Svelte equivalent to Radix UI).
- **Icons**: `lucide-svelte` will be used for icon consistency.

## Data Flow

- **Fetching**: SvelteKit's native `load` functions (`+page.ts` / `+layout.ts`) will handle data fetching from the existing ACGS backend endpoints.
- **State Management**: Svelte 5's rune-based reactivity (`$state`, `$derived`, `$effect`) will replace React's hooks (`useState`, `useEffect`, context) for managing local UI state, resulting in cleaner and more performant data flows without unnecessary re-renders.

## Error Handling & Testing

- **Testing**:
  - **E2E**: Playwright (standard SvelteKit default) for integration tests.
  - **Unit**: Vitest and `@testing-library/svelte` for component-level verification.
- **Error Boundaries**: SvelteKit's `+error.svelte` files will define strict routing boundaries to catch and gracefully display fetch failures or runtime errors within the dashboard.

## Next Steps

1. Rename the legacy untracked folder.
2. Scaffold SvelteKit in `packages/propriety-ai`.
3. Update `.gitignore` and commit the initial structure.
4. Begin incremental porting of UI components from the legacy React app to Svelte 5 syntax.
