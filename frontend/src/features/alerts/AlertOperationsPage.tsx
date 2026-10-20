import { useEffect, useState } from 'react';

import { getAlertOperations } from '../../api';
import SectionPageHeader from '../shared/SectionPageHeader';
import { toAlertOperationsData } from './alertAdapter';
import type { AlertOperationsData, DecisionRecord } from './types';

const EMPTY_DATA: AlertOperationsData = { principles: [], rules: [], decisions: [] };
const STATUS_PRESENTATION: Record<DecisionRecord['status'], { label: string; tone: string }> = {
  ALERT: { label: '발령', tone: 'danger' },
  UNAVAILABLE: { label: '판단 불가', tone: 'warning' },
  ERROR: { label: '장애', tone: 'danger' },
};

function timeOnly(value: string) {
  return value.includes('T') ? value.slice(11, 19) : value;
}

export default function AlertOperationsPage({ referenceTime }: { referenceTime?: string }) {
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await getAlertOperations({ signal: controller.signal });
        setData(toAlertOperationsData(response.data));
      } catch (requestError) {
        if (!(requestError instanceof Error && requestError.name === 'AbortError')) {
          setError(requestError instanceof Error ? requestError.message : '경보 운영 정보를 불러오지 못했습니다.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  return (
    <main className="workspace-page-main" aria-busy={loading}>
      <SectionPageHeader
        title="경보 운영"
        description="임무별 발령·해제 기준과 확인 지속시간을 사전 확정하고 판단 근거를 기록합니다."
        referenceTime={referenceTime}
      />
      {error && <div className="workspace-error" role="alert">{error}</div>}
      <section className="workspace-card principles-card" aria-labelledby="principles-title">
        <h2 id="principles-title">경보 운영 원칙</h2>
        <div className="principle-grid">
          {data.principles.map((principle) => (
            <article key={principle.title}>
              <strong>{principle.title}</strong>
              <span>{principle.description}</span>
            </article>
          ))}
        </div>
      </section>
      <div className="alert-layout">
        <section className="workspace-card alert-rules-card" aria-labelledby="alert-rules-title">
          <h2 id="alert-rules-title">임무별 경보 기준</h2>
          <p className="workspace-caption">운영 기준 확정 전 상태를 표시합니다. 실제 임계값은 승인 후 입력합니다.</p>
          <div className="workspace-table-scroll">
            <table className="workspace-table alert-rules-table">
              <thead><tr><th>임무 유형</th><th>발령 임계값</th><th>해제 임계값</th><th>확인 지속시간</th><th>결측 처리</th></tr></thead>
              <tbody>
                {data.rules.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.missionType}</td><td>{rule.triggerThreshold}</td><td>{rule.clearThreshold}</td><td>{rule.confirmationDuration}</td><td className="warning-text">{rule.missingDataAction}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="notice-card"><strong>운영 적용 전 확인</strong><span>임계값·해제 조건·확인 지속시간은 임무 책임자의 승인 이후 활성화합니다.</span></aside>
          <div className="rule-actions">
            <button type="button" disabled title="백엔드 운영 API 연동 후 사용할 수 있습니다.">기준 편집</button>
            <button type="button" className="primary" disabled title="백엔드 운영 API 연동 후 사용할 수 있습니다.">승인 요청</button>
          </div>
        </section>
        <section className="workspace-card decision-log-card" aria-labelledby="decision-log-title">
          <h2 id="decision-log-title">최근 판단 기록</h2>
          <p className="workspace-caption">발령·해제 시각과 판단 근거를 함께 보관합니다.</p>
          <div className="decision-list">
            {data.decisions.map((decision) => {
              const presentation = STATUS_PRESENTATION[decision.status];
              return (
                <article key={decision.id}>
                  <div><time dateTime={decision.occurredAt}>{timeOnly(decision.occurredAt)}</time><span className={`status-badge ${presentation.tone}`}>{presentation.label}</span></div>
                  <strong>{decision.mission}</strong>
                  <p>{decision.reason}</p>
                </article>
              );
            })}
          </div>
          <aside className="notice-card compact"><strong>결측 처리 원칙</strong><span>결측 발생 시 기존 경보를 자동 해제하지 않고 ‘판단 불가’로 기록합니다.</span></aside>
        </section>
      </div>
    </main>
  );
}
