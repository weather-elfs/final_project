import { setupWorker } from 'msw/browser';
import { mswLoader } from 'msw-storybook-addon/csf3';
import type { Preview } from '@storybook/react-vite';

import '../src/styles.css';

const preview: Preview = {
  loaders: [mswLoader(async () => {
    const worker = setupWorker();
    await worker.start({
      onUnhandledRequest(request, print) {
        if (new URL(request.url).pathname.startsWith('/api/')) print.error();
      },
    });
    return worker;
  })],
  parameters: {
    layout: 'fullscreen',
    controls: { expanded: true },
    a11y: { test: 'error' },
  },
};

export default preview;
