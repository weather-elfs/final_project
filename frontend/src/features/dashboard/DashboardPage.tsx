import { useEffect, useState } from 'react';

import { ApiError, getDashboard, getDashboardConfig } from '../../api';
import { toDashboardConfig, toViewModel } from './dashboardAdapter';
import DashboardView from './DashboardView';
import type { DashboardConfig, DashboardData, MissionValue, MissionValueKey, MissionValues } from './types';

const EMPTY_CONFIG: DashboardConfig = { stations: [], forecastHorizonsH: [], missionTypes: [] };

interface DashboardPageProps {
  onLogout: () => void;
  onUnauthorized: () => void;
}

export default function DashboardPage({ onLogout, onUnauthorized }: DashboardPageProps) {
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [values, setValues] = useState<MissionValues>({ stationId: '', horizonH: 6, missionType: '', minimumVisibilityKm: 1 });
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getDashboardConfig({ signal: controller.signal })
      .then(({ data }) => {
        const nextConfig = toDashboardConfig(data);
        setConfig(nextConfig);
        setValues((current) => ({
          ...current,
          stationId: nextConfig.stations.find((station) => station.id === '112')?.id ?? nextConfig.stations[0]?.id ?? '',
          horizonH: nextConfig.forecastHorizonsH.at(-1) ?? 6,
          missionType: nextConfig.missionTypes[0]?.missionType ?? '',
        }));
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name !== 'AbortError') setError(requestError.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!values.stationId || !values.missionType) return undefined;
    const controller = new AbortController();
    setDashboard(null);
    setLoading(true);
    setError('');
    getDashboard(values, { signal: controller.signal })
      .then(({ data }) => setDashboard(toViewModel<DashboardData>(data)))
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name === 'AbortError') return;
        if (requestError instanceof ApiError && requestError.status === 401) onUnauthorized();
        const reference = requestError instanceof ApiError && requestError.requestId ? ` (요청 ID: ${requestError.requestId})` : '';
        const message = requestError instanceof Error ? requestError.message : '데이터 요청을 처리하지 못했습니다.';
        setError(`${message}${reference}`);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [values, refreshKey, onUnauthorized]);

  const handleChange = (key: MissionValueKey, value: MissionValue) => setValues((current) => ({ ...current, [key]: value } as MissionValues));

  return <DashboardView config={config} dashboard={dashboard} values={values} loading={loading} error={error} onChange={handleChange} onRefresh={() => setRefreshKey((key) => key + 1)} onLogout={onLogout} />;
}
