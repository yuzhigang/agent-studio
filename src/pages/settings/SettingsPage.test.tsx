import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsPage } from './SettingsPage';

test('resets local model and instance data', async () => {
  const user = userEvent.setup();
  localStorage.setItem(
    'agent-studio/models/v1',
    JSON.stringify([{ metadata: { name: 'temp', title: 'Temp' }, attributes: {}, variables: {} }]),
  );
  localStorage.setItem(
    'agent-studio/instances/v1',
    JSON.stringify([{ id: 'temp_instance', modelId: 'temp', state: 'idle', metadata: { name: 'temp_instance', title: 'Temp' } }]),
  );

  render(<SettingsPage />);

  await user.click(screen.getByRole('button', { name: 'Reset Local Data' }));

  await waitFor(() => {
    const models = JSON.parse(localStorage.getItem('agent-studio/models/v1') ?? '[]') as Array<{ metadata?: { name?: string } }>;
    const instances = JSON.parse(localStorage.getItem('agent-studio/instances/v1') ?? '[]') as Array<{ id?: string }>;
    expect(models.some((model) => model.metadata?.name === 'temp')).toBe(false);
    expect(models.some((model) => model.metadata?.name === 'ladle')).toBe(true);
    expect(instances.some((instance) => instance.id === 'temp_instance')).toBe(false);
    expect(instances.some((instance) => instance.id === 'ladle_001')).toBe(true);
  });
});
