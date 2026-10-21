import { useCallback, useEffect, useState } from 'react';

import { getHistory } from '../../api';
import { DEMO_MODE } from '../../demo';
import SectionPageHeader from '../shared/SectionPageHeader';
import { HISTORY_TYPE_LABELS, toHistoryData } from './historyAdapter';
import type { HistoryData, HistoryRecord, HistoryType } from './types';

const EMPTY_DATA: HistoryData = { records: [], total: 0 };
const STATUS_LABELS: Record<HistoryRecord['status'], string> = { ALERTED: '발령', DELAYED: '지연', ERROR: '오류', COMPLETED: '완료' };
const STATUS_TONES: Record<HistoryRecord['status'], string> = { ALERTED: 'danger-text', DELAYED: 'warning-text', ERROR: 'danger-text', COMPLETED: 'success-text' };

function dateTimeParts(value: string) {
  if (!value.includes('T')) return { date: value, time: '' };
  return { date: value.slice(0, 10).replaceAll('-', '.'), time: value.slice(11, 19) };
}

export default function HistoryPage({ referenceTime }: { referenceTime?: string }) {
  const [historyType, setHistoryType] = useState<HistoryType>('ALL');
  const [missionType, setMissionType] = useState('ALL');
  const [data, setData] = useState(EMPTY_DATA);
  const [selectedId, setSelectedId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (type = historyType, mission = missionType, signal?: AbortSignal) => {
    setLoading(true);
    setError('');
    try {
      const response = await getHistory({ historyType: type, missionType: mission }, { signal });
      const nextData = toHistoryData(response.data);
      setData(nextData);
      setSelectedId((current) => nextData.records.some((record) => record.id === current) ? current : nextData.records[0]?.id ?? '');
    } catch (requestError) {
      if (!(requestError instanceof Error && requestError.name === 'AbortError')) {
        setError(requestError instanceof Error ? requestError.message : '이력을 불러오지 못했습니다.');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [historyType, missionType]);

  useEffect(() => {
    const controller = new AbortController();
    void load('ALL', 'ALL', controller.signal);
    return () => controller.abort();
  }, []);

  const selected = data.records.find((record) => record.id === selectedId) ?? data.records[0];
  const selectedDateTime = selected ? dateTimeParts(selected.occurredAt) : null;
  const releaseDateTime = selected?.releasedAt ? dateTimeParts(selected.releasedAt) : null;

  return (
    <main className="workspace-page-main" aria-busy={loading}>
      <SectionPageHeader
        title="이력 조회"
        description={DEMO_MODE ? '시연용 샘플 이력입니다. 실제 기상 조회 결과나 운영 기록을 저장·조회하지 않습니다.' : '결과·경보·장애 이력을 조회하고 상세 판단 근거를 확인합니다.'}
        referenceTime={referenceTime}
      />
      {error && <div className="workspace-error" role="alert">{error}</div>}
      <section className="workspace-card history-filter-card" aria-label="이력 조회 조건">
        <label>이력 유형<select value={historyType} onChange={(event) => setHistoryType(event.target.value as HistoryType)}><option value="ALL">전체 · 결과 · 경보 · 장애</option><option value="RESULT">결과</option><option value="ALERT">경보</option><option value="INCIDENT">장애</option></select></label>
        <label>조회 기간<input value="2026.09.18 00:00–23:59" readOnly /></label>
        <label>임무 유형<select value={missionType} onChange={(event) => setMissionType(event.target.value)}><option value="ALL">전체 임무</option><option value="MARITIME_TRANSPORT">해양 수송·보급</option></select></label>
        <span className="filter-spacer" />
        <button type="button" onClick={() => void load()} disabled={loading}>{loading ? '조회 중' : '조회'}</button>
        <button type="button" className="primary" disabled title="백엔드 내보내기 API 연동 후 사용할 수 있습니다.">XLSX 다운로드</button>
      </section>
      <div className="history-layout">
        <section className="workspace-card history-table-card" aria-labelledby="history-table-title">
          <h2 id="history-table-title">운영 이력</h2>
          <p className="workspace-caption">총 {data.total}건 · 시각은 KST 기준</p>
          <div className="workspace-table-scroll">
            <table className="workspace-table history-table">
              <thead><tr><th>발생 시각</th><th>유형</th><th>대상</th><th>상태</th><th>요약</th></tr></thead>
              <tbody>
                {data.records.map((record) => {
                  const occurredAt = dateTimeParts(record.occurredAt);
                  return (
                    <tr key={record.id} className={record.id === selected?.id ? 'selected' : ''} tabIndex={0} aria-selected={record.id === selected?.id} onClick={() => setSelectedId(record.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedId(record.id); }}>
                      <td><time dateTime={record.occurredAt}><span>{occurredAt.date}</span><span>{occurredAt.time}</span></time></td>
                      <td>{HISTORY_TYPE_LABELS[record.type]}</td><td>{record.target}</td><td className={STATUS_TONES[record.status]}>{STATUS_LABELS[record.status]}</td><td>{record.summary}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <nav className="pagination" aria-label="이력 페이지"><button type="button" className="active" aria-current="page">1</button><button type="button">2</button><button type="button">3</button></nav>
        </section>
        <aside className="workspace-card history-detail-card" aria-labelledby="history-detail-title">
          <h2 id="history-detail-title">상세 판단 근거</h2>
          {selected ? (
            <>
              <span className={`detail-badge ${STATUS_TONES[selected.status]}`}>{HISTORY_TYPE_LABELS[selected.type]} · {STATUS_LABELS[selected.status]}</span>
              <dl>
                <div><dt>임무</dt><dd>{selected.mission}</dd></div>
                <div><dt>발생 시각</dt><dd>{selectedDateTime?.date} {selectedDateTime?.time} KST</dd></div>
                <div><dt>해제 시각</dt><dd>{releaseDateTime ? `${releaseDateTime.date} ${releaseDateTime.time} KST` : '—'}</dd></div>
                <div><dt>데이터 상태</dt><dd>{selected.dataStatus}</dd></div>
                <div className="reason"><dt>판단 근거</dt><dd>{selected.reason}</dd></div>
              </dl>
              <div className="explanation-note"><strong>설명</strong><span>{selected.explanation}</span></div>
            </>
          ) : <p className="history-empty">조건에 맞는 이력이 없습니다.</p>}
        </aside>
      </div>
    </main>
  );
}
