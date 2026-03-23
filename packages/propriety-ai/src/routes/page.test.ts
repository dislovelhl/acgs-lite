import { render } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import Page from './+page.svelte';

describe('Home Page', () => {
	it('renders the ACGS hero copy', () => {
		const { getByText } = render(Page);
		expect(getByText('HTTPS')).toBeTruthy();
		expect(getByText('for AI')).toBeTruthy();
	});
});
