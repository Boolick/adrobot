import { CampaignListItem, type CampaignSummaryDto } from '@/entities/campaign';
import { AlertBanner, Badge, Button, Spinner } from '@/shared/ui';

export type BackendHealthStatus = 'checking' | 'online' | 'offline';

export interface CampaignSidebarProps {
  campaigns: CampaignSummaryDto[];
  isLoading: boolean;
  error: string | null;
  selectedCampaignId: number | null;
  isCreating: boolean;
  healthStatus: BackendHealthStatus;
  onSelectCampaign: (campaignId: number) => void;
  onNewCampaign: () => void;
  onRetry: () => void;
}

function getHealthBadgeVariant(status: BackendHealthStatus): 'success' | 'warning' | 'error' {
  if (status === 'online') {
    return 'success';
  }
  if (status === 'offline') {
    return 'error';
  }
  return 'warning';
}

function getHealthLabel(status: BackendHealthStatus): string {
  if (status === 'online') {
    return 'API Online';
  }
  if (status === 'offline') {
    return 'API Offline';
  }
  return 'Checking API';
}

export function CampaignSidebar({
  campaigns,
  isLoading,
  error,
  selectedCampaignId,
  isCreating,
  healthStatus,
  onSelectCampaign,
  onNewCampaign,
  onRetry,
}: CampaignSidebarProps) {
  return (
    <aside className="workspace-sidebar" aria-label="Tracked campaigns">
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="sidebar-brand__title">Adrobot</span>
          <Badge variant={getHealthBadgeVariant(healthStatus)}>
            {getHealthLabel(healthStatus)}
          </Badge>
        </div>
        <Button
          variant="primary"
          size="md"
          className="sidebar-new-btn"
          onClick={onNewCampaign}
          aria-pressed={isCreating}
        >
          + New Campaign
        </Button>
      </div>

      <div className="sidebar-section-label">
        <span>Campaigns</span>
        <span className="sidebar-count">{campaigns.length}</span>
      </div>

      <div className="sidebar-list">
        {isLoading && (
          <div className="sidebar-state">
            <Spinner size="sm" label="Loading campaigns" />
            <span>Loading campaigns...</span>
          </div>
        )}

        {!isLoading && error && (
          <div className="sidebar-error">
            <AlertBanner variant="error" message={error} />
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}

        {!isLoading && !error && campaigns.length === 0 && (
          <p className="sidebar-empty">
            No tracked campaigns yet. Create one to start staging streams.
          </p>
        )}

        {!isLoading &&
          !error &&
          campaigns.map((campaign) => (
            <CampaignListItem
              key={campaign.id}
              campaign={campaign}
              isSelected={!isCreating && selectedCampaignId === campaign.id}
              onSelect={onSelectCampaign}
            />
          ))}
      </div>
    </aside>
  );
}
