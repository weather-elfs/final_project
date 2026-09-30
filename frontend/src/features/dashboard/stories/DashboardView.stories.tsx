import type { Meta, StoryObj } from '@storybook/react-vite';

import DashboardView from '../DashboardView';
import { config, dashboard, noop, values } from './storyData';

const meta = { title: 'Dashboard/DashboardView', component: DashboardView, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof DashboardView>;
export default meta;
type Story = StoryObj<typeof meta>;

const defaultArgs = { config, dashboard, values, onChange: noop, onRefresh: noop, onLogout: noop };
export const Default: Story = { args: defaultArgs };
export const PartialData: Story = { args: { ...defaultArgs, dashboard: { ...dashboard, meta: { ...dashboard.meta, partial: true }, current: { ...dashboard.current, pm25UgM3: null } } } };
export const Loading: Story = { args: { ...defaultArgs, dashboard: null, loading: true } };
export const Error: Story = { args: { ...defaultArgs, dashboard: null, error: '관측 데이터를 불러오지 못했습니다. (요청 ID: story-error)' } };
