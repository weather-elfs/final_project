import ForecastPanel from './components/ForecastPanel';
import MissionConditionsForm from './components/MissionConditionsForm';
import VisibilitySummary from './components/VisibilitySummary';
import WeatherMap from './components/WeatherMap';
import { formatKst } from './formatters';
import type { DashboardViewProps } from './types';

export default function DashboardView({ config, dashboard, values, loading = false, error = '', onChange, onRefresh, onLogout }: DashboardViewProps) {
  const selectedStation = config.stations.find((station) => station.id === values.stationId);

  return (
    <div className="weather-ui app-shell">
      <aside className="sidebar">
        <div className="brand"><span aria-hidden="true">W</span><strong>기상 데이터 지상국</strong></div>
        <nav aria-label="주 메뉴"><button className="active" type="button"><i aria-hidden="true" />대시보드</button><button type="button"><i aria-hidden="true" />이력</button></nav>
        <div className="sidebar-foot"><strong>인천 연안</strong><span>해양 임무 지원 시안</span><button type="button" onClick={onLogout}>로그아웃</button><small>시스템 v1.0 · 국방기상지원센터</small></div>
      </aside>

      <main className="dashboard-main">
        <header className="page-header">
          <div><p className="breadcrumb">대시보드 / 해양 기상 현황</p><h1>해양 기상 현황</h1><p>인천 연안 · 현재 관측과 예측을 한 화면에서 확인</p></div>
          <div className="header-actions"><div><span>예시 기준 시각</span><strong>{formatKst(dashboard?.meta?.generatedAt)} KST</strong></div><button type="button" onClick={onRefresh} disabled={loading}>자료 갱신</button><button type="button">전광판 보기</button></div>
        </header>

        {error && <div className="page-error" role="alert"><strong>데이터를 불러오지 못했습니다.</strong><span>{error}</span></div>}
        {dashboard?.meta?.partial && <div className="partial-notice" role="status">일부 자료가 지연되었습니다. 사용 가능한 최신 관측과 예측을 표시합니다.</div>}

        <div className={`dashboard-grid${loading ? ' is-loading' : ''}`} aria-busy={loading}>
          <section className="panel map-panel" aria-labelledby="map-title">
            <div className="panel-header"><div><h2 id="map-title">시정 현황 지도</h2><p>{selectedStation?.name ?? '관측소'} · 예측 {values.horizonH}시간</p></div><span className="layer-label">통합 관측</span></div>
            {config.stations.length ? <WeatherMap stations={config.stations} selectedId={values.stationId} selectedVisibilityKm={dashboard?.current?.visibilityKm} onSelect={(stationId) => onChange('stationId', stationId)} /> : <div className="map-placeholder">관측소 설정을 불러오는 중입니다.</div>}
            <div className="map-source"><span>지도: OpenStreetMap</span><span>데이터: 내부 통합 API</span></div>
          </section>
          <VisibilitySummary dashboard={dashboard} horizonH={values.horizonH} />
          <MissionConditionsForm config={config} values={values} loading={loading} onChange={onChange} onSubmit={onRefresh} />
          <ForecastPanel dashboard={dashboard} horizonH={values.horizonH} minimumVisibilityKm={values.minimumVisibilityKm} />
        </div>
      </main>
    </div>
  );
}
