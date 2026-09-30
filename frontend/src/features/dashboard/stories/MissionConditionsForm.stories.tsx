import type { Meta, StoryObj } from '@storybook/react-vite';

import MissionConditionsForm from '../components/MissionConditionsForm';
import { config, noop, values } from './storyData';

const meta = { title: 'Dashboard/Components/MissionConditionsForm', component: MissionConditionsForm } satisfies Meta<typeof MissionConditionsForm>;
export default meta;
type Story = StoryObj<typeof meta>;
const defaultArgs = { config, values, loading: false, onChange: noop, onSubmit: noop };
export const Default: Story = { args: defaultArgs };
export const Submitting: Story = { args: { ...defaultArgs, loading: true } };
