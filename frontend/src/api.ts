const SUCCESS_CODES = new Set(['SUCCESS', 'PARTIAL_SUCCESS']);

export interface ApiEnvelope<T> {
  code: string;
  message?: string;
  data: T;
  meta?: { request_id?: string };
}

interface ApiErrorOptions {
  code?: string;
  data?: unknown;
  requestId?: string | null;
  status?: number;
}

export interface DashboardRequest {
  stationId: string;
  forecastIntervalH: number;
  missionType: string;
}

export interface MapViewport {
  west: number;
  south: number;
  east: number;
  north: number;
  zoom: number;
}

export class ApiError extends Error {
  code: string;
  data: unknown;
  requestId: string | null;
  status: number;

  constructor(message: string, { code = 'REQUEST_FAILED', data = null, requestId = null, status = 0 }: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.data = data;
    this.requestId = requestId;
    this.status = status;
  }
}

export async function request<T>(url: string, options: RequestInit = {}): Promise<ApiEnvelope<T>> {
  const { signal = AbortSignal.timeout(10_000), ...fetchOptions } = options;
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...fetchOptions,
    signal,
    headers: { Accept: 'application/json', ...fetchOptions.headers },
  });

  let payload: ApiEnvelope<T>;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('서버 응답 형식을 확인할 수 없습니다.', {
      code: 'INVALID_RESPONSE',
      status: response.status,
    });
  }

  if (!response.ok || !SUCCESS_CODES.has(payload?.code)) {
    const errorData = payload?.data as { meta?: { request_id?: string } } | null;
    throw new ApiError(payload?.message || '요청을 처리하지 못했습니다.', {
      code: payload?.code,
      data: payload?.data,
      requestId: errorData?.meta?.request_id ?? payload?.meta?.request_id ?? null,
      status: response.status,
    });
  }

  return payload;
}

export function buildDashboardUrl({ stationId, forecastIntervalH, missionType }: DashboardRequest) {
  const query = new URLSearchParams({
    forecast_interval_h: String(forecastIntervalH),
    mission_type: missionType,
  });

  return `/api/v1/stations/${encodeURIComponent(stationId)}/dashboard?${query}`;
}

export function login(centerId: string, password: string, options?: RequestInit) {
  return request<{ center: { id: string; name: string } }>('/api/v1/auth/login', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    body: JSON.stringify({ center_id: centerId, password }),
  });
}

export function getDashboardConfig(options?: RequestInit) {
  return request<unknown>('/api/v1/dashboard/config', options);
}

export function getDashboard(params: DashboardRequest, options?: RequestInit) {
  return request<unknown>(buildDashboardUrl(params), options);
}
