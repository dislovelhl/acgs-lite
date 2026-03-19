import { render } from '@testing-library/svelte';
import { describe, it, expect } from 'vitest';
import Page from './+page.svelte';

describe('Home Page', () => {
  it('renders the dashboard title', () => {
    const { getByText } = render(Page);
    expect(getByText('ACGS Dashboard')).toBeTruthy();
  });
});
