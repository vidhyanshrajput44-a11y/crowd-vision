import React, { Component, ErrorInfo, ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class RootErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('CrowdVision RootErrorBoundary caught an error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#070B14] text-red-400 p-8 font-mono">
          <div className="max-w-3xl mx-auto bg-slate-900/90 border border-red-500/30 rounded-xl p-6 shadow-2xl">
            <h1 className="text-xl font-bold text-red-400 mb-2">CrowdVision Initialization Error</h1>
            <p className="text-xs text-slate-300 mb-4">
              A frontend rendering error occurred. Details below:
            </p>
            <pre className="bg-black/60 p-4 rounded-lg text-xs text-red-300 overflow-auto whitespace-pre-wrap mb-4">
              {this.state.error?.toString()}
              {'\n\n'}
              {this.state.error?.stack}
            </pre>
            {this.state.errorInfo?.componentStack && (
              <pre className="bg-black/40 p-4 rounded-lg text-[11px] text-slate-400 overflow-auto whitespace-pre-wrap">
                {this.state.errorInfo.componentStack}
              </pre>
            )}
            <button
              onClick={() => {
                localStorage.clear();
                window.location.reload();
              }}
              className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold transition-colors"
            >
              Clear Local Storage & Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// Global unhandled error fallback
window.addEventListener('error', (event) => {
  const root = document.getElementById('root');
  if (root && root.innerHTML.trim() === '') {
    const box = document.createElement('div');
    box.style.cssText = 'padding: 24px; color: #f87171; background: #070B14; font-family: monospace; min-height: 100vh;';
    box.innerHTML = `<h1 style="font-size: 18px; font-weight: bold; margin-bottom: 8px;">Window Runtime Error</h1><pre style="background: rgba(0,0,0,0.5); padding: 16px; border-radius: 8px; white-space: pre-wrap;">${event.message}\n${event.filename}:${event.lineno}</pre>`;
    document.body.appendChild(box);
  }
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>,
);
