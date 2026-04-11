import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the application shell', () => {
  render(<App />);

  expect(screen.getByText('Agent Studio')).toBeInTheDocument();
  expect(screen.getByText('App shell booting')).toBeInTheDocument();
});
