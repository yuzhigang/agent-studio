import { render, screen } from '@testing-library/react';
import App from './App';

test('renders routed app shell with models selected by default', async () => {
  render(<App />);

  expect(await screen.findByRole('link', { name: 'Models' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: 'Models' })).toBeInTheDocument();
});
