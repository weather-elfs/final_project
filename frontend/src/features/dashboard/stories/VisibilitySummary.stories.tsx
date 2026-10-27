import type { Meta, StoryObj } from '@storybook/react-vite';

import VisibilitySummary from '../components/VisibilitySummary';
import { dashboard } from './storyData';

const meta = { title: 'Dashboard/Components/VisibilitySummary', component: VisibilitySummary } satisfies Meta<typeof VisibilitySummary>;
export default meta;
type Story = StoryObj<typeof meta>;
const actions = { loading: false, onRefresh: () => {} };
export const Complete: Story = { args: { dashboard, ...actions } };
export const ModerateGrades: Story = { args: { dashboard: { ...dashboard, current: { ...dashboard.current, visibilityKm: 1.4 }, diagnosis: { ...dashboard.diagnosis, pmDisplayGrade: '보통' } }, ...actions } };
export const SevereGrades: Story = { args: { dashboard: { ...dashboard, current: { ...dashboard.current, visibilityKm: 0.3 }, diagnosis: { ...dashboard.diagnosis, pmDisplayGrade: '매우 나쁨' } }, ...actions } };
export const MissingMetrics: Story = { args: { dashboard: { ...dashboard, current: { ...dashboard.current, pm25UgM3: null, pm10UgM3: null }, diagnosis: null }, ...actions } };
