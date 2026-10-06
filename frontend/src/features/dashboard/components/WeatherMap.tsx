import { useCallback, useEffect, useState } from 'react';
import { Circle, CircleMarker, MapContainer, Pane, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

import type { MapViewport } from '../../../api';
import { buildFogDistributionClusters } from '../fogDistribution';
import type { DashboardMapPoint, FogMapLayer } from '../types';

const INITIAL_CENTER: [number, number] = [37.47772, 126.6249];
const INITIAL_ZOOM = 10;
const UNAVAILABLE_STATUSES = new Set(['ERROR', 'FAIL', 'FAILED', 'MISSING', 'UNAVAILABLE']);
const FOG_DISTRIBUTION_BANDS = [
  { stage: 1, color: '#9eff91', radiusScale: 1, fillOpacity: 0.12 },
  { stage: 2, color: '#ffc905', radiusScale: 0.82, fillOpacity: 0.16 },
  { stage: 3, color: '#ff8205', radiusScale: 0.65, fillOpacity: 0.2 },
  { stage: 4, color: '#f02200', radiusScale: 0.48, fillOpacity: 0.27 },
  { stage: 5, color: '#890997', radiusScale: 0.33, fillOpacity: 0.36 },
  { stage: 6, color: '#640015', radiusScale: 0.22, fillOpacity: 0.44 },
] as const;
const FOG_STAGE_LEGEND = [
  { label: '1–2단계', background: 'linear-gradient(90deg, #9eff91 0 50%, #ffc905 50%)' },
  { label: '3–4단계', background: 'linear-gradient(90deg, #ff8205 0 50%, #f02200 50%)' },
  { label: '5–6단계', background: 'linear-gradient(90deg, #890997 0 50%, #640015 50%)' },
] as const;

const STATUS_LABELS: Record<string, string> = {
  GOOD: '정상',
  RETRY_SUCCESS: '재시도 후 정상',
  DELAYED: '지연',
  ERROR: '오류',
  FAIL: '실패',
  FAILED: '실패',
  MISSING: '자료 없음',
  UNAVAILABLE: '사용 불가',
  UNKNOWN: '상태 확인 필요',
};

interface WeatherMapProps {
  points: DashboardMapPoint[];
  selectedId: string;
  focusStation?: Pick<DashboardMapPoint, 'stationId' | 'latitude' | 'longitude'>;
  fogLayer?: FogMapLayer;
  tilesEnabled?: boolean;
  onSelect: (stationId: string) => void;
  onViewportChange: (viewport: MapViewport) => void;
}

function MapFocus({ station }: { station?: Pick<DashboardMapPoint, 'stationId' | 'latitude' | 'longitude'> }) {
  const map = useMap();

  useEffect(() => {
    if (station) map.flyTo([station.latitude, station.longitude], INITIAL_ZOOM, { duration: 0.5 });
  }, [map, station?.latitude, station?.longitude, station?.stationId]);

  return null;
}

function ViewportReporter({ onViewportChange }: { onViewportChange: (viewport: MapViewport) => void }) {
  const map = useMap();
  const reportViewport = useCallback(() => {
    const bounds = map.getBounds();
    onViewportChange({
      west: bounds.getWest(),
      south: bounds.getSouth(),
      east: bounds.getEast(),
      north: bounds.getNorth(),
      zoom: map.getZoom(),
    });
  }, [map, onViewportChange]);

  useMapEvents({ moveend: reportViewport });
  useEffect(reportViewport, [reportViewport]);

  return null;
}

export default function WeatherMap({ points, selectedId, focusStation, fogLayer, tilesEnabled = true, onSelect, onViewportChange }: WeatherMapProps) {
  const [fogVisible, setFogVisible] = useState(true);
  const selected = points.find((point) => point.stationId === selectedId) ?? focusStation;
  const fogClusters = buildFogDistributionClusters(fogLayer?.cells ?? []);

  return (
    <div className="map-frame">
      <MapContainer center={INITIAL_CENTER} zoom={INITIAL_ZOOM} minZoom={6} maxZoom={13} className="map-canvas">
        {tilesEnabled && <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />}
        {fogVisible && fogLayer && (
          <Pane name="gk2a-fog-layer" style={{ zIndex: 350 }}>
            {FOG_DISTRIBUTION_BANDS.map((band) => fogClusters
              .filter((cluster) => band.stage <= cluster.maxFogClass)
              .map((cluster) => (
              <Circle
                key={`${band.stage}-${cluster.id}`}
                center={cluster.center}
                radius={cluster.radiusM * band.radiusScale}
                interactive={false}
                pathOptions={{
                  className: 'fog-density-band',
                  color: band.color,
                  fillColor: band.color,
                  fillOpacity: band.fillOpacity * cluster.intensity,
                  opacity: 0,
                  stroke: false,
                }}
              />
            )))}
          </Pane>
        )}
        <MapFocus station={selected} />
        <ViewportReporter onViewportChange={onViewportChange} />
        {points.map((point) => {
          const active = point.stationId === selectedId;
          const status = point.status.toUpperCase();
          const unavailable = UNAVAILABLE_STATUSES.has(status);
          const detail = point.visibilityKm == null
            ? `ASOS · ${STATUS_LABELS[status] ?? point.status}`
            : `ASOS · 시정 ${point.visibilityKm.toFixed(1)} km`;
          return (
            <CircleMarker
              key={point.stationId}
              center={[point.latitude, point.longitude]}
              radius={active ? 9 : 6}
              pathOptions={{ color: unavailable ? '#9ca3af' : active ? '#f97316' : '#2563eb', fillColor: '#ffffff', fillOpacity: 1, weight: active ? 4 : 3 }}
              eventHandlers={{ click: () => onSelect(point.stationId) }}
            >
              <Tooltip direction="top" offset={[0, -8]} opacity={1} {...(active ? { permanent: true } : {})} className="station-tooltip">
                <strong>{point.stationName} ({point.stationId})</strong>
                <span>{detail}</span>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      {fogLayer && (
        <button
          type="button"
          className={`fog-layer-toggle${fogVisible ? ' active' : ''}`}
          aria-pressed={fogVisible}
          onClick={() => setFogVisible((visible) => !visible)}
        >
          <i aria-hidden="true" />
          GK2A 분포
        </button>
      )}
      <div className="map-legend" aria-label="지도 범례">
        <span><i className="selected" />선택 ASOS</span>
        <span><i />기타 ASOS</span>
        {fogVisible && fogLayer && FOG_STAGE_LEGEND.map((item) => (
          <span key={item.label}><i className="fog-density" style={{ background: item.background }} />{item.label}</span>
        ))}
      </div>
      {fogVisible && fogLayer && (
        <div className="fog-layer-time">
          {fogLayer.source} · {new Intl.DateTimeFormat('ko-KR', {
            timeZone: 'Asia/Seoul',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          }).format(new Date(fogLayer.observedAt))} KST
        </div>
      )}
    </div>
  );
}
