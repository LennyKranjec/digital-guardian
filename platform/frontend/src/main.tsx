import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import './index.css';
import { loadChallengePlugins } from './plugins';
import './shared/i18n';

loadChallengePlugins();

const container = document.getElementById('root');
if (!container) throw new Error('#root fehlt in index.html');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
