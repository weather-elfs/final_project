import { useEffect } from 'react';
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

import type { DashboardStation } from '../types';
import { isFiniteNumber } from '../formatters';

interface WeatherMapProps {
  stations: DashboardStation[];
  selectedId: string;
  selectedVisibilityKm?: number | null;
  onSelect: (stationId: string) => void;
}

function MapFocus({ station }: { station?: DashboardStation }) {
  const map = useMap();

  useEffect(() => {
    if (station) map.flyTo([station.latitude, station.longitude], 9, { duration: 0.5 });
  }, [map, station]);

  return null;
}

export default function WeatherMap({ stations, selectedId, selectedVisibilityKm, onSelect }: WeatherMapProps) {
  const selected = stations.find((station) => station.id === selectedId) ?? stations[0];

  return (
    <div className="map-frame">
      <MapContainer center={[37.58, 125.75]} zoom={8} minZoom={6} maxZoom={13} className="map-canvas">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapFocus station={selected} />
        {stations.map((station) => {
          const active = station.id === selectedId;
          return (
            <CircleMarker
              key={station.id}
              center={[station.latitude, station.longitude]}
              radius={active ? 11 : 7}
              pathOptions={{ color: active ? '#ff6817' : '#0a5da8', fillColor: '#ffffff', fillOpacity: 1, weight: active ? 4 : 3 }}
              eventHandlers={{ click: () => onSelect(station.id) }}
            >
              <Tooltip direction="top" offset={[0, -8]} opacity={1} className="station-tooltip">
                <strong>{station.name}</strong>
                {active && isFiniteNumber(selectedVisibilityKm) ? ` · ${selectedVisibilityKm.toFixed(1)} km` : ''}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <p className="map-caption">관측소를 선택하면 통합 대시보드 API를 다시 조회합니다.</p>
    </div>
  );
}
