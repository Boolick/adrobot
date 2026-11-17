import type { ReactNode } from 'react';
import { Badge } from '@/shared/ui';
import type { StreamOfferDto } from '../model/types';
import { PinIcon } from './PinIcon';

export interface OfferRowProps {
  offer: StreamOfferDto;
  pinControl?: ReactNode;
  shareControl?: ReactNode;
  actions?: ReactNode;
}

export function OfferRow({ offer, pinControl, shareControl, actions }: OfferRowProps) {
  const isRemoved = offer.status === 'removed';

  return (
    <div className={`offer-row ${isRemoved ? 'offer-row--removed' : ''}`.trim()}>
      <div className="offer-row__main">
        <span className="offer-row__id">#{offer.keitaro_offer_id}</span>
        <span className="offer-row__name">{offer.offer_name}</span>
        {isRemoved && <Badge variant="neutral">removed</Badge>}
        {!isRemoved && !offer.is_published && <Badge variant="accent">draft</Badge>}
      </div>

      <div className="offer-row__controls">
        {shareControl ?? (
          <Badge variant={isRemoved ? 'neutral' : 'accent'} className="offer-row__share">
            {isRemoved ? '0%' : `${offer.share}%`}
          </Badge>
        )}

        {!isRemoved &&
          (pinControl ?? (
            <span
              className={`pin-indicator ${offer.is_pinned ? 'pin-indicator--active' : ''}`.trim()}
              title={offer.is_pinned ? 'Pinned share' : 'Unpinned'}
            >
              <PinIcon filled={offer.is_pinned} />
            </span>
          ))}

        {actions && <div className="offer-row__actions">{actions}</div>}
      </div>
    </div>
  );
}
