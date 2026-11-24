import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));

export default defineConfig(({ command }) => ({
  base: './',
  define: { __APP_VERSION__: JSON.stringify(version) },
  plugins: [react(), {
    name: 'development-csp',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        if (command !== 'serve') return html;
        // Use an external module for React's refresh preamble; script-src stays self-only.
        return html.replace(/<script type="module">([\s\S]*?\$RefreshSig\$[\s\S]*?)<\/script>/, '<script type="module" src="/@lumix-refresh"></script>')
          .replace("connect-src 'self'", "connect-src 'self' ws://127.0.0.1:5173");
      },
    },
    configureServer(server) {
      server.middlewares.use('/@lumix-refresh', (_request, response) => {
        response.setHeader('Content-Type', 'application/javascript');
        response.end(react.preambleCode.replace('__BASE__', '/'));
      });
    },
  }],
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  build: { outDir: 'renderer-dist', emptyOutDir: true },
}));
