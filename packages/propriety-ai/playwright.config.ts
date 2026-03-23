import { defineConfig } from '@playwright/test';

export default defineConfig({
	webServer: { command: 'env -u NO_COLOR npm run build && env -u NO_COLOR npm run preview', port: 4173 },
	testMatch: '**/*.e2e.{ts,js}'
});
