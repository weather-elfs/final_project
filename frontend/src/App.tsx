import { useCallback, useState } from 'react';

import LoginPage from './features/auth/LoginPage';
import DashboardPage from './features/dashboard/DashboardPage';

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const clearAuthentication = useCallback(() => setAuthenticated(false), []);

  if (!authenticated) return <LoginPage onAuthenticated={() => setAuthenticated(true)} />;
  return <DashboardPage onUnauthorized={clearAuthentication} />;
}
