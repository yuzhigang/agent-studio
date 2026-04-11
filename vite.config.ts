import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
    testTimeout: 30000,
    hookTimeout: 30000,
    fileParallelism: false,
    exclude: [...configDefaults.exclude, '.worktrees/**'],
  },
});
