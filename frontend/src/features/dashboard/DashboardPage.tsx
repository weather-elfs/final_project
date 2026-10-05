import { useCallback, useEffect, useState } from 'react';

import { ApiError, getDashboard, getDashboardConfig, type MapViewport } from '../../api';
import { stationsInViewport, toDashboardConfig, toViewModel } from './dashboardAdapter';
import DashboardView from './DashboardView';
import type { DashboardConfig, DashboardData, MissionValue, MissionValueKey, MissionValues } from './types';

const EMPTY_CONFIG: DashboardConfig = { stations: [], forecastIntervalOptionsH: [], missionTypes: [] };
const EMPTY_VALUES: MissionValues = { stationId: '', forecastIntervalH: '', missionType: '' };

interface DashboardPageProps {
  mapTilesEnabled?: boolean;
  onUnauthorized: () => void;
}

export default function DashboardPage({ mapTilesEnabled = true, onUnauthorized }: DashboardPageProps) {
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [mapMode, setMapMode] = useState<'current' | 'forecast'>('current');
  const [mapViewport, setMapViewport] = useState<MapViewport | null>(null);
  const [values, setValues] = useState<MissionValues>(EMPTY_VALUES);
  const [forecastRequested, setForecastRequested] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const errorMessage = (requestError: unknown) => {
    if (requestError instanceof ApiError && requestError.status === 401) onUnauthorized();
    const reference = requestError instanceof ApiError && requestError.requestId ? ` (요청 ID: ${requestError.requestId})` : '';
    return `${requestError instanceof Error ? requestError.message : '데이터 요청을 처리하지 못했습니다.'}${reference}`;
  };

  useEffect(() => {
    const controller = new AbortController();

    async function initialize() {
      setLoading(true);
      try {
        const configResponse = await getDashboardConfig({ signal: controller.signal });
        const nextConfig = toDashboardConfig(configResponse.data);
        setConfig(nextConfig);

        const stationId = nextConfig.stations.find((station) => station.id === '112')?.id ?? nextConfig.stations[0]?.id;
        const forecastIntervalH = nextConfig.forecastIntervalOptionsH.includes(6) ? 6 : nextConfig.forecastIntervalOptionsH[0];
        const missionType = nextConfig.missionTypes[0]?.missionType;
        if (stationId && forecastIntervalH && missionType) {
          const response = await getDashboard({ stationId, forecastIntervalH, missionType }, { signal: controller.signal });
          setDashboard(toViewModel<DashboardData>(response.data));
        }
      } catch (requestError) {
        if (!(requestError instanceof Error && requestError.name === 'AbortError')) setError(errorMessage(requestError));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    void initialize();
    return () => controller.abort();
  }, []);

  const visibleStations = stationsInViewport(config.stations, mapViewport);

  useEffect(() => {
    if (!mapViewport) return;
    const visibleStationIds = new Set(stationsInViewport(config.stations, mapViewport).map((station) => station.id));
    setValues((current) => {
      if (!current.stationId || visibleStationIds.has(current.stationId)) return current;
      return { ...current, stationId: '' };
    });
  }, [config.stations, mapViewport]);

  const fallbackRequest = (stationId = values.stationId || dashboard?.station?.stationId || config.stations[0]?.id) => {
    const forecastIntervalH = values.forecastIntervalH || (config.forecastIntervalOptionsH.includes(6) ? 6 : config.forecastIntervalOptionsH[0]);
    const missionType = values.missionType || config.missionTypes[0]?.missionType;
    return stationId && forecastIntervalH && missionType ? { stationId, forecastIntervalH, missionType } : null;
  };

  const loadDashboard = async (request: NonNullable<ReturnType<typeof fallbackRequest>>) => {
    setLoading(true);
    setError('');
    try {
      const response = await getDashboard(request);
      setDashboard(toViewModel<DashboardData>(response.data));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => {
    const request = fallbackRequest();
    if (!request || !values.stationId || !values.forecastIntervalH || !values.missionType) return;
    setForecastRequested(true);
    void loadDashboard(request);
  };

  const handleRefresh = () => {
    const request = fallbackRequest();
    if (request) void loadDashboard(request);
  };

  const handleStationSelect = (stationId: string) => {
    setValues((current) => ({ ...current, stationId }));
    const request = fallbackRequest(stationId);
    if (request) void loadDashboard(request);
  };

  const handleMapModeChange = (mode: 'current' | 'forecast') => {
    setMapMode(mode);
  };

  const handleMapViewportChange = useCallback((viewport: MapViewport) => setMapViewport(viewport), []);

  const handleChange = (key: MissionValueKey, value: MissionValue) => setValues((current) => ({ ...current, [key]: value } as MissionValues));

  return <DashboardView config={config} missionStations={visibleStations} dashboard={dashboard} mapMode={mapMode} mapTilesEnabled={mapTilesEnabled} values={values} forecastRequested={forecastRequested} loading={loading} error={error} onChange={handleChange} onMapModeChange={handleMapModeChange} onMapViewportChange={handleMapViewportChange} onStationSelect={handleStationSelect} onRefresh={handleRefresh} onSubmit={handleSubmit} />;
}
