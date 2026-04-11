import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, test } from 'vitest';
import { modelService } from '@/mocks/services/modelService';
import { ModelDetailPage } from './ModelDetailPage';

function renderModelDetail(pathname = '/models/ladle') {
  const router = createMemoryRouter([{ path: '/models/:modelId', element: <ModelDetailPage /> }], {
    initialEntries: [pathname],
  });
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(async () => {
  localStorage.clear();
  await modelService.reset();
});

test('edits model metadata and saves the update', async () => {
  const user = userEvent.setup();
  renderModelDetail();

  expect(await screen.findByDisplayValue('钢包智能体')).toBeInTheDocument();

  await user.clear(screen.getByLabelText('Title'));
  await user.type(screen.getByLabelText('Title'), '钢包智能体 MVP');
  await user.click(screen.getByRole('button', { name: 'Save' }));

  await waitFor(async () => {
    const updated = await modelService.getByName('ladle');
    expect(updated?.metadata.title).toBe('钢包智能体 MVP');
  });
});

test('keeps invalid intermediate JSON text and shows error state', async () => {
  renderModelDetail();

  expect(await screen.findByDisplayValue('钢包智能体')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('tab', { name: 'Advanced JSON' }));

  const editor = screen.getByLabelText('Derived Properties');
  fireEvent.change(editor, { target: { value: '{' } });

  expect(editor).toHaveValue('{');
  expect(screen.getByText('Fix JSON errors before saving.')).toBeInTheDocument();
});

test('keeps metadata name immutable on detail page', async () => {
  renderModelDetail();

  expect(await screen.findByDisplayValue('钢包智能体')).toBeInTheDocument();
  const nameInput = screen.getByLabelText('Name');
  expect(nameInput).toHaveValue('ladle');
  expect(nameInput).toBeDisabled();
});
