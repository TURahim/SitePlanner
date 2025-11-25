/**
 * Application entry point
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { configureAmplify } from './lib/amplify';
import App from './App';
import './index.css';

// Initialize Amplify before rendering
configureAmplify();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
