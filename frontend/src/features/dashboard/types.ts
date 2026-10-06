import type { MapViewport } from '../../api';

export interface DashboardStation {
  id: string;
  name: string;
  stationId: string;
  stationName: string;
  latitude: number;
  longitude: number;
  available: boolean;
  currentStatus?: string;
  forecastStatus?: string;
}

export interface MissionType {
  missionType: string;
  displayName: string;
  enabled: boolean;
  ruleVersion: string | null;
  requiredMetrics: string[];
}

export interface FogLayerCell {
  id: string;
  fogClass: number;
  positions: Array<[number, number]>;
}

export interface FogLayerLegendItem {
  value: number;
  label: string;
  color: string;
}

export interface FogMapLayer {
  source: string;
  observedAt: string;
  projection: string;
  resolutionKm: number;
  quality: {
    field: string;
    acceptedValues: number[];
  };
  legend: FogLayerLegendItem[];
  cells: FogLayerCell[];
}

export interface DashboardConfig {
  stations: DashboardStation[];
  forecastIntervalOptionsH: number[];
  missionTypes: MissionType[];
  fogLayer?: FogMapLayer;
  meta?: { requestId?: string; generatedAt?: string; partial?: boolean };
}

export interface MissionValues {
  stationId: string;
  forecastIntervalH: number | '';
  missionType: string;
}

export type MissionValueKey = keyof MissionValues;
export type MissionValue = MissionValues[MissionValueKey];

export interface CurrentConditions {
  observedAt?: string;
  status?: string;
  visibilityKm?: number | null;
  pm1UgM3?: number | null;
  pm25UgM3?: number | null;
  pm10UgM3?: number | null;
  temperatureC?: number | null;
  windDirectionDeg?: number | null;
  windDirectionLabel?: string;
  windSpeedMS?: number | null;
  weatherLabel?: string;
  fogGradeLabel?: string;
  aqi?: { value?: number | null; displayLevel?: number; displayGrade?: string; status?: string };
  relativeHumidityPct?: number | null;
  temperatureDewpointSpreadC?: number | null;
}

export interface ForecastPoint {
  validAt?: string;
  horizonH?: number;
  status?: string;
  visibilityPredKm?: number | null;
  temperatureC?: number | null;
  windDirectionLabel?: string;
  windSpeedMS?: number | null;
  weatherLabel?: string;
  fogGradeLabel?: string;
  aqi?: { value?: number | null; displayLevel?: number; displayGrade?: string; status?: string };
}

export interface MissionFactor {
  actual: number;
  unit: string;
  operator: string;
  threshold: number;
  passed?: boolean;
}

export interface DashboardData {
  station?: { stationId?: string; stationName?: string };
  current?: CurrentConditions;
  forecastTimeline?: ForecastPoint[];
  missionEvaluation?: {
    evaluationStatus?: string;
    passed?: boolean;
    missionGrade?: string | null;
    factors?: MissionFactor[];
    ruleVersion?: string;
  };
  diagnosis?: { fogLabel?: string; pmDisplayGrade?: string; summary?: string } | null;
  sourceStatus?: Array<{ source: string; status: string; observedAt?: string }>;
  apiStatus?: {
    overall?: { code?: string; label?: string };
    summary?: { good?: number; delayed?: number; fail?: number };
    sources?: Array<{ source?: string; displayName?: string; code?: string; label?: string }>;
  };
  meta?: { requestId?: string; generatedAt?: string; partial?: boolean };
}

export interface DashboardMapPoint {
  stationId: string;
  stationName: string;
  latitude: number;
  longitude: number;
  validAt?: string;
  visibilityKm?: number | null;
  fogGradeCode?: string;
  status: string;
}

export interface DashboardViewProps {
  config: DashboardConfig;
  missionStations: DashboardStation[];
  dashboard: DashboardData | null;
  mapMode: 'current' | 'forecast';
  mapTilesEnabled?: boolean;
  values: MissionValues;
  forecastRequested?: boolean;
  loading?: boolean;
  error?: string;
  onChange: (key: MissionValueKey, value: MissionValue) => void;
  onMapModeChange: (mode: 'current' | 'forecast') => void;
  onMapViewportChange: (viewport: MapViewport) => void;
  onStationSelect: (stationId: string) => void;
  onRefresh: () => void;
  onSubmit: () => void;
}
