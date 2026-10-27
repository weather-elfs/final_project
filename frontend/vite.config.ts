import { rm } from 'node:fs/promises';
import { resolve } from 'node:path';

import { defineConfig, loadEnv } from 'vite';

import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000';

  return {
    plugins: [
      react(),
      {
        name: 'exclude-demo-service-worker',
        apply: 'build',
        async writeBundle(outputOptions) {
          if (mode === 'demo' && outputOptions.dir) {
            await rm(resolve(outputOptions.dir, 'mockServiceWorker.js'), { force: true });
          }
        },
      },
    ],
    server: {
      proxy:
        mode === 'backend'
          ? {
              '/api': {
                target: backendTarget,
                changeOrigin: true,
              },
            }
          : undefined,
    },
  };
});
