import { useCallback, useEffect, useState } from 'react';
import type { CampaignDetailDto, CampaignSummaryDto } from '@/entities/campaign';
import { extractErrorInfo, getHealth, isAbortError, listCampaigns } from '@/shared/api';
import { Button } from '@/shared/ui';
import {
  CampaignCreatorWidget,
  CampaignEditorWidget,
  CampaignSidebar,
  type BackendHealthStatus,
} from '@/widgets';

type WorkspaceMode = 'empty' | 'create' | 'detail';

function toSummaryDto(detail: CampaignDetailDto): CampaignSummaryDto {
  return {
    id: detail.id,
    keitaro_campaign_id: detail.keitaro_campaign_id,
    name: detail.name,
    alias: detail.alias,
    geo: detail.geo,
    domain_id: detail.domain_id,
    group_id: detail.group_id,
    source_id: detail.source_id,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

export function DashboardPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummaryDto[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(true);
  const [campaignsError, setCampaignsError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<BackendHealthStatus>('checking');

  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [mode, setMode] = useState<WorkspaceMode>('empty');

  const loadCampaigns = useCallback((signal?: AbortSignal) => {
    setCampaignsLoading(true);
    setCampaignsError(null);

    void listCampaigns(signal)
      .then((items) => {
        setCampaigns(items);
        setCampaignsLoading(false);
        setSelectedCampaignId((prevId) => {
          if (prevId !== null && items.some((c) => c.id === prevId)) {
            return prevId;
          }
          return items[0]?.id ?? null;
        });
        setMode((prevMode) => {
          if (prevMode === 'create') {
            return 'create';
          }
          return items.length > 0 ? 'detail' : 'empty';
        });
      })
      .catch((err: unknown) => {
        if (isAbortError(err)) {
          return;
        }
        setCampaignsError(extractErrorInfo(err, 'Failed to load campaigns.').message);
        setCampaignsLoading(false);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadCampaigns(controller.signal);

    void getHealth(controller.signal)
      .then(() => setHealthStatus('online'))
      .catch((err: unknown) => {
        if (!isAbortError(err)) {
          setHealthStatus('offline');
        }
      });

    return () => {
      controller.abort();
    };
  }, [loadCampaigns]);

  const handleSelectCampaign = (campaignId: number) => {
    setSelectedCampaignId(campaignId);
    setMode('detail');
  };

  const handleNewCampaign = () => {
    setMode('create');
  };

  const handleCampaignCreated = (created: CampaignDetailDto) => {
    const summary = toSummaryDto(created);
    setCampaigns((prev) => [summary, ...prev.filter((item) => item.id !== summary.id)]);
    setSelectedCampaignId(created.id);
    setMode('detail');
  };

  const handleCancelCreate = () => {
    if (selectedCampaignId !== null) {
      setMode('detail');
    } else if (campaigns.length > 0) {
      setSelectedCampaignId(campaigns[0].id);
      setMode('detail');
    } else {
      setMode('empty');
    }
  };

  return (
    <div className="workspace-shell">
      <CampaignSidebar
        campaigns={campaigns}
        isLoading={campaignsLoading}
        error={campaignsError}
        selectedCampaignId={selectedCampaignId}
        isCreating={mode === 'create'}
        healthStatus={healthStatus}
        onSelectCampaign={handleSelectCampaign}
        onNewCampaign={handleNewCampaign}
        onRetry={() => loadCampaigns()}
      />

      <main className="workspace-main">
        {mode === 'create' && (
          <CampaignCreatorWidget
            onCreated={handleCampaignCreated}
            onCancel={campaigns.length > 0 ? handleCancelCreate : undefined}
          />
        )}

        {mode === 'detail' && selectedCampaignId !== null && (
          <CampaignEditorWidget campaignId={selectedCampaignId} />
        )}

        {(mode === 'empty' || (mode === 'detail' && selectedCampaignId === null)) && (
          <section className="empty-workspace" aria-label="Empty workspace">
            <div className="empty-workspace__card">
              <h1 className="empty-workspace__title">No campaigns tracked yet</h1>
              <p className="empty-workspace__subtitle">
                Create your first 2-stream Keitaro campaign (Flow 1 GEO redirect + Flow 2 Offer
                stream) to begin staging offer weights and publishing updates.
              </p>
              <Button variant="primary" size="md" onClick={handleNewCampaign}>
                + Create First Campaign
              </Button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
