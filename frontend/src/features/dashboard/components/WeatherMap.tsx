import 'leaflet/dist/leaflet.css';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CircleMarker,
  MapContainer,
  Pane,
  Polygon,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import type { DashboardMapPoint, FogMapLayer } from '../types';

import type { MapViewport } from '../../../api';
import {
  buildFogCoverageBounds,
  type FogCoverageBounds,
} from '../fogDistribution';
import { interpolateFogMapLayer } from '../forecastFog';
import FogSurfaceLayer from './FogSurfaceLayer';

const INITIAL_CENTER: [number, number] = [37.47772, 126.6249];
const FOG_FRAME_TRANSITION_MS = 850;
const INITIAL_ZOOM = 10;
const UNAVAILABLE_STATUSES = new Set([
  'ERROR',
  'FAIL',
  'FAILED',
  'MISSING',
  'NOT_AVAILABLE',
  'UNAVAILABLE',
]);
const DELAYED_STATUSES = new Set(['DELAYED', 'STALE']);
const FOG_DISTRIBUTION_BANDS = [
  {
    stage: 1,
    label: '옅은 안개',
    rangeLabel: '4–10 km',
    color: '#9eff91',
    radiusScale: 1,
    fillOpacity: 0.11,
  },
  {
    stage: 2,
    label: '옅은 안개',
    rangeLabel: '2–4 km',
    color: '#ffc905',
    radiusScale: 0.82,
    fillOpacity: 0.14,
  },
  {
    stage: 3,
    label: '안개',
    rangeLabel: '1–2 km',
    color: '#ff8205',
    radiusScale: 0.65,
    fillOpacity: 0.18,
  },
  {
    stage: 4,
    label: '안개',
    rangeLabel: '500 m–1 km',
    color: '#f02200',
    radiusScale: 0.48,
    fillOpacity: 0.23,
  },
  {
    stage: 5,
    label: '짙은 안개',
    rangeLabel: '200–500 m',
    color: '#890997',
    radiusScale: 0.33,
    fillOpacity: 0.32,
  },
  {
    stage: 6,
    label: '짙은 안개',
    rangeLabel: '200 m 미만',
    color: '#640015',
    radiusScale: 0.22,
    fillOpacity: 0.4,
  },
] as const;

const STATUS_LABELS: Record<string, string> = {
  SUCCESS: '정상',
  GOOD: '정상',
  RETRY_SUCCESS: '재시도 후 정상',
  DELAYED: '최신 자료 지연',
  STALE: '최신 자료 지연',
  ERROR: '오류',
  FAIL: '실패',
  FAILED: '실패',
  MISSING: '자료 없음',
  NOT_AVAILABLE: '예측 미제공',
  UNAVAILABLE: '사용 불가',
  UNKNOWN: '상태 확인 필요',
};

interface WeatherMapProps {
  points: DashboardMapPoint[];
  selectedId: string;
  focusStation?: Pick<
    DashboardMapPoint,
    'stationId' | 'latitude' | 'longitude'
  >;
  fogLayer?: FogMapLayer;
  forecastPlayback?: {
    frames: Array<{ horizonH: number; validAt?: string }>;
    activeIndex: number;
    coverageBounds?: FogCoverageBounds;
    playing: boolean;
    onToggle: () => void;
    onSelect: (index: number) => void;
  };
  tilesEnabled?: boolean;
  onSelect: (stationId: string) => void;
  onViewportChange: (viewport: MapViewport) => void;
}

function formatForecastFrameTime(validAt?: string) {
  if (!validAt || !Number.isFinite(Date.parse(validAt))) return '--:--';

  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(validAt));
}

function MapFocus({
  station,
  coverageBounds,
}: {
  station?: Pick<DashboardMapPoint, 'stationId' | 'latitude' | 'longitude'>;
  coverageBounds?: FogCoverageBounds;
}) {
  const map = useMap();
  const south = coverageBounds?.[0][0];
  const west = coverageBounds?.[0][1];
  const north = coverageBounds?.[1][0];
  const east = coverageBounds?.[1][1];

  useEffect(() => {
    if (south != null && west != null && north != null && east != null) {
      map.fitBounds([[south, west], [north, east]], {
        padding: [12, 12],
        maxZoom: INITIAL_ZOOM,
        animate: true,
        duration: 0.5,
      });
    } else if (station) {
      map.flyTo([station.latitude, station.longitude], INITIAL_ZOOM, {
        duration: 0.5,
      });
    }
  }, [
    map,
    south,
    west,
    north,
    east,
    station?.latitude,
    station?.longitude,
    station?.stationId,
  ]);

  return null;
}

function ViewportReporter({
  onViewportChange,
}: {
  onViewportChange: (viewport: MapViewport) => void;
}) {
  const map = useMap();
  const reportTimerRef = useRef<number | undefined>(undefined);
  const lastViewportKeyRef = useRef('');
  const scheduleViewportReport = useCallback(() => {
    window.clearTimeout(reportTimerRef.current);
    reportTimerRef.current = window.setTimeout(() => {
      const bounds = map.getBounds();
      const viewport = {
        west: Number(bounds.getWest().toFixed(5)),
        south: Number(bounds.getSouth().toFixed(5)),
        east: Number(bounds.getEast().toFixed(5)),
        north: Number(bounds.getNorth().toFixed(5)),
        zoom: map.getZoom(),
      };
      const viewportKey = `${viewport.west}:${viewport.south}:${viewport.east}:${viewport.north}:${viewport.zoom}`;
      if (viewportKey === lastViewportKeyRef.current) return;
      lastViewportKeyRef.current = viewportKey;
      onViewportChange(viewport);
    }, 250);
  }, [map, onViewportChange]);

  useMapEvents({ moveend: scheduleViewportReport });
  useEffect(() => () => window.clearTimeout(reportTimerRef.current), []);

  return null;
}

function useSmoothFogLayer(
  targetLayer: FogMapLayer | undefined,
  enabled: boolean,
  frameIndex?: number,
) {
  const [displayedLayer, setDisplayedLayer] = useState(targetLayer);
  const displayedLayerRef = useRef(targetLayer);
  const animationFrameRef = useRef<number | null>(null);
  const previousFrameIndexRef = useRef(frameIndex);

  useEffect(() => {
    if (animationFrameRef.current != null) {
      window.cancelAnimationFrame(animationFrameRef.current);
    }

    const fromLayer = displayedLayerRef.current;
    const previousFrameIndex = previousFrameIndexRef.current;
    previousFrameIndexRef.current = frameIndex;
    const restarting =
      frameIndex != null &&
      previousFrameIndex != null &&
      frameIndex < previousFrameIndex;
    const prefersReducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;

    if (
      !enabled ||
      restarting ||
      prefersReducedMotion ||
      !fromLayer ||
      !targetLayer
    ) {
      displayedLayerRef.current = targetLayer;
      setDisplayedLayer(targetLayer);
      return;
    }

    const startedAt = window.performance.now();
    const animate = (now: number) => {
      const progress = Math.min(
        1,
        (now - startedAt) / FOG_FRAME_TRANSITION_MS,
      );
      const nextLayer = interpolateFogMapLayer(
        fromLayer,
        targetLayer,
        progress,
      );

      displayedLayerRef.current = nextLayer;
      setDisplayedLayer(nextLayer);

      if (progress < 1) {
        animationFrameRef.current = window.requestAnimationFrame(animate);
      }
    };

    animationFrameRef.current = window.requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current != null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [enabled, frameIndex, targetLayer]);

  return displayedLayer;
}

export default function WeatherMap({
  points,
  selectedId,
  focusStation,
  fogLayer,
  forecastPlayback,
  tilesEnabled = true,
  onSelect,
  onViewportChange,
}: WeatherMapProps) {
  const [fogVisible, setFogVisible] = useState(true);
  const displayedFogLayer = useSmoothFogLayer(
    fogLayer,
    Boolean(forecastPlayback),
    forecastPlayback?.activeIndex,
  );
  const selected =
    points.find((point) => point.stationId === selectedId) ?? focusStation;
  const fogCoverageBounds = useMemo(
    () =>
      forecastPlayback?.coverageBounds ??
      buildFogCoverageBounds(displayedFogLayer?.cells ?? []),
    [displayedFogLayer?.cells, forecastPlayback?.coverageBounds],
  );

  return (
    <div
      className={`map-frame${fogVisible && fogLayer ? ' with-fog-scale' : ''}`}
    >
      <div className='map-viewport'>
        <MapContainer
          center={INITIAL_CENTER}
          zoom={INITIAL_ZOOM}
          minZoom={6}
          maxZoom={13}
          className='map-canvas'
        >
          {tilesEnabled && (
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
            />
          )}
          {fogVisible && displayedFogLayer && (
            <>
              {forecastPlayback && fogCoverageBounds && (
                <Pane name='forecast-coverage-mask' style={{ zIndex: 348 }}>
                  <Polygon
                    positions={[
                      [[85, -180], [85, 180], [-85, 180], [-85, -180]],
                      [
                        fogCoverageBounds[0],
                        [fogCoverageBounds[1][0], fogCoverageBounds[0][1]],
                        fogCoverageBounds[1],
                        [fogCoverageBounds[0][0], fogCoverageBounds[1][1]],
                      ],
                    ]}
                    interactive={false}
                    pathOptions={{
                      fillColor: '#26394a',
                      fillOpacity: 0.16,
                      fillRule: 'evenodd',
                      stroke: false,
                    }}
                  />
                </Pane>
              )}
              {fogCoverageBounds && (
                <Pane name='gk2a-fog-base' style={{ zIndex: 349 }}>
                  <Rectangle
                    bounds={fogCoverageBounds}
                    interactive={false}
                    pathOptions={{
                      color: 'transparent',
                      fillColor: '#74d7f7',
                      fillOpacity: 0.16,
                      opacity: 0,
                      stroke: false,
                    }}
                  />
                </Pane>
              )}
              <FogSurfaceLayer cells={displayedFogLayer.cells} />
              {forecastPlayback && fogCoverageBounds && (
                <Pane name='forecast-coverage-border' style={{ zIndex: 351 }}>
                  <Rectangle
                    bounds={fogCoverageBounds}
                    interactive={false}
                    pathOptions={{
                      color: '#487e9c',
                      opacity: 0.85,
                      weight: 1.5,
                      fill: false,
                    }}
                  />
                </Pane>
              )}
            </>
          )}
          <MapFocus
            station={selected}
            coverageBounds={forecastPlayback?.coverageBounds}
          />
          <ViewportReporter onViewportChange={onViewportChange} />
          {points.map((point) => {
            const active = point.stationId === selectedId;
            const status = point.status.toUpperCase();
            const unavailable = UNAVAILABLE_STATUSES.has(status);
            const delayed = DELAYED_STATUSES.has(status);
            const statusLabel = STATUS_LABELS[status] ?? point.status;
            const detail =
              point.visibilityKm == null
                ? `ASOS · ${statusLabel}`
                : `ASOS · 시정 ${point.visibilityKm.toFixed(1)} km${delayed || unavailable ? ` · ${statusLabel}` : ''}`;
            return (
              <CircleMarker
                key={point.stationId}
                center={[point.latitude, point.longitude]}
                radius={active ? 9 : 6}
                pathOptions={{
                  color: active ? '#f97316' : '#2563eb',
                  fillColor: '#ffffff',
                  fillOpacity: 1,
                  weight: active ? 4 : 3,
                }}
                eventHandlers={{ click: () => onSelect(point.stationId) }}
              >
                <Tooltip
                  key={`${point.stationId}-${active ? 'selected' : 'hover'}`}
                  direction='top'
                  offset={[0, -8]}
                  opacity={1}
                  permanent={active}
                  className='station-tooltip'
                >
                  <strong>
                    {point.stationName} ({point.stationId})
                  </strong>
                  <span>{detail}</span>
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
        {fogLayer && (
          <button
            type='button'
            className={`fog-layer-toggle${fogVisible ? ' active' : ''}`}
            aria-pressed={fogVisible}
            aria-label={
              fogVisible ? 'GK2A 안개 분포 숨기기' : 'GK2A 안개 분포 표시'
            }
            title={
              fogVisible ? 'GK2A 안개 분포 숨기기' : 'GK2A 안개 분포 표시'
            }
            onClick={() => setFogVisible((visible) => !visible)}
          >
            <span aria-hidden='true'>😶‍🌫️</span>
          </button>
        )}
        <div className='map-legend' aria-label='지도 범례'>
          <span>
            <i className='selected' />
            선택 ASOS
          </span>
          <span>
            <i />
            기타 ASOS
          </span>
        </div>
        {forecastPlayback && (
          <div
            className='forecast-playback'
            aria-label='예측 레이어 시간 재생'
          >
            <button
              type='button'
              className='forecast-playback-toggle'
              aria-label={forecastPlayback.playing ? '예측 일시정지' : '예측 재생'}
              title={forecastPlayback.playing ? '일시정지' : '재생'}
              onClick={forecastPlayback.onToggle}
            >
              <span aria-hidden='true'>
                {forecastPlayback.playing ? 'Ⅱ' : '▶'}
              </span>
            </button>
            <div className='forecast-playback-steps' role='group' aria-label='예측 시점'>
              {forecastPlayback.frames.map((frame, index) => (
                <button
                  type='button'
                  key={`${frame.horizonH}-${frame.validAt ?? index}`}
                  className={[
                    forecastPlayback.activeIndex === index ? 'active' : '',
                    forecastPlayback.activeIndex > index ? 'complete' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  aria-pressed={forecastPlayback.activeIndex === index}
                  aria-label={`+${frame.horizonH}시간 ${formatForecastFrameTime(frame.validAt)} KST`}
                  onClick={() => forecastPlayback.onSelect(index)}
                >
                  <strong>+{frame.horizonH}h</strong>
                  <span>{formatForecastFrameTime(frame.validAt)}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {fogVisible && fogLayer && (
          <div className='fog-layer-time'>
            {fogLayer.source} ·{' '}
            {new Intl.DateTimeFormat('ko-KR', {
              timeZone: 'Asia/Seoul',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            }).format(new Date(fogLayer.observedAt))}{' '}
            KST
          </div>
        )}
      </div>
      {fogVisible && fogLayer && (
        <div className='fog-stage-scale' aria-label='안개 위험 단계 범위'>
          <div className='fog-stage-scale-heading'>
            <strong>안개 위험 단계</strong>
            <span>6등급</span>
          </div>
          <div className='fog-stage-scale-range'>
            <div className='fog-stage-scale-bar' aria-hidden='true'>
              {FOG_DISTRIBUTION_BANDS.map((band) => (
                <i key={band.stage} style={{ backgroundColor: band.color }} />
              ))}
            </div>
            <div className='fog-stage-scale-ticks'>
              {FOG_DISTRIBUTION_BANDS.map((band) => (
                <span key={band.stage}>
                  <b>{band.stage}/6</b>
                  <em>{band.label}</em>
                  <small>{band.rangeLabel}</small>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
