import { useEffect, useMemo, useRef, useState } from 'react';
import {
  formatKstDate,
  formatKstTime,
  isKstRefreshImminent,
} from './formatters';

import AlertOperationsPage from '../alerts/AlertOperationsPage';
import HistoryPage from '../history/HistoryPage';
import ForecastPanel from './components/ForecastPanel';
import MissionConditionsForm from './components/MissionConditionsForm';
import VisibilitySummary from './components/VisibilitySummary';
import WeatherMap from './components/WeatherMap';
import { buildFogCoverageBounds } from './fogDistribution';
import { buildForecastFogDemoFrames } from './forecastFog';
import { isForecastAvailable, normalizeCurrentStatus } from './stationStatus';
import type { DashboardViewProps } from './types';

function useCurrentTime() {
  const [liveTime, setLiveTime] = useState(() => new Date().toISOString());

  useEffect(() => {
    const update = () => setLiveTime(new Date().toISOString());
    update();
    const intervalId = window.setInterval(update, 1_000);
    return () => window.clearInterval(intervalId);
  }, []);

  return liveTime;
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);
    mediaQuery.addEventListener('change', updatePreference);
    return () => mediaQuery.removeEventListener('change', updatePreference);
  }, []);

  return prefersReducedMotion;
}

export default function DashboardView({
  centerId = '33182',
  config,
  missionStations,
  dashboard,
  mapMode,
  mapTilesEnabled = true,
  values,
  forecastRequested = false,
  loading = false,
  error = '',
  onChange,
  onMapModeChange,
  onMapViewportChange,
  onStationSelect,
  onRefresh,
  onSubmit,
  onLogout,
}: DashboardViewProps) {
  const [activeSection, setActiveSection] = useState<
    'dashboard' | 'alerts' | 'history'
  >('dashboard');
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [forecastFrameIndex, setForecastFrameIndex] = useState(0);
  const [forecastPlaying, setForecastPlaying] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = usePrefersReducedMotion();
  const liveReferenceTime = useCurrentTime();
  const refreshImminent = isKstRefreshImminent(liveReferenceTime);
  const selectedStationId =
    values.stationId ||
    dashboard?.station?.stationId ||
    config.stations.find((station) => station.id === '112')?.id ||
    config.stations[0]?.id ||
    '';
  const selectedStation = config.stations.find(
    (station) => station.id === selectedStationId,
  );
  const forecastFogFrames = useMemo(
    () =>
      buildForecastFogDemoFrames(
        config.fogLayer,
        dashboard?.forecastTimeline ?? [],
      ),
    [config.fogLayer, dashboard?.forecastTimeline],
  );
  const activeForecastFrameIndex = forecastFogFrames[forecastFrameIndex]
    ? forecastFrameIndex
    : 0;
  const forecastCoverageBounds = useMemo(
    () =>
      buildFogCoverageBounds(
        forecastFogFrames.flatMap((frame) => frame.layer.cells),
        0.32,
      ),
    [forecastFogFrames],
  );
  const activeForecastFogFrame =
    forecastFogFrames[activeForecastFrameIndex];
  const forecastMapPoint = activeForecastFogFrame
    ? dashboard?.forecastTimeline?.find(
        (point) => point.horizonH === activeForecastFogFrame.horizonH,
      )
    : (dashboard?.forecastTimeline?.find((point) => point.horizonH === 6) ??
      dashboard?.forecastTimeline?.[0]);
  const forecastAvailable =
    Boolean(forecastMapPoint) ||
    isForecastAvailable(selectedStation?.forecastStatus);
  const forecastMapLabel =
    forecastMapPoint?.horizonH == null
      ? '예측'
      : `+${forecastMapPoint.horizonH}시간 예측`;
  const mapReferenceTime =
    mapMode === 'current'
      ? dashboard?.current?.observedAt
      : forecastMapPoint?.validAt;
  const mapPoints = config.stations.map((station) => {
    const hasSelectedDashboard = dashboard?.station?.stationId === station.id;
    return {
      stationId: station.id,
      stationName: station.name,
      latitude: station.latitude,
      longitude: station.longitude,
      validAt:
        mapMode === 'current'
          ? dashboard?.current?.observedAt
          : forecastMapPoint?.validAt,
      visibilityKm: hasSelectedDashboard
        ? mapMode === 'current'
          ? dashboard?.current?.visibilityKm
          : forecastMapPoint?.visibilityPredKm
        : null,
      status:
        mapMode === 'current'
          ? hasSelectedDashboard
            ? normalizeCurrentStatus(dashboard?.current?.status)
            : (station.currentStatus ?? 'UNKNOWN')
          : hasSelectedDashboard && forecastMapPoint
            ? 'GOOD'
            : (station.forecastStatus ?? 'UNKNOWN'),
    };
  });
  const missionConfig = { ...config, stations: missionStations };

  useEffect(() => {
    setForecastFrameIndex(0);
  }, [dashboard?.meta?.requestId, selectedStationId, values.forecastIntervalH]);

  useEffect(() => {
    setForecastPlaying(
      mapMode === 'forecast' &&
        forecastFogFrames.length > 1 &&
        !prefersReducedMotion,
    );
  }, [
    dashboard?.meta?.requestId,
    forecastFogFrames.length,
    mapMode,
    prefersReducedMotion,
  ]);

  useEffect(() => {
    if (
      mapMode !== 'forecast' ||
      !forecastPlaying ||
      forecastFogFrames.length < 2
    ) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setForecastFrameIndex(
        (index) => (index + 1) % forecastFogFrames.length,
      );
    }, 900);
    return () => window.clearInterval(intervalId);
  }, [forecastFogFrames.length, forecastPlaying, mapMode]);

  useEffect(() => {
    if (!accountMenuOpen) return undefined;

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!accountMenuRef.current?.contains(event.target as Node))
        setAccountMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setAccountMenuOpen(false);
    };

    document.addEventListener('pointerdown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [accountMenuOpen]);

  const handleLogout = () => {
    setAccountMenuOpen(false);
    onLogout?.();
  };

  return (
    <div className='weather-ui dashboard-shell'>
      <header className='top-bar'>
        <div className='brand'>
          <span aria-hidden='true'>W</span>
          <strong>기상 데이터 지상국</strong>
        </div>
        <div className='header-cluster'>
          <nav className='primary-navigation' aria-label='주요 메뉴'>
            <button
              type='button'
              className={activeSection === 'dashboard' ? 'active' : ''}
              aria-current={activeSection === 'dashboard' ? 'page' : undefined}
              onClick={() => setActiveSection('dashboard')}
            >
              대시보드
            </button>
            <button
              type='button'
              className={activeSection === 'alerts' ? 'active' : ''}
              aria-current={activeSection === 'alerts' ? 'page' : undefined}
              onClick={() => setActiveSection('alerts')}
            >
              경보 운영
            </button>
            <button
              type='button'
              className={activeSection === 'history' ? 'active' : ''}
              aria-current={activeSection === 'history' ? 'page' : undefined}
              onClick={() => setActiveSection('history')}
            >
              이력 조회
            </button>
          </nav>
          <div className='account-menu' ref={accountMenuRef}>
            <button
              className='account-trigger'
              type='button'
              aria-label={`${centerId} 계정 메뉴`}
              aria-haspopup='menu'
              aria-expanded={accountMenuOpen}
              aria-controls='account-menu-popover'
              onClick={() => setAccountMenuOpen((open) => !open)}
            >
              <span className='account-status' aria-hidden='true' />
              <span>{centerId}</span>
              <span className='account-chevron' aria-hidden='true' />
            </button>
            {accountMenuOpen && (
              <div
                id='account-menu-popover'
                className='account-menu-popover'
                role='menu'
                aria-label='계정 메뉴'
              >
                <p>센터 ID {centerId}</p>
                <button type='button' role='menuitem' onClick={handleLogout}>
                  로그아웃
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      {activeSection === 'dashboard' ? (
        <>
          <div className='page-meta'>
            <div
              className={`reference-time${refreshImminent ? ' refresh-imminent' : ''}`}
            >
              <span>현재 시각 {formatKstDate(liveReferenceTime)}</span>
              <strong>{formatKstTime(liveReferenceTime)} KST</strong>
            </div>
          </div>

          <main className='dashboard-main'>
            {error && (
              <div className='page-error' role='alert'>
                <strong>데이터를 불러오지 못했습니다.</strong>
                <span>{error}</span>
              </div>
            )}
            <div className='dashboard-grid' aria-busy={loading}>
              <section className='panel map-panel' aria-labelledby='map-title'>
                <div className='panel-header map-header'>
                  <div>
                    <h2 id='map-title'>시정 현황 지도</h2>
                    <p>
                      {selectedStation
                        ? `${selectedStation.name} 연안`
                        : '인천 연안'}{' '}
                      · {mapMode === 'current' ? '현재 관측' : forecastMapLabel}{' '}
                      {formatKstTime(mapReferenceTime)} KST
                    </p>
                  </div>
                  <div
                    className='layer-toggle'
                    role='group'
                    aria-label='지도 레이어'
                  >
                    <button
                      type='button'
                      className={mapMode === 'current' ? 'active' : ''}
                      onClick={() => onMapModeChange('current')}
                    >
                      현재 관측
                    </button>
                    <button
                      type='button'
                      className={mapMode === 'forecast' ? 'active' : ''}
                      onClick={() => {
                        setForecastFrameIndex(0);
                        onMapModeChange('forecast');
                      }}
                      disabled={!forecastAvailable}
                      title={
                        forecastAvailable
                          ? undefined
                          : '예측 서비스가 제공되지 않습니다.'
                      }
                    >
                      예측 레이어
                    </button>
                  </div>
                </div>
                <WeatherMap
                  points={mapPoints}
                  selectedId={selectedStationId}
                  focusStation={selectedStation}
                  fogLayer={
                    mapMode === 'current'
                      ? config.fogLayer
                      : activeForecastFogFrame?.layer
                  }
                  forecastPlayback={
                    mapMode === 'forecast' && forecastFogFrames.length > 0
                      ? {
                          frames: forecastFogFrames.map(
                            ({ horizonH, validAt }) => ({ horizonH, validAt }),
                          ),
                          activeIndex: activeForecastFrameIndex,
                          coverageBounds: forecastCoverageBounds,
                          playing: forecastPlaying,
                          onToggle: () =>
                            setForecastPlaying((playing) => !playing),
                          onSelect: (index) => {
                            setForecastFrameIndex(index);
                            setForecastPlaying(false);
                          },
                        }
                      : undefined
                  }
                  tilesEnabled={mapTilesEnabled}
                  onSelect={onStationSelect}
                  onViewportChange={onMapViewportChange}
                />
                <div className='map-source'>
                  {(mapMode === 'forecast' || Boolean(config.fogLayer?.cells.length)) && (
                    <span>
                      {mapMode === 'forecast'
                        ? '수집된 GK2A 관측 격자를 바탕으로 안개 분포 변화를 시각화합니다.'
                        : '지도 음영은 GK2A 탐지 격자를 평활화한 안개 분포 추정입니다.'}
                    </span>
                  )}
                  <span>{mapMode === 'forecast' ? '기상·예측 시점: API · 안개 음영: 이동 시연' : '데이터 출처 ASOS · 해양부이 · GK2A · AirKorea'}</span>
                </div>
              </section>

              <VisibilitySummary
                dashboard={dashboard}
                loading={loading}
                onRefresh={onRefresh}
              />
              <MissionConditionsForm
                config={missionConfig}
                values={values}
                currentTime={liveReferenceTime}
                forecastBaseTime={dashboard?.current?.observedAt}
                loading={loading}
                onChange={onChange}
                onSubmit={onSubmit}
              />
              <ForecastPanel
                dashboard={dashboard}
                requested={forecastRequested}
                loading={loading}
                available={forecastAvailable}
              />
            </div>
          </main>
        </>
      ) : activeSection === 'alerts' ? (
        <AlertOperationsPage referenceTime={liveReferenceTime} />
      ) : (
        <HistoryPage referenceTime={liveReferenceTime} />
      )}
      <footer className='app-footer'>시스템 v1.0 · 국방기상지원센터</footer>
    </div>
  );
}
