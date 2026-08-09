import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from '@/app/App';
import { apiClient } from '@/api/client';
import './index.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('the application root element is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <App client={apiClient} />
  </StrictMode>,
);
