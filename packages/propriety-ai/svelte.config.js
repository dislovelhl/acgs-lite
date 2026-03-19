import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
        kit: {
                adapter: adapter({
                        fallback: 'index.html' // required for SPA mode
                })
        },
        vitePlugin: {
                dynamicCompileOptions: ({ filename }) => filename.includes('node_modules') ? undefined : { runes: true }
        }
};

export default config;
