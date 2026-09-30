export type GradeTone = 'green' | 'yellow' | 'orange' | 'red' | 'purple' | 'maroon' | 'neutral';

const FOG_TONES: Record<string, GradeTone> = {
  박무: 'yellow',
  '안개 가능': 'purple',
  안개: 'purple',
  '짙은 안개': 'maroon',
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

export function aqiGradeTone(label?: string): GradeTone {
  return label ? AQI_TONES[label] ?? 'neutral' : 'neutral';
}

export function displayAqiGrade(label?: string): string {
  return label === '양호' ? '좋음' : label ?? '판단 대기';
}
