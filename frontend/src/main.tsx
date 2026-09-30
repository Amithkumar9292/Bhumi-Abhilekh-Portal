import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';

import './design-system/tokens.css';
import './design-system/reset.css';
import './design-system/animations.css';
import './index.css';

import { I18nProvider } from './i18n/useTranslation';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>
);
