import {
  StreamCard,
  isEditorBusy,
  useStreamEditor,
  type EditorStatus,
} from '@/features/stream-editor';
import { AlertBanner, Badge, Button, Spinner } from '@/shared/ui';

export interface CampaignEditorWidgetProps {
  campaignId: number;
}

const KEITARO_CAMPAIGN_BASE_URL = 'https://tlgk.host/admin/#!/campaigns';

function getEditorStatusBadge(status: EditorStatus): {
  label: string;
  variant: 'neutral' | 'success' | 'warning' | 'error' | 'accent';
} {
  switch (status) {
    case 'dirty_valid':
      return { label: 'Staged changes ready', variant: 'warning' };
    case 'dirty_invalid':
      return { label: 'Validation required', variant: 'error' };
    case 'saving':
      return { label: 'Syncing...', variant: 'accent' };
    case 'ready':
      return { label: 'Synced', variant: 'success' };
    default:
      return { label: status, variant: 'neutral' };
  }
}

export function CampaignEditorWidget({ campaignId }: CampaignEditorWidgetProps) {
  const { state, commands } = useStreamEditor(campaignId);

  if (state.status === 'loading' || (state.status === 'idle' && state.campaign === null)) {
    return (
      <div className="panel-loading">
        <Spinner size="md" label="Loading campaign streams" />
        <span>Loading campaign and staged streams...</span>
      </div>
    );
  }

  if (state.status === 'error' || state.campaign === null) {
    return (
      <div className="workspace-panel">
        <AlertBanner
          variant="error"
          title="Unable to load campaign"
          code={state.loadError?.code}
          message={state.loadError?.message ?? 'Campaign could not be loaded.'}
          details={state.loadError?.details}
        />
        <div>
          <Button variant="secondary" onClick={commands.reloadCampaign}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const { campaign } = state;
  const isBusy = isEditorBusy(state.status);
  const isFetchingStreams = state.pendingAction?.kind === 'FETCH_STREAMS';
  const hasDirtyStream = campaign.streams.some((stream) => stream.is_dirty);
  const statusBadge = getEditorStatusBadge(state.status);

  const handleFetchFromKt = () => {
    if (isBusy) {
      return;
    }
    if (hasDirtyStream) {
      const confirmed = window.confirm(
        'One or more streams have unsaved local edits. Fetching streams from Keitaro will overwrite those staged changes. Continue?',
      );
      if (!confirmed) {
        return;
      }
    }
    void commands.fetchStreamsFromKt();
  };

  return (
    <div className="workspace-panel">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <span>Campaigns</span>
        <span className="breadcrumbs__sep">/</span>
        <span>{campaign.name}</span>
        <span className="breadcrumbs__sep">/</span>
        <span className="breadcrumbs__current">Keitaro Streams</span>
      </nav>

      <header className="panel-header">
        <div className="panel-header__info">
          <div className="panel-header__title-row">
            <h1 className="panel-title">{campaign.name}</h1>
            <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
          </div>
          <div className="campaign-meta">
            <Badge variant="neutral">KT #{campaign.keitaro_campaign_id}</Badge>
            {campaign.alias && (
              <span className="campaign-meta__alias">
                Alias: <code>/{campaign.alias}</code>
              </span>
            )}
            <div className="campaign-meta__geos" aria-label="Target GEO countries">
              {campaign.geo.map((code) => (
                <Badge key={code} variant="accent">
                  {code}
                </Badge>
              ))}
            </div>
          </div>
        </div>

        <div className="panel-header__actions">
          <Button
            variant="secondary"
            size="md"
            disabled={isBusy}
            isLoading={isFetchingStreams}
            onClick={handleFetchFromKt}
          >
            FETCH STREAMS FROM KT
          </Button>
          <a
            href={`${KEITARO_CAMPAIGN_BASE_URL}/${campaign.keitaro_campaign_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn--ghost btn--md"
          >
            VIEW IN KT ↗
          </a>
        </div>
      </header>

      {state.actionError && (
        <AlertBanner
          variant="error"
          title="Stream operation failed"
          code={state.actionError.code}
          message={state.actionError.message}
          details={state.actionError.details}
          onDismiss={commands.dismissActionError}
        />
      )}

      <div className="streams-list">
        {campaign.streams.length === 0 ? (
          <section className="surface-card">
            <p className="empty-hint">
              No local streams found. Click <strong>FETCH STREAMS FROM KT</strong> to sync from
              Keitaro.
            </p>
          </section>
        ) : (
          campaign.streams.map((stream) => (
            <StreamCard
              key={stream.id}
              stream={stream}
              isBusy={isBusy}
              pendingAction={state.pendingAction}
              onAddOffer={commands.addOffer}
              onRemoveOffer={commands.removeOffer}
              onBringBackOffer={commands.bringBackOffer}
              onTogglePin={commands.togglePin}
              onCancelChanges={commands.cancelChanges}
              onPushToKt={commands.pushToKt}
            />
          ))
        )}
      </div>
    </div>
  );
}
