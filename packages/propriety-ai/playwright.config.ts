import { defineConfig } from '@playwright/test';

const lightpandaWsEndpoint = process.env.LIGHTPANDA_WS_ENDPOINT;

const projects = [
	{
		name: 'chromium',
		use: {
			browserName: 'chromium'
		}
	}
];

if (lightpandaWsEndpoint) {
	projects.unshift({
		name: 'lightpanda',
		use: {
			connectOptions: {
				wsEndpoint: lightpandaWsEndpoint
			}
		}
	});
}

export default defineConfig({
	webServer: {
		command: 'env -u NO_COLOR npm run build && env -u NO_COLOR npm run preview',
		port: 4173
	},
	testMatch: '**/*.e2e.{ts,js}',
	projects
});
