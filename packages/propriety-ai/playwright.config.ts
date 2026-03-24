import { defineConfig } from '@playwright/test';

export default defineConfig({
	webServer: {
		command: 'env -u NO_COLOR npm run build && env -u NO_COLOR npm run preview',
		port: 4173
	},
	testMatch: '**/*.e2e.{ts,js}',
	projects: [
		{
			name: 'lightpanda',
			use: {
				connectOptions: {
					wsEndpoint: 'ws://127.0.0.1:9222'
				}
			}
		},
		{
			name: 'chromium',
			use: {
				browserName: 'chromium'
			}
		}
	]
});
