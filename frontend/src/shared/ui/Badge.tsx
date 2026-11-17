import type { ReactNode } from 'react';

export interface BadgeProps {
  variant?: 'success' | 'warning' | 'error' | 'neutral';
  children: ReactNode;
}

export function Badge({ variant = 'neutral', children }: BadgeProps) {
  return <span className={`badge badge--${variant}`}>{children}</span>;
}
