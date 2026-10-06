export type GradeTone = 'green' | 'yellow' | 'orange' | 'red' | 'purple' | 'maroon' | 'neutral';

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
  if (visibilityKm > 10) return { stage: null, label: '안개 없음', rangeLabel: '10 km 초과', tone: 'neutral' };
  if (visibilityKm >= 4) return { stage: 1, label: '옅은 안개', rangeLabel: '4–10 km', tone: 'green' };
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
  const stage = fogGradeByVisibility(visibilityKm).stage;
  return stage ? `${stage}/6단계` : '—/6단계';
}

export function aqiGradeTone(label?: string): GradeTone {
  return label ? AQI_TONES[label] ?? 'neutral' : 'neutral';
}

export function displayAqiGrade(label?: string): string {
  return label === '양호' ? '좋음' : label ?? '판단 대기';
}
