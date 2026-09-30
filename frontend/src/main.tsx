import React from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import './styles.css';

async function enableMocking() {
  if (!import.meta.env.DEV) return;
  const { worker } = await import('./mocks/browser.js');
  await worker.start({
    onUnhandledRequest(request, print) {
      if (new URL(request.url).pathname.startsWith('/api/')) print.error();
    },
  });
}

enableMocking().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('앱 루트 요소를 찾을 수 없습니다.');
  createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
