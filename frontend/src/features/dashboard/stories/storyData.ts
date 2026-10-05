import { dashboardConfig, dashboardFixture } from '../../../mocks/fixtures';
import { toDashboardConfig, toViewModel } from '../dashboardAdapter';
import type { DashboardData, MissionValues } from '../types';

export const config = toDashboardConfig(dashboardConfig.data);
export const dashboard = toViewModel<DashboardData>(dashboardFixture('112', 6)?.data);
export const values: MissionValues = { stationId: '', forecastIntervalH: '', missionType: '' };
export const noop = () => {};
