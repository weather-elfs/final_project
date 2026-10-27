import type { AlertOperationsData } from './types';

interface AlertOperationsResponse {
  principles?: Array<{ title?: string; description?: string }>;
  rules?: Array<{
    id?: string;
    mission_type?: string;
    trigger_threshold?: string;
    clear_threshold?: string;
    confirmation_duration?: string;
    missing_data_action?: string;
  }>;
  decisions?: Array<{
    id?: string;
    occurred_at?: string;
    status?: string;
    mission?: string;
    reason?: string;
  }>;
}

export function toAlertOperationsData(payload: unknown): AlertOperationsData {
  const data = (payload ?? {}) as AlertOperationsResponse;
  return {
    principles: (data.principles ?? []).map((item) => ({
      title: item.title ?? '',
      description: item.description ?? '',
    })),
    rules: (data.rules ?? []).map((item, index) => ({
      id: item.id ?? `rule-${index}`,
      missionType: item.mission_type ?? '',
      triggerThreshold: item.trigger_threshold ?? '미설정',
      clearThreshold: item.clear_threshold ?? '미설정',
      confirmationDuration: item.confirmation_duration ?? '미설정',
      missingDataAction: item.missing_data_action ?? '판단 불가',
    })),
    decisions: (data.decisions ?? []).map((item, index) => ({
      id: item.id ?? `decision-${index}`,
      occurredAt: item.occurred_at ?? '',
      status: item.status === 'ALERT' || item.status === 'ERROR' ? item.status : 'UNAVAILABLE',
      mission: item.mission ?? '',
      reason: item.reason ?? '',
    })),
  };
}
