import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import LegacyApp from './App';
import AppV2 from './v2/App';
import reportWebVitals from './reportWebVitals';

const useV2 = process.env.REACT_APP_UI_VERSION === 'v2';
const RootApp = useV2 ? AppV2 : LegacyApp;

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <RootApp />
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
