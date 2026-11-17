import { Badge } from '@/shared/ui';
import type { CampaignSummaryDto } from '../model/types';

export interface CampaignListItemProps {
  campaign: CampaignSummaryDto;
  isSelected: boolean;
  onSelect: (campaignId: number) => void;
}

export function CampaignListItem({ campaign, isSelected, onSelect }: CampaignListItemProps) {
  return (
    <button
      type="button"
      className={`sidebar-item ${isSelected ? 'sidebar-item--active' : ''}`.trim()}
      onClick={() => onSelect(campaign.id)}
      aria-current={isSelected ? 'page' : undefined}
    >
      <div className="sidebar-item__top">
        <span className="sidebar-item__name" title={campaign.name}>
          {campaign.name}
        </span>
        <Badge variant={isSelected ? 'accent' : 'neutral'}>
          KT #{campaign.keitaro_campaign_id}
        </Badge>
      </div>
      <div className="sidebar-item__meta">
        {campaign.alias && <span className="sidebar-item__alias">/{campaign.alias}</span>}
        <span className="sidebar-item__geos">
          {campaign.geo.length > 0 ? campaign.geo.join(', ') : 'No GEO'}
        </span>
      </div>
    </button>
  );
}
