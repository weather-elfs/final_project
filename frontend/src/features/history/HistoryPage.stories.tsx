import type { Meta, StoryObj } from '@storybook/react-vite';

import { handlers } from '../../mocks/handlers';
import HistoryPage from './HistoryPage';

const meta = { title: 'Operations/HistoryPage', component: HistoryPage, parameters: { layout: 'fullscreen' } } satisfies Meta<typeof HistoryPage>;
export default meta;
type Story = StoryObj<typeof meta>;
export const MockedApi: Story = {
  args: { referenceTime: '2026-09-18T09:05:00+09:00' },
  beforeEach({ msw }) { msw.use(...handlers); },
};
