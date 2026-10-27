import { useCallback, useEffect, useState } from 'react';

import { ApiError, getDashboard, getDashboardConfig, type MapViewport } from '../../api';
import { stationsInViewport, toDashboardConfig, toDashboardData } from './dashboardAdapter';
import DashboardView from './DashboardView';
import type { DashboardConfig, DashboardData, MissionValue, MissionValueKey, MissionValues } from './types';

const EMPTY_CONFIG: DashboardConfig = { stations: [], forecastIntervalOptionsH: [], missionTypes: [] };
const EMPTY_VALUES: MissionValues = { stationId: '', forecastIntervalH: '', missionType: '' };
const INITIAL_CONFIG_BOUNDS = { west: 124, south: 37, east: 127, north: 38.3 };

interface DashboardPageProps {
  centerId: string;
  mapTilesEnabled?: boolean;
  onUnauthorized: () => void;
}

export default function DashboardPage({ centerId, mapTilesEnabled = true, onUnauthorized }: DashboardPageProps) {
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [mapMode, setMapMode] = useState<'current' | 'forecast'>('current');
  const [mapViewport, setMapViewport] = useState<MapViewport | null>(null);
  const [values, setValues] = useState<MissionValues>(EMPTY_VALUES);
  const [forecastRequested, setForecastRequested] = useState(false);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retryingSource, setRetryingSource] = useState<string | null>(null);

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
        const configResponse = await getDashboardConfig(INITIAL_CONFIG_BOUNDS, { signal: controller.signal });
        const nextConfig = toDashboardConfig(configResponse.data);
        setConfig(nextConfig);

        const stationId = nextConfig.stations.find((station) => station.id === '112')?.id ?? nextConfig.stations[0]?.id;
        if (stationId) setValues((current) => ({ ...current, stationId }));
        const forecastIntervalH = nextConfig.forecastIntervalOptionsH.includes(6) ? 6 : nextConfig.forecastIntervalOptionsH[0];
        const missionType = nextConfig.missionTypes[0]?.missionType;
        if (stationId && forecastIntervalH && missionType) {
          const response = await getDashboard({ stationId, forecastIntervalH, missionType }, { signal: controller.signal });
          setDashboard(toDashboardData(response.data));
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
    const bounds = mapViewport;
    const controller = new AbortController();

    async function refreshConfig() {
      try {
        const response = await getDashboardConfig(bounds, { signal: controller.signal });
        const nextConfig = toDashboardConfig(response.data);
        setConfig((current) => ({
          ...nextConfig,
          fogLayer: nextConfig.fogLayer ?? current.fogLayer,
        }));
      } catch (requestError) {
        if (!(requestError instanceof Error && requestError.name === 'AbortError')) setError(errorMessage(requestError));
      }
    }

    void refreshConfig();
    return () => controller.abort();
  }, [mapViewport]);

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
      setDashboard(toDashboardData(response.data));
    } catch (requestError) {
      setDashboard((current) => current?.station?.stationId === request.stationId && current?.requestContext?.forecastIntervalH === request.forecastIntervalH ? current : null);
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    const request = fallbackRequest();
    if (loading || retryingSource || !request || !values.stationId || !values.forecastIntervalH || !values.missionType) return;
    setForecastRequested(true);
    setForecastLoading(true);
    try {
      await loadDashboard(request);
    } finally {
      setForecastLoading(false);
    }
  };

  const handleRetrySource = async (source: string) => {
    const collection = dashboard?.meta?.collection;
    const context = dashboard?.requestContext;
    const stationId = dashboard?.station?.stationId;
    if (loading || retryingSource || !collection?.id || !stationId || !context?.forecastIntervalH || !context.missionType) return;
    setRetryingSource(source);
    setError('');
    try {
      const response = await getDashboard({ stationId, forecastIntervalH: context.forecastIntervalH, missionType: context.missionType, collectionId: collection.id, retrySource: source });
      setDashboard((current) => current?.meta?.collection?.id === collection.id ? toDashboardData(response.data) : current);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setRetryingSource(null);
    }
  };

  const handleRefresh = () => {
    if (retryingSource) return;
    const request = fallbackRequest();
    if (request) void loadDashboard(request);
  };

  const handleStationSelect = (stationId: string) => {
    if (retryingSource) return;
    setValues((current) => ({ ...current, stationId }));
    const request = fallbackRequest(stationId);
    if (request) void loadDashboard(request);
  };

  const handleMapModeChange = (mode: 'current' | 'forecast') => {
    setMapMode(mode);
  };

  const handleMapViewportChange = useCallback((viewport: MapViewport) => setMapViewport(viewport), []);

  const handleChange = (key: MissionValueKey, value: MissionValue) => {
    if (key === 'stationId') {
      handleStationSelect(String(value));
      return;
    }
    setValues((current) => ({ ...current, [key]: value } as MissionValues));
  };

  return <DashboardView centerId={centerId} config={config} missionStations={visibleStations} dashboard={dashboard} mapMode={mapMode} mapTilesEnabled={mapTilesEnabled} values={values} forecastRequested={forecastRequested} forecastLoading={forecastLoading} loading={loading} retryingSource={retryingSource} error={error} onChange={handleChange} onMapModeChange={handleMapModeChange} onMapViewportChange={handleMapViewportChange} onStationSelect={handleStationSelect} onRefresh={handleRefresh} onRetrySource={handleRetrySource} onSubmit={handleSubmit} onLogout={onUnauthorized} />;
}
