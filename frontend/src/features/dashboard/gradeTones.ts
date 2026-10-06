export type GradeTone = 'green' | 'yellow' | 'orange' | 'red' | 'purple' | 'maroon' | 'neutral';

const FOG_TONES: Record<string, GradeTone> = {
  '옅은 안개': 'green',
  '안개 가능': 'yellow',
  박무: 'orange',
  안개: 'red',
  '짙은 안개': 'purple',
  '매우 짙은 안개': 'maroon',
};

const FOG_STAGES: Record<string, number> = {
  '옅은 안개': 1,
  '안개 가능': 2,
  박무: 3,
  안개: 4,
  '짙은 안개': 5,
  '매우 짙은 안개': 6,
};

const AQI_TONES: Record<string, GradeTone> = {
  좋음: 'green',
  양호: 'green',
  보통: 'orange',
  나쁨: 'red',
  '매우 나쁨': 'maroon',
};

export function fogGradeTone(label?: string): GradeTone {
  return label ? FOG_TONES[label] ?? 'neutral' : 'neutral';
}

export function fogStageLabel(label?: string): string {
  const stage = label ? FOG_STAGES[label] : undefined;
  return stage ? `${stage}/6단계` : '—/6단계';
}

export function aqiGradeTone(label?: string): GradeTone {
  return label ? AQI_TONES[label] ?? 'neutral' : 'neutral';
}

export function displayAqiGrade(label?: string): string {
  return label === '양호' ? '좋음' : label ?? '판단 대기';
}
