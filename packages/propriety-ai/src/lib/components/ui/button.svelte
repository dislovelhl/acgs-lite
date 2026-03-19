<script lang="ts">
	let {
		children,
		variant = 'primary',
		...rest
	} = $props<{
		children: import('svelte').Snippet;
		variant?: 'primary' | 'secondary' | 'outline';
		[key: string]: unknown;
	}>();

	const variants = {
		primary: 'bg-blue-600 text-white hover:bg-blue-700',
		secondary:
			'bg-gray-100 text-gray-900 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700',
		outline:
			'bg-transparent text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 dark:text-white dark:ring-gray-700 dark:hover:bg-gray-800'
	};
</script>

<button
	class="inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:pointer-events-none disabled:opacity-50 {variants[
		variant
	]}"
	{...rest}
>
	{@render children()}
</button>
