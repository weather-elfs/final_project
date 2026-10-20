import './styles.css';

import { createRoot } from 'react-dom/client';
import App from './App';

async function enableMocking() {
  if (!import.meta.env.DEV) return;
  const { backendPlaceholderWorker, worker } = await import('./mocks/browser.js');
  const activeWorker = import.meta.env.MODE === 'backend' ? backendPlaceholderWorker : worker;
  await activeWorker.start({
    onUnhandledRequest(request, print) {
      if (import.meta.env.MODE === 'backend') return;
      if (new URL(request.url).pathname.startsWith('/api/')) print.error();
    },
  });
}

enableMocking().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('앱 루트 요소를 찾을 수 없습니다.');
  createRoot(root).render(<App />);
});
