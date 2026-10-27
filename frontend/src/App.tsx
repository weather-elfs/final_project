import { useCallback, useState } from 'react';

import { DEMO_CENTER, DEMO_LOGIN_MODE } from './demo';
import LoginPage from './features/auth/LoginPage';
import DashboardPage from './features/dashboard/DashboardPage';

const DEMO_SESSION_KEY = 'weather-demo-session';

export default function App() {
  const [center, setCenter] = useState<{ id: string; name: string } | null>(() => (
    DEMO_LOGIN_MODE && sessionStorage.getItem(DEMO_SESSION_KEY) === 'active' ? { ...DEMO_CENTER } : null
  ));
  const handleAuthenticated = (nextCenter: { id: string; name: string }) => {
    if (DEMO_LOGIN_MODE) sessionStorage.setItem(DEMO_SESSION_KEY, 'active');
    setCenter(nextCenter);
  };
  const clearAuthentication = useCallback(() => {
    sessionStorage.removeItem(DEMO_SESSION_KEY);
    setCenter(null);
  }, []);

  if (!center) return <LoginPage onAuthenticated={handleAuthenticated} />;
  return <DashboardPage centerId={center.id} onUnauthorized={clearAuthentication} />;
}
