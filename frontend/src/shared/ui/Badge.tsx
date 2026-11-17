import type { ReactNode } from 'react';

export interface BadgeProps {
  variant?: 'neutral' | 'success' | 'warning' | 'error' | 'accent';
  className?: string;
  children: ReactNode;
}

export function Badge({ variant = 'neutral', className = '', children }: BadgeProps) {
  const classes = ['badge', `badge--${variant}`, className].filter(Boolean).join(' ');
  return <span className={classes}>{children}</span>;
}
