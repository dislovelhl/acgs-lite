import { render } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import Page from './+page.svelte';

vi.mock('@threlte/core', async (importOriginal) => {
	const actual = (await importOriginal()) as Record<string, unknown>;
	return {
		...actual,
		Canvas: Object.assign(() => {}, { render: () => {} }),
		T: new Proxy({}, { get: () => () => {} })
	};
});

describe('Home Page', () => {
	it('renders the ACGS hero copy', () => {
		const { getByText } = render(Page);
		expect(getByText(/HTTPS/i)).toBeTruthy();
		expect(getByText(/for AI/i)).toBeTruthy();
	});
});
