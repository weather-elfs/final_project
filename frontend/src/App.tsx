import { useCallback, useState } from 'react';

import LoginPage from './features/auth/LoginPage';
import DashboardPage from './features/dashboard/DashboardPage';

const BACKEND_INTEGRATION_MODE = import.meta.env.DEV && import.meta.env.MODE === 'backend';
const DEVELOPMENT_CENTER = { id: '33182', name: '개발용 관제센터' };

export default function App() {
  const [center, setCenter] = useState<{ id: string; name: string } | null>(BACKEND_INTEGRATION_MODE ? DEVELOPMENT_CENTER : null);
  const clearAuthentication = useCallback(() => {
    if (!BACKEND_INTEGRATION_MODE) setCenter(null);
  }, []);

  if (!center) return <LoginPage onAuthenticated={setCenter} />;
  return <DashboardPage centerId={center.id} onUnauthorized={clearAuthentication} />;
}
