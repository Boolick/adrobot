import type { CampaignDetailDto } from '@/entities/campaign';
import { CreateCampaignForm } from '@/features/create-campaign';

export interface CampaignCreatorWidgetProps {
  onCreated: (campaign: CampaignDetailDto) => void;
  onCancel?: () => void;
}

export function CampaignCreatorWidget({ onCreated, onCancel }: CampaignCreatorWidgetProps) {
  return (
    <div className="workspace-panel">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span>Campaigns</span>
        <span className="breadcrumbs__sep">/</span>
        <span className="breadcrumbs__current">New Campaign</span>
      </nav>

      <header className="panel-header">
        <div>
          <h1 className="panel-title">Create Campaign</h1>
          <p className="panel-subtitle">
            Creates a Keitaro campaign with Flow 1 (GEO redirect) and Flow 2 (default offer at 100%
            share).
          </p>
        </div>
      </header>

      <section className="surface-card">
        <CreateCampaignForm onCreated={onCreated} onCancel={onCancel} />
      </section>
    </div>
  );
}
