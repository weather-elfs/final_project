import { useEffect, useState } from 'react';

import ForecastPanel from './components/ForecastPanel';
import MissionConditionsForm from './components/MissionConditionsForm';
import VisibilitySummary from './components/VisibilitySummary';
import WeatherMap from './components/WeatherMap';
import { formatKstDate, formatKstTime, isKstRefreshImminent } from './formatters';
import type { DashboardViewProps } from './types';

function useLiveReferenceTime(reference?: string) {
  const [liveTime, setLiveTime] = useState<string>();

  useEffect(() => {
    const referenceTime = reference ? Date.parse(reference) : Number.NaN;
    if (!Number.isFinite(referenceTime)) {
      setLiveTime(undefined);
      return undefined;
    }

    const synchronizedAt = Date.now();
    const update = () => setLiveTime(new Date(referenceTime + Date.now() - synchronizedAt).toISOString());
    update();
    const intervalId = window.setInterval(update, 1_000);
    return () => window.clearInterval(intervalId);
  }, [reference]);

  return liveTime ?? (reference && Number.isFinite(Date.parse(reference)) ? reference : undefined);
}

export default function DashboardView({ config, missionStations, dashboard, mapMode, mapTilesEnabled = true, values, forecastRequested = false, loading = false, error = '', onChange, onMapModeChange, onMapViewportChange, onStationSelect, onRefresh, onSubmit }: DashboardViewProps) {
  const liveReferenceTime = useLiveReferenceTime(dashboard?.meta?.generatedAt ?? config.meta?.generatedAt);
  const refreshImminent = isKstRefreshImminent(liveReferenceTime);
  const selectedStationId = values.stationId || dashboard?.station?.stationId || config.stations.find((station) => station.id === '112')?.id || config.stations[0]?.id || '';
  const selectedStation = config.stations.find((station) => station.id === selectedStationId);
  const forecastAtSixHours = dashboard?.forecastTimeline?.find((point) => point.horizonH === 6);
  const mapReferenceTime = mapMode === 'current'
    ? dashboard?.current?.observedAt ?? config.meta?.generatedAt
    : forecastAtSixHours?.validAt ?? config.meta?.generatedAt;
  const mapPoints = config.stations.map((station) => {
    const hasSelectedDashboard = dashboard?.station?.stationId === station.id;
    return {
      stationId: station.id,
      stationName: station.name,
      latitude: station.latitude,
      longitude: station.longitude,
      validAt: mapMode === 'current' ? dashboard?.current?.observedAt : forecastAtSixHours?.validAt,
      visibilityKm: hasSelectedDashboard
        ? mapMode === 'current' ? dashboard?.current?.visibilityKm : forecastAtSixHours?.visibilityPredKm
        : null,
      status: mapMode === 'current' ? station.currentStatus ?? 'UNKNOWN' : station.forecastStatus ?? 'UNKNOWN',
    };
  });
  const missionConfig = { ...config, stations: missionStations };

  return (
    <div className="weather-ui dashboard-shell">
      <header className="top-bar">
        <div className="brand"><span aria-hidden="true">W</span><strong>기상 데이터 지상국</strong></div>
        <div className={`reference-time${refreshImminent ? ' refresh-imminent' : ''}`}><span>현재 시각 {formatKstDate(liveReferenceTime)}</span><strong>{formatKstTime(liveReferenceTime)} KST</strong></div>
      </header>

      <main className="dashboard-main">
        {error && <div className="page-error" role="alert"><strong>데이터를 불러오지 못했습니다.</strong><span>{error}</span></div>}
        <div className="dashboard-grid" aria-busy={loading}>
          <section className="panel map-panel" aria-labelledby="map-title">
            <div className="panel-header map-header">
              <div><h2 id="map-title">시정 현황 지도</h2><p>{selectedStation ? `${selectedStation.name} 연안` : '인천 연안'} · {mapMode === 'current' ? '현재 관측' : '+6시간 예측'} {formatKstTime(mapReferenceTime)} KST</p></div>
              <div className="layer-toggle" role="group" aria-label="지도 레이어">
                <button type="button" className={mapMode === 'current' ? 'active' : ''} onClick={() => onMapModeChange('current')}>현재 관측</button>
                <button type="button" className={mapMode === 'forecast' ? 'active' : ''} onClick={() => onMapModeChange('forecast')}>예측 레이어</button>
              </div>
            </div>
            {config.stations.length > 0 ? <WeatherMap points={mapPoints} selectedId={selectedStationId} focusStation={selectedStation} tilesEnabled={mapTilesEnabled} onSelect={onStationSelect} onViewportChange={onMapViewportChange} /> : <div className="map-placeholder">지도 자료를 불러오는 중입니다.</div>}
            <div className="map-source"><span>지도 음영은 관측 자료와 예측 모델을 바탕으로 추정한 시정 분포입니다.</span><span>데이터 출처 ASOS · 해양부이 · GK2A · AirKorea · 산림청</span></div>
          </section>

          <VisibilitySummary dashboard={dashboard} loading={loading} onRefresh={onRefresh} />
          <MissionConditionsForm config={missionConfig} values={values} generatedAt={dashboard?.meta?.generatedAt} loading={loading} onChange={onChange} onSubmit={onSubmit} />
          <ForecastPanel dashboard={dashboard} requested={forecastRequested} loading={loading} />
        </div>
      </main>
      <footer className="app-footer">시스템 v1.0 · 국방기상지원센터</footer>
    </div>
  );
}
