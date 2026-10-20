export const alertOperationsFixture = {
  code: 'SUCCESS',
  message: '경보 운영 설정과 최근 판단 기록을 조회했습니다.',
  data: {
    principles: [
      { title: '기준 사전 확정', description: '임무별 발령·해제 임계값과 확인 지속시간을 운영 전에 확정' },
      { title: '결측 분리', description: '결측은 해제가 아닌 ‘판단 불가’ 상태로 별도 구분' },
      { title: '근거 기록', description: '발생·해제 시각과 각 판단에 사용한 근거를 함께 기록' },
    ],
    rules: [
      { id: 'rule-1', mission_type: '해양 수송·보급', trigger_threshold: '미설정', clear_threshold: '미설정', confirmation_duration: '미설정', missing_data_action: '판단 불가' },
      { id: 'rule-2', mission_type: '항공 작전', trigger_threshold: '미설정', clear_threshold: '미설정', confirmation_duration: '미설정', missing_data_action: '판단 불가' },
      { id: 'rule-3', mission_type: '감시·정찰', trigger_threshold: '미설정', clear_threshold: '미설정', confirmation_duration: '미설정', missing_data_action: '판단 불가' },
    ],
    decisions: [
      { id: 'decision-1', occurred_at: '2026-09-18T09:05:00+09:00', status: 'ALERT', mission: '해양 수송·보급', reason: '시정 기준이 확인 지속시간 동안 충족됨' },
      { id: 'decision-2', occurred_at: '2026-09-18T08:42:00+09:00', status: 'UNAVAILABLE', mission: '대기질 보조 판단', reason: '에어코리아 23분째 미수신' },
      { id: 'decision-3', occurred_at: '2026-09-18T08:40:00+09:00', status: 'ERROR', mission: '위성 자료', reason: '천리안 응답 시간 초과' },
    ],
    meta: { request_id: 'req_alert_operations_20260918', generated_at: '2026-09-18T09:05:00+09:00' },
  },
};

export const historyRecords = [
  {
    id: 'history-1', occurred_at: '2026-09-18T09:05:00+09:00', type: 'ALERT', target: '해양 수송·보급', status: 'ALERTED', summary: '시정 기준이 확인 지속시간 동안 충족됨', mission: '해양 수송·보급', mission_type: 'MARITIME_TRANSPORT', released_at: null, data_status: '정상', reason: '시정 기준이 확인 지속시간 동안 충족됨', explanation: '결측이 발생하면 해제 대신 ‘판단 불가’로 전환하며, 복구 후 다시 기준을 평가합니다.',
  },
  {
    id: 'history-2', occurred_at: '2026-09-18T08:42:00+09:00', type: 'INCIDENT', target: '에어코리아', status: 'DELAYED', summary: '23분째 미수신 · 최종 관측 08:42:00', mission: '대기질 보조 판단', mission_type: 'MARITIME_TRANSPORT', released_at: '2026-09-18T09:11:00+09:00', data_status: '지연', reason: '에어코리아 관측 자료가 23분 동안 갱신되지 않음', explanation: '자료가 다시 수신되면 최신성 기준을 재평가해 상태를 정상으로 전환합니다.',
  },
  {
    id: 'history-3', occurred_at: '2026-09-18T08:40:00+09:00', type: 'INCIDENT', target: '천리안', status: 'ERROR', summary: '응답 시간 초과 · 최종 관측 08:40:00', mission: '위성 자료', mission_type: 'MARITIME_TRANSPORT', released_at: null, data_status: '오류', reason: '천리안 응답 시간 초과', explanation: '응답 실패는 관측값으로 대체하지 않고 장애 이력으로 분리해 기록합니다.',
  },
  {
    id: 'history-4', occurred_at: '2026-09-18T08:30:00+09:00', type: 'RESULT', target: '시간대별 예측', status: 'COMPLETED', summary: '+9시간 시정 최저 3.7 km · 2/6단계', mission: '해양 수송·보급', mission_type: 'MARITIME_TRANSPORT', released_at: null, data_status: '정상', reason: '+9시간 시정 최저 3.7 km · 2/6단계', explanation: '선택한 간격의 네 시점 중 시정이 가장 낮은 결과를 대표값으로 기록합니다.',
  },
] as const;
