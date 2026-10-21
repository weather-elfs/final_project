export type GradeTone = 'sky' | 'green' | 'yellow' | 'orange' | 'red' | 'purple' | 'maroon' | 'neutral';

export interface FogGradePresentation {
  stage: number | null;
  label: string;
  rangeLabel: string;
  tone: GradeTone;
}

const PENDING_FOG_GRADE: FogGradePresentation = {
  stage: null,
  label: '판단 대기',
  rangeLabel: '자료 없음',
  tone: 'neutral',
};

export function fogGradeByVisibility(visibilityKm?: number | null): FogGradePresentation {
  if (visibilityKm == null || !Number.isFinite(visibilityKm) || visibilityKm < 0) return PENDING_FOG_GRADE;
  if (visibilityKm >= 10) return { stage: null, label: '안개 없음', rangeLabel: '10 km 이상', tone: 'sky' };
  if (visibilityKm >= 4) return { stage: 1, label: '옅은 안개', rangeLabel: '4–10 km 미만', tone: 'green' };
  if (visibilityKm >= 2) return { stage: 2, label: '옅은 안개', rangeLabel: '2–4 km', tone: 'yellow' };
  if (visibilityKm >= 1) return { stage: 3, label: '안개', rangeLabel: '1–2 km', tone: 'orange' };
  if (visibilityKm >= 0.5) return { stage: 4, label: '안개', rangeLabel: '500 m–1 km', tone: 'red' };
  if (visibilityKm >= 0.2) return { stage: 5, label: '짙은 안개', rangeLabel: '200–500 m', tone: 'purple' };
  return { stage: 6, label: '짙은 안개', rangeLabel: '200 m 미만', tone: 'maroon' };
}

const AQI_TONES: Record<string, GradeTone> = {
  좋음: 'green',
  양호: 'green',
  보통: 'orange',
  나쁨: 'red',
  '매우 나쁨': 'maroon',
};

export function fogGradeTone(visibilityKm?: number | null): GradeTone {
  return fogGradeByVisibility(visibilityKm).tone;
}

export function fogStageLabel(visibilityKm?: number | null): string {
  const grade = fogGradeByVisibility(visibilityKm);
  return grade.stage ? `${grade.stage}/6단계` : grade.label === '안개 없음' ? '안개 없음' : '—/6단계';
}

export function aqiGradeTone(label?: string): GradeTone {
  return label ? AQI_TONES[label] ?? 'neutral' : 'neutral';
}

export function displayAqiGrade(label?: string): string {
  return label === '양호' ? '좋음' : label ?? '판단 대기';
}

export interface AirQualityPresentation {
  value: number | null;
  stage: number | null;
  label: string;
  tone: GradeTone;
}

export const AIR_QUALITY_CRITERIA = [
  { stage: 1, maxValue: 100, label: '양호', range: 'AQI 0–100', tone: 'green' },
  { stage: 2, maxValue: 150, label: '민감군 주의', range: 'AQI 101–150', tone: 'orange' },
  { stage: 3, maxValue: 200, label: '나쁨', range: 'AQI 151–200', tone: 'red' },
  { stage: 4, maxValue: 300, label: '매우 나쁨', range: 'AQI 201–300', tone: 'purple' },
  { stage: 5, maxValue: Infinity, label: '위험', range: 'AQI 301 이상', tone: 'maroon' },
] as const;

type ParticleBreakpoint = readonly [concentrationLow: number, concentrationHigh: number, indexLow: number, indexHigh: number];

// EPA / AirNow, May 2026, Table 6 and Equation 1:
// https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf
// API 값의 평균 기간은 보장되지 않으므로 공식 AQI가 아닌 PM 기반 추정값에만 사용한다.
const PM25_BREAKPOINTS: readonly ParticleBreakpoint[] = [
  [0, 9, 0, 50],
  [9.1, 35.4, 51, 100],
  [35.5, 55.4, 101, 150],
  [55.5, 125.4, 151, 200],
  [125.5, 225.4, 201, 300],
  [225.5, 325.4, 301, 500],
];

const PM10_BREAKPOINTS: readonly ParticleBreakpoint[] = [
  [0, 54, 0, 50],
  [55, 154, 51, 100],
  [155, 254, 101, 150],
  [255, 354, 151, 200],
  [355, 424, 201, 300],
  [425, 604, 301, 500],
];

function particleIndex(concentration: number | null | undefined, precision: number, breakpoints: readonly ParticleBreakpoint[]): number | null {
  if (concentration == null || !Number.isFinite(concentration) || concentration < 0) return null;
  const scaled = concentration * precision;
  if (!Number.isFinite(scaled)) return null;
  // 버림할 때 부동소수점 오차로 소수 한 자리가 낮아지는 것을 방지한다.
  const truncated = Math.trunc(scaled + Number.EPSILON * scaled) / precision;
  const interval = breakpoints.find(([min, max]) => truncated >= min && truncated <= max)
    ?? breakpoints[breakpoints.length - 1];
  if (!interval) return null;
  const [low, high, indexLow, indexHigh] = interval;
  const value = Math.round((indexHigh - indexLow) / (high - low) * (truncated - low) + indexLow);
  return Number.isFinite(value) ? value : null;
}

export function airQualityByParticles(pm25UgM3?: number | null, pm10UgM3?: number | null): AirQualityPresentation {
  const pm25Index = particleIndex(pm25UgM3, 10, PM25_BREAKPOINTS);
  const pm10Index = particleIndex(pm10UgM3, 1, PM10_BREAKPOINTS);
  if (pm25Index == null || pm10Index == null) {
    return { value: null, stage: null, label: '판단 대기', tone: 'neutral' };
  }
  const value = Math.max(pm25Index, pm10Index);
  const grade = AIR_QUALITY_CRITERIA.find((item) => value <= item.maxValue)!;
  return { value, stage: grade.stage, label: grade.label, tone: grade.tone };
}
