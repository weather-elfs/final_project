import { useEffect, useState } from 'react';

export default function RequestErrorNotice({ message, hasData, busy, onRetry }: {
  message: string;
  hasData: boolean;
  busy: boolean;
  onRetry?: () => void;
}) {
  const [visible, setVisible] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    if (!hasData || detailsOpen) return;
    const timer = window.setTimeout(() => setVisible(false), 8_000);
    return () => window.clearTimeout(timer);
  }, [hasData, detailsOpen]);

  if (!visible) return null;

  return <aside className="dashboard-error-notice" role="alert" aria-label="데이터 요청 오류 안내">
    <div className="error-notice-content">
      <strong>{hasData ? '최신 자료를 갱신하지 못했습니다.' : '자료를 불러오지 못했습니다.'}</strong>
      <p>{hasData ? '기존 자료는 유지됩니다. 잠시 후 다시 시도해주세요.' : onRetry ? '연결 상태를 확인한 뒤 다시 시도해주세요.' : '연결 상태를 확인한 뒤 페이지를 새로고침해주세요.'}</p>
      <details onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
        <summary>오류 상세 보기</summary>
        <p>{message}</p>
      </details>
    </div>
    <div className="error-notice-actions">
      {onRetry && <button type="button" onClick={onRetry} disabled={busy}>다시 시도</button>}
      <button type="button" className="error-notice-close" aria-label="오류 안내 닫기" onClick={() => setVisible(false)}>×</button>
    </div>
  </aside>;
}
