export interface DashboardStation {
  id: string;
  name: string;
  stationId: string;
  stationName: string;
  latitude: number;
  longitude: number;
  available: boolean;
}

export interface MissionType {
  missionType: string;
  displayName: string;
  enabled: boolean;
  ruleVersion: string | null;
  requiredMetrics: string[];
}

export interface DashboardConfig {
  stations: DashboardStation[];
  forecastHorizonsH: number[];
  missionTypes: MissionType[];
  meta?: { requestId?: string; partial?: boolean };
}

export interface MissionValues {
  stationId: string;
  horizonH: number;
  missionType: string;
  minimumVisibilityKm: number;
}

export type MissionValueKey = keyof MissionValues;
export type MissionValue = MissionValues[MissionValueKey];

export interface CurrentConditions {
  observedAt?: string;
  status?: string;
  visibilityKm?: number | null;
  pm25UgM3?: number | null;
  pm10UgM3?: number | null;
  relativeHumidityPct?: number | null;
  temperatureDewpointSpreadC?: number | null;
}

export interface ForecastPoint {
  validAt?: string;
  status?: string;
  visibilityPredKm?: number | null;
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
  selectedForecast?: ForecastPoint;
  history?: Array<{ observedAt?: string; visibilityKm?: number | null }>;
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
  apiStatus?: { overall?: { code?: string; label?: string } };
  meta?: { requestId?: string; generatedAt?: string; partial?: boolean };
}

export interface DashboardViewProps {
  config: DashboardConfig;
  dashboard: DashboardData | null;
  values: MissionValues;
  loading?: boolean;
  error?: string;
  onChange: (key: MissionValueKey, value: MissionValue) => void;
  onRefresh: () => void;
  onLogout: () => void;
}
