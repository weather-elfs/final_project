import { formatKstDate, formatKstTime } from '../dashboard/formatters';

interface SectionPageHeaderProps {
  title: string;
  description: string;
  referenceTime?: string;
}

export default function SectionPageHeader({ title, description, referenceTime }: SectionPageHeaderProps) {
  const hasReferenceTime = Boolean(referenceTime && Number.isFinite(Date.parse(referenceTime)));

  return (
    <header className="section-page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <strong>{hasReferenceTime ? `현재 시각 ${formatKstDate(referenceTime)} ${formatKstTime(referenceTime)} KST` : '현재 시각 --:--:-- KST'}</strong>
    </header>
  );
}
