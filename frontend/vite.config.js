import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({
    plugins: [react()],
    test: {
        exclude: ['node_modules/**', 'dist/**', 'tests/**/*.spec.ts'],
    },
    server: {
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8001',
                changeOrigin: true,
            },
        },
    },
});
