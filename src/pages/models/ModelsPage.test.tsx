import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { modelService } from '@/mocks/services/modelService';
import { ModelsPage } from './ModelsPage';

beforeEach(async () => {
  localStorage.clear();
  await modelService.reset();
});

test('renders models and creates a new model', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter>
      <ModelsPage />
    </MemoryRouter>,
  );

  expect(await screen.findByText('钢包智能体')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'scheduler');
  await user.type(screen.getByLabelText('Title'), '调度智能体');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('调度智能体')).toBeInTheDocument();
});

test('rejects duplicate model name on create', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter>
      <ModelsPage />
    </MemoryRouter>,
  );

  expect(await screen.findByText('钢包智能体')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'ladle');
  await user.type(screen.getByLabelText('Title'), '重复名智能体');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('Model name already exists')).toBeInTheDocument();
});

test('rejects route-hostile model name on create', async () => {
  const user = userEvent.setup();

  render(
    <MemoryRouter>
      <ModelsPage />
    </MemoryRouter>,
  );

  expect(await screen.findByText('钢包智能体')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New Model' }));
  await user.type(screen.getByLabelText('Name'), 'bad/name');
  await user.type(screen.getByLabelText('Title'), '非法路由名');
  await user.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText('Name can only include letters, numbers, "_" and "-"')).toBeInTheDocument();
});
