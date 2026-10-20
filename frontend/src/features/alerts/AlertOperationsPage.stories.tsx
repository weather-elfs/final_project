import type { Meta, StoryObj } from '@storybook/react-vite';

import { handlers } from '../../mocks/handlers';
import AlertOperationsPage from './AlertOperationsPage';

const meta = { title: 'Operations/AlertOperationsPage', component: AlertOperationsPage, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof AlertOperationsPage>;
export default meta;
type Story = StoryObj<typeof meta>;
export const MockedApi: Story = {
  args: { referenceTime: '2026-09-18T09:05:00+09:00' },
  beforeEach({ msw }) { msw.use(...handlers); },
};
