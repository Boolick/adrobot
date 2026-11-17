import { useEffect, useState } from 'react';
import { getHealth, type HealthResponse } from '@/shared/api/client';
import { Badge } from '@/shared/ui';

type HealthStatus = 'checking' | 'connected' | 'disconnected';

function getBadgeVariant(status: HealthStatus): 'success' | 'error' | 'warning' {
  if (status === 'connected') {
    return 'success';
  }
  if (status === 'disconnected') {
    return 'error';
  }
  return 'warning';
}

function getBadgeLabel(status: HealthStatus): string {
  if (status === 'checking') {
    return 'Checking...';
  }
  if (status === 'connected') {
    return 'Backend Online';
  }
  return 'Backend Offline';
}

export function DashboardPage() {
  const [status, setStatus] = useState<HealthStatus>('checking');
  const [data, setData] = useState<HealthResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const checkHealth = async () => {
    setStatus('checking');
    setErrorMessage(null);
    try {
      const result = await getHealth();
      setData(result);
      setStatus('connected');
    } catch (err) {
      setStatus('disconnected');
      setErrorMessage(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  useEffect(() => {
    void checkHealth();
  }, []);

  return (
    <main className="app-container">
      <header className="header">
        <h1 className="header-title">Adrobot Dashboard</h1>
        <div className="status-row">
          <Badge variant={getBadgeVariant(status)}>{getBadgeLabel(status)}</Badge>
          <button type="button" className="btn" onClick={() => void checkHealth()}>
            Refresh
          </button>
        </div>
      </header>

      <section className="card">
        <h2 className="card-title">Backend Connectivity</h2>
        <p className="card-description">
          Health check via OpenAPI contract-defined <code>GET /health</code> endpoint.
        </p>

        <div className="status-row">
          <span>Status:</span>
          <strong>{status}</strong>
        </div>

        {data && (
          <div style={{ marginTop: '1rem' }}>
            <span>Response: </span>
            <code>{JSON.stringify(data)}</code>
          </div>
        )}

        {errorMessage && (
          <div style={{ marginTop: '1rem', color: 'var(--color-error)' }}>
            <span>Error: </span>
            <code>{errorMessage}</code>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card-title">Architecture Skeleton</h2>
        <p className="card-description">
          Feature-Sliced Design (FSD) architecture initialized with Vite, React 19, TypeScript, Zod,
          and strict ESLint boundaries.
        </p>
      </section>
    </main>
  );
}
