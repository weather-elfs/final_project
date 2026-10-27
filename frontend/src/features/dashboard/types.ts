import type { MapViewport } from '../../api';

export type StationCurrentStatus = 'GOOD' | 'DELAYED' | 'MISSING' | 'UNAVAILABLE' | 'UNKNOWN';
export type StationForecastStatus = 'GOOD' | 'DELAYED' | 'NOT_AVAILABLE' | 'UNKNOWN';

export interface DashboardStation {
  id: string;
  name: string;
  stationId: string;
  stationName: string;
  latitude: number;
  longitude: number;
  available: boolean;
  currentStatus: StationCurrentStatus;
  forecastStatus: StationForecastStatus;
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
  aqi?: { value?: number | null; displayLevel?: number | null; displayGrade?: string | null; status?: string; basis?: string; standard?: string };
  relativeHumidityPct?: number | null;
  temperatureDewpointSpreadC?: number | null;
}

export interface ForecastPoint {
  validAt?: string;
  horizonH?: number;
  status?: string;
  missingSources?: string[];
  missingFeatures?: string[];
  unavailableTargets?: string[];
  reason?: string;
  visibilityPredKm?: number | null;
  visibilityGrade?: string;
  pm25PredUgM3?: number | null;
  pm10PredUgM3?: number | null;
  temperatureC?: number | null;
  windDirectionLabel?: string;
  windSpeedMS?: number | null;
  weatherLabel?: string;
  fogGradeLabel?: string;
  aqi?: { value?: number | null; displayLevel?: number; displayGrade?: string; status?: string };
}

export interface MissionFactor {
  metric?: string;
  actual: number | null;
  unit: string;
  operator: string;
  threshold: number;
  required?: boolean;
  passed?: boolean | null;
}

export interface RequestContext {
  forecastIntervalH?: number;
  forecastHorizonsH?: number[];
  missionType?: string;
}

export interface ForecastSummary extends ForecastPoint {
  selectionReason?: string;
}

export interface SourceStatusDetail {
  source: string;
  status: string;
  observedAt?: string | null;
  issuedAt?: string | null;
  collectedAt?: string | null;
  ageMinutes?: number | null;
  reason?: string | null;
}

export interface MarineConditions {
  source?: string;
  stationName?: string;
  observedAt?: string;
  waterTemperatureC?: number | null;
  salinityPsu?: number | null;
  airTemperatureC?: number | null;
  airPressureHpa?: number | null;
  windSpeedMS?: number | null;
  windDirectionDeg?: number | null;
  gustSpeedMS?: number | null;
  waveHeightM?: number | null;
  significantWaveHeightM?: number | null;
  averageWaveHeightM?: number | null;
  wavePeriodS?: number | null;
}

export interface DashboardData {
  station?: { stationId?: string; stationName?: string };
  requestContext?: RequestContext;
  current?: CurrentConditions;
  marine?: MarineConditions | null;
  forecastTimeline?: ForecastPoint[];
  forecastSummary?: ForecastSummary | null;
  missionEvaluation?: {
    missionType?: string;
    evaluationStatus?: string;
    passed?: boolean | null;
    missionGrade?: string | null;
    factors?: MissionFactor[];
    ruleVersion?: string;
    reasonCodes?: string[];
  };
  diagnosis?: { fogLabel?: string; pmDisplayGrade?: string; summary?: string } | null;
  sourceStatus?: SourceStatusDetail[];
  apiStatus?: {
    overall?: { code?: string; label?: string };
    summary?: { good?: number; delayed?: number; fail?: number };
    sources?: Array<{ source?: string; displayName?: string; code?: string; label?: string }>;
  };
  meta?: {
    requestId?: string; generatedAt?: string; partial?: boolean; mock?: boolean;
    model?: { missingFeatures?: string[]; originAt?: string };
    collection?: {
      id: string;
      expiresAt?: string;
      errors?: Record<string, string>;
      retryableSources?: string[];
      modelInputObservedAt?: Record<string, string | null>;
      fetchedAt?: Record<string, string>;
    };
  };
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
  centerId?: string;
  config: DashboardConfig;
  missionStations: DashboardStation[];
  dashboard: DashboardData | null;
  mapMode: 'current' | 'forecast';
  mapTilesEnabled?: boolean;
  values: MissionValues;
  forecastRequested?: boolean;
  forecastLoading?: boolean;
  loading?: boolean;
  error?: string;
  onChange: (key: MissionValueKey, value: MissionValue) => void;
  onMapModeChange: (mode: 'current' | 'forecast') => void;
  onMapViewportChange: (viewport: MapViewport) => void;
  onStationSelect: (stationId: string) => void;
  onRefresh: () => void;
  onRetrySource?: (source: string) => void;
  retryingSource?: string | null;
  onSubmit: () => void;
  onLogout?: () => void;
}
