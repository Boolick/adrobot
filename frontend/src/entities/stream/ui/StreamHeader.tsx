import type { ReactNode } from 'react';
import { Badge } from '@/shared/ui';
import type { StreamDto } from '../model/types';

export interface StreamHeaderProps {
  stream: StreamDto;
  actions?: ReactNode;
}

export function StreamHeader({ stream, actions }: StreamHeaderProps) {
  return (
    <div className="stream-header">
      <div className="stream-header__title-group">
        <span className="stream-header__position">#{stream.position}</span>
        <h3 className="stream-header__name">{stream.name}</h3>
        <Badge variant="neutral">KT #{stream.keitaro_stream_id}</Badge>
        {!stream.has_offers && <Badge variant="neutral">Read-only · No Offers</Badge>}
        {stream.has_offers && stream.is_dirty && (
          <Badge variant="warning">Unpublished changes</Badge>
        )}
      </div>
      {actions && <div className="stream-header__actions">{actions}</div>}
    </div>
  );
}
