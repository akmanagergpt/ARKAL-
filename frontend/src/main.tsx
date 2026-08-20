import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from '@/app/App';
import { DesktopBootBoundary } from '@/app/DesktopBootBoundary';
import { apiClient, isTauriRuntime } from '@/api/client';
import './index.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('the application root element is missing from index.html');
}

const commandCenter = <App client={apiClient} />;

createRoot(container).render(
  <StrictMode>
    {isTauriRuntime()
      ? <DesktopBootBoundary client={apiClient}>{commandCenter}</DesktopBootBoundary>
      : commandCenter}
  </StrictMode>,
);
