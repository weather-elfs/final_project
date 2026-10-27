import type { Meta, StoryObj } from '@storybook/react-vite';

import ForecastPanel from '../components/ForecastPanel';
import { dashboard } from './storyData';

const meta = { title: 'Dashboard/Components/ForecastPanel', component: ForecastPanel } satisfies Meta<typeof ForecastPanel>;
export default meta;
type Story = StoryObj<typeof meta>;
const base = { dashboard, requested: true, loading: false };
export const Empty: Story = { args: { dashboard, requested: false, loading: false } };
export const Passed: Story = { args: base };
export const Failed: Story = { args: { ...base, dashboard: { ...dashboard, missionEvaluation: { ...dashboard.missionEvaluation, passed: false, missionGrade: 'RESTRICTED' } } } };
export const NotEvaluable: Story = { args: { ...base, dashboard: { ...dashboard, missionEvaluation: { evaluationStatus: 'NOT_EVALUABLE', missionGrade: null, factors: [] } } } };

export const StageBadges: Story = {
  args: {
    ...base,
    dashboard: {
      ...dashboard,
      requestContext: { ...dashboard.requestContext, forecastIntervalH: 3 },
      forecastSummary: undefined,
      forecastTimeline: [
        { weatherLabel: '흐림', temperatureC: 17, windDirectionLabel: '북서풍', windSpeedMS: 4, visibilityPredKm: 4.6, aqi: { status: 'calculated', value: 125 } },
        { weatherLabel: '박무', temperatureC: 17, windDirectionLabel: '서북서풍', windSpeedMS: 3.8, visibilityPredKm: 4.1, aqi: { status: 'calculated', value: 175 } },
        { weatherLabel: '안개', temperatureC: 16, windDirectionLabel: '서풍', windSpeedMS: 3.2, visibilityPredKm: 3.7, aqi: { status: 'calculated', value: 180 } },
        { weatherLabel: '흐림', temperatureC: 16, windDirectionLabel: '남서풍', windSpeedMS: 2.7, visibilityPredKm: 4.3, aqi: { status: 'calculated', value: 130 } },
      ].map((point, index) => ({ ...point, horizonH: (index + 1) * 3, validAt: `2026-10-27T${12 + index * 3}:00:00+09:00` })),
    },
  },
};
