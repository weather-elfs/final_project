import type { Meta, StoryObj } from '@storybook/react-vite';

import { handlers } from '../../../mocks/handlers';
import DashboardPage from '../DashboardPage';
import { noop } from './storyData';

const meta = { title: 'Dashboard/Integration/DashboardPage', component: DashboardPage, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof DashboardPage>;
export default meta;
type Story = StoryObj<typeof meta>;
export const MockedApi: Story = {
  args: { mapTilesEnabled: false, onUnauthorized: noop },
  beforeEach({ msw }) { msw.use(...handlers); },
};
