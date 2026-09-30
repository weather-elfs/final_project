import { dashboardConfig, dashboardFixture } from '../../../mocks/fixtures';
import { toDashboardConfig, toViewModel } from '../dashboardAdapter';
import type { DashboardData, MissionValues } from '../types';

export const config = toDashboardConfig(dashboardConfig.data);
export const dashboard = toViewModel<DashboardData>(dashboardFixture('112', 6, 1)?.data);
export const values: MissionValues = { stationId: '112', horizonH: 6, missionType: 'MARITIME_TRANSPORT', minimumVisibilityKm: 1 };
export const noop = () => {};
