export interface AlertBannerProps {
  variant?: 'error' | 'warning' | 'info' | 'success';
  title?: string;
  message: string;
  code?: string;
  details?: Record<string, string> | null;
  action?: React.ReactNode;
  onDismiss?: () => void;
}

export function AlertBanner({
  variant = 'error',
  title,
  message,
  code,
  details,
  action,
  onDismiss,
}: AlertBannerProps) {
  const detailEntries = details ? Object.entries(details) : [];

  return (
    <div
      className={`alert alert--${variant}`}
      role={variant === 'error' || variant === 'warning' ? 'alert' : 'status'}
    >
      <div className="alert__content">
        <div className="alert__header">
          {title && <strong className="alert__title">{title}</strong>}
          {code && <code className="alert__code">{code}</code>}
        </div>
        <p className="alert__message">{message}</p>
        {detailEntries.length > 0 && (
          <ul className="alert__details">
            {detailEntries.map(([key, val]) => (
              <li key={key}>
                <code>{key}</code>: {val}
              </li>
            ))}
          </ul>
        )}
      </div>
      {action && <div className="alert__action">{action}</div>}
      {onDismiss && (
        <button
          type="button"
          className="alert__dismiss"
          onClick={onDismiss}
          aria-label="Dismiss notification"
        >
          ✕
        </button>
      )}
    </div>
  );
}
