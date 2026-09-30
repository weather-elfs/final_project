import type { Meta, StoryObj } from '@storybook/react-vite';

import ForecastPanel from '../components/ForecastPanel';
import { dashboard } from './storyData';

const meta = { title: 'Dashboard/Components/ForecastPanel', component: ForecastPanel } satisfies Meta<typeof ForecastPanel>;
export default meta;
type Story = StoryObj<typeof meta>;
const base = { dashboard, horizonH: 6, minimumVisibilityKm: 1 };
export const Passed: Story = { args: base };
export const Failed: Story = { args: { ...base, dashboard: { ...dashboard, missionEvaluation: { ...dashboard.missionEvaluation, passed: false, missionGrade: 'RESTRICTED' } } } };
export const NotEvaluable: Story = { args: { ...base, dashboard: { ...dashboard, missionEvaluation: { evaluationStatus: 'NOT_EVALUABLE', missionGrade: null, factors: [] } } } };
