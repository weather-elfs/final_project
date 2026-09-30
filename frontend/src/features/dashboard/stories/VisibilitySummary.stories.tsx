import type { Meta, StoryObj } from '@storybook/react-vite';

import VisibilitySummary from '../components/VisibilitySummary';
import { dashboard } from './storyData';

const meta = { title: 'Dashboard/Components/VisibilitySummary', component: VisibilitySummary } satisfies Meta<typeof VisibilitySummary>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Complete: Story = { args: { dashboard, horizonH: 6 } };
export const ModerateGrades: Story = { args: { dashboard: { ...dashboard, diagnosis: { ...dashboard.diagnosis, fogLabel: '박무', pmDisplayGrade: '보통' } }, horizonH: 6 } };
export const SevereGrades: Story = { args: { dashboard: { ...dashboard, diagnosis: { ...dashboard.diagnosis, fogLabel: '짙은 안개', pmDisplayGrade: '매우 나쁨' } }, horizonH: 6 } };
export const MissingMetrics: Story = { args: { dashboard: { ...dashboard, current: { ...dashboard.current, pm25UgM3: null, pm10UgM3: null }, diagnosis: null }, horizonH: 6 } };
