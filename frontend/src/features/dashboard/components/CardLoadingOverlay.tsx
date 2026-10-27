export default function CardLoadingOverlay({ label }: { label: string }) {
  return <div className="card-loading-overlay" role="status">
    <span className="loading-spinner" aria-hidden="true" />
    <strong>{label}</strong>
  </div>;
}
