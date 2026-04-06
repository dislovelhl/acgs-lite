import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	test: {
		environment: 'jsdom',
		setupFiles: ['vitest-webgl-canvas-mock'],
		globals: true,
		include: ['src/**/*.{test,spec}.{js,ts}']
	},
	resolve: {
		conditions: process.env.VITEST ? ['browser'] : undefined
	}
});
