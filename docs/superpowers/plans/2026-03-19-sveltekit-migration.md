# SvelteKit Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the `propriety-ai` dashboard to a SvelteKit SPA within the monorepo's `packages/` directory.

**Architecture:** Svelte 5, SvelteKit (Static Adapter for SPA fallback), Tailwind CSS v4, Bits UI, `@xyflow/svelte`.

**Tech Stack:** Svelte, Vite, TypeScript, Playwright, Vitest.

---

### Task 1: Rename Legacy Directory

**Files:**
- Modify: `propriety-ai/` -> `propriety-ai-legacy/`

- [ ] **Step 1: Rename the folder**

Run: `mv propriety-ai propriety-ai-legacy`
Expected: Folder is renamed.

- [ ] **Step 2: Commit the change**
Note: Since it is ignored in git, there may be no git change, but we ensure our workspace is clean.

```bash
git commit --allow-empty -m "chore: prepare for sveltekit migration by renaming legacy directory"
```

### Task 2: Scaffold SvelteKit App

**Files:**
- Create: `packages/propriety-ai/...`

- [ ] **Step 1: Scaffold using the new Svelte CLI (`sv`)**

Run:
```bash
mkdir -p packages
cd packages
npx sv create propriety-ai --template minimal --types ts --style tailwind --no-add-on
```
(Follow prompts if any, or run the equivalent non-interactive `npx sv create propriety-ai ...`)
Actually, the `sv create` command can be non-interactive.

- [ ] **Step 2: Install dependencies**

Run:
```bash
cd packages/propriety-ai
npm install
```

- [ ] **Step 3: Setup Static Adapter for SPA**

Install adapter: `npm i -D @sveltejs/adapter-static`

Edit `svelte.config.js`:
```javascript
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: 'index.html'
    })
  }
};
export default config;
```

- [ ] **Step 4: Commit the scaffold**

```bash
git add packages/propriety-ai
git commit -m "build: scaffold sveltekit app in packages/propriety-ai"
```

### Task 3: Install Ecosystem Dependencies

**Files:**
- Modify: `packages/propriety-ai/package.json`

- [ ] **Step 1: Install Svelte-specific libraries**

Run:
```bash
cd packages/propriety-ai
npm install @xyflow/svelte layerchart lucide-svelte bits-ui clsx tailwind-merge d3
npm install -D @types/d3
```

- [ ] **Step 2: Commit dependencies**

```bash
git add packages/propriety-ai/package.json packages/propriety-ai/package-lock.json
git commit -m "build: add svelte ui and flow dependencies"
```

### Task 4: Update Gitignore and Monorepo Integration

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Update `.gitignore`**

Open `.gitignore` at the root and remove `propriety-ai/` from the `# Frontend build artifacts` section.
Add SvelteKit ignores:
```gitignore
packages/propriety-ai/.svelte-kit
packages/propriety-ai/build
packages/propriety-ai/node_modules
```

- [ ] **Step 2: Verify git status**

Run: `git status`
Expected: `packages/propriety-ai` is correctly tracked (excluding build artifacts).

- [ ] **Step 3: Commit `.gitignore` changes**

```bash
git add .gitignore
git commit -m "build: integrate packages/propriety-ai into monorepo tracking"
```

### Task 5: Setup Basic Layout and Routing

**Files:**
- Create: `packages/propriety-ai/src/routes/+layout.svelte`
- Modify: `packages/propriety-ai/src/routes/+page.svelte`
- Create: `packages/propriety-ai/tests/routing.test.ts`

- [ ] **Step 1: Create a basic Vitest routing test**

Since SvelteKit scaffold doesn't include Vitest by default with `--no-add-on`, install it:
`npm install -D vitest @testing-library/svelte jsdom`

Create `packages/propriety-ai/vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte({ hot: !process.env.VITEST })],
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
```

Create `packages/propriety-ai/src/routes/page.test.ts`:
```typescript
import { render } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import Page from './+page.svelte';

describe('Home Page', () => {
  it('renders the dashboard title', () => {
    const { getByText } = render(Page);
    expect(getByText('ACGS Dashboard')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test (expect fail)**
Run: `npx vitest run`
Expected: Fails because the title is missing.

- [ ] **Step 3: Implement Layout and Page**

In `packages/propriety-ai/src/routes/+layout.svelte`:
```svelte
<script>
  import '../app.css';
  let { children } = $props();
</script>

<main class="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <div class="p-4">
    {@render children()}
  </div>
</main>
```

In `packages/propriety-ai/src/routes/+page.svelte`:
```svelte
<h1 class="text-2xl font-bold">ACGS Dashboard</h1>
<p>SvelteKit migration successful.</p>
```

- [ ] **Step 4: Run test (expect pass)**
Run: `npx vitest run`
Expected: PASS

- [ ] **Step 5: Commit Layout**
```bash
git add packages/propriety-ai
git commit -m "feat(ui): add base layout and home page with tests"
```
