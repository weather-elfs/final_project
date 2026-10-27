export const statusLabels: Record<string, string> = {
  fresh: '최신', delayed: '지연', missing: '누락', ready: '준비', stale: '오래됨', failed: '실패',
};

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function formatKst(value?: string) {
  if (!value) return '시각 정보 없음';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}

export function formatKstDate(value?: string) {
  if (!value) return '시각 정보 없음';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(value)).replaceAll(' ', '').replace(/\.$/, '');
}

export function formatKstTime(value?: string) {
  if (!value) return '--:--:--';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(value));
}

export function isKstRefreshImminent(value?: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return false;

  const timeParts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Seoul', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(new Date(value));
  const minute = Number(timeParts.find((part) => part.type === 'minute')?.value);
  const second = Number(timeParts.find((part) => part.type === 'second')?.value);

  return minute === 59 && second >= 50;
}

export function metric(value: number | null | undefined, unit: string, digits = 0) {
  return isFiniteNumber(value) ? `${value.toFixed(digits)} ${unit}` : '자료 없음';
}
