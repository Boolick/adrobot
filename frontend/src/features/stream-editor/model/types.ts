import type { CampaignDetailDto } from '@/entities/campaign';
import type { StreamDto } from '@/entities/stream';

export type EditorStatus =
  'idle' | 'loading' | 'ready' | 'dirty_valid' | 'dirty_invalid' | 'saving' | 'error';

export type MutationActionKind =
  | 'FETCH_STREAMS'
  | 'ADD_OFFER'
  | 'REMOVE_OFFER'
  | 'BRING_BACK_OFFER'
  | 'TOGGLE_PIN'
  | 'REBALANCE_STREAM'
  | 'CANCEL_CHANGES'
  | 'PUSH_TO_KT';

export interface PendingEditorAction {
  kind: MutationActionKind;
  streamId?: number;
  offerId?: number;
}

export interface EditorErrorInfo {
  message: string;
  code?: string;
  details?: Record<string, string> | null;
}

export interface StreamEditorState {
  status: EditorStatus;
  selectedCampaignId: number | null;
  campaign: CampaignDetailDto | null;
  pendingAction: PendingEditorAction | null;
  loadError: EditorErrorInfo | null;
  actionError: EditorErrorInfo | null;
}

export type StreamEditorAction =
  | { type: 'RESET_EDITOR' }
  | { type: 'LOAD_CAMPAIGN_START'; campaignId: number }
  | { type: 'LOAD_CAMPAIGN_SUCCESS'; campaignId: number; campaign: CampaignDetailDto }
  | { type: 'LOAD_CAMPAIGN_FAILURE'; campaignId: number; error: EditorErrorInfo }
  | { type: 'FETCH_STREAMS' }
  | { type: 'ADD_OFFER'; streamId: number; offerId: number }
  | { type: 'REMOVE_OFFER'; streamId: number; offerId: number }
  | { type: 'BRING_BACK_OFFER'; streamId: number; offerId: number }
  | { type: 'TOGGLE_PIN'; streamId: number; offerId: number }
  | { type: 'REBALANCE_STREAM'; streamId: number }
  | { type: 'CANCEL_CHANGES'; streamId: number }
  | { type: 'PUSH_TO_KT'; streamId: number }
  | { type: 'FETCH_STREAMS_SUCCESS'; campaignId: number; campaign: CampaignDetailDto }
  | { type: 'STREAM_MUTATION_SUCCESS'; campaignId: number; stream: StreamDto }
  | { type: 'MUTATION_FAILURE'; campaignId: number; error: EditorErrorInfo }
  | { type: 'DISMISS_ACTION_ERROR' };
