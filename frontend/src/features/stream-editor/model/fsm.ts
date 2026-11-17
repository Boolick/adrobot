import type { CampaignDetailDto } from '@/entities/campaign';
import type { StreamDto } from '@/entities/stream';
import type {
  EditorStatus,
  MutationActionKind,
  StreamEditorAction,
  StreamEditorState,
} from './types';

export const INITIAL_STREAM_EDITOR_STATE: StreamEditorState = {
  status: 'idle',
  selectedCampaignId: null,
  campaign: null,
  pendingAction: null,
  loadError: null,
  actionError: null,
};

export function deriveEditorStatus(
  campaign: CampaignDetailDto,
): 'ready' | 'dirty_valid' | 'dirty_invalid' {
  const editableStreams = campaign.streams.filter((stream) => stream.has_offers);

  if (editableStreams.some((stream) => stream.is_dirty && !stream.can_push)) {
    return 'dirty_invalid';
  }
  if (editableStreams.some((stream) => stream.is_dirty && stream.can_push)) {
    return 'dirty_valid';
  }
  return 'ready';
}

export function isEditorBusy(status: EditorStatus): boolean {
  return status === 'loading' || status === 'saving';
}

function replaceStreamInCampaign(
  campaign: CampaignDetailDto,
  updatedStream: StreamDto,
): CampaignDetailDto {
  const exists = campaign.streams.some((stream) => stream.id === updatedStream.id);
  const nextStreams = exists
    ? campaign.streams.map((stream) => (stream.id === updatedStream.id ? updatedStream : stream))
    : [...campaign.streams, updatedStream];

  nextStreams.sort((a, b) => a.position - b.position || a.id - b.id);
  return { ...campaign, streams: nextStreams };
}

function startMutation(
  state: StreamEditorState,
  kind: MutationActionKind,
  streamId?: number,
  offerId?: number,
): StreamEditorState {
  if (isEditorBusy(state.status) || state.status === 'idle' || state.status === 'error') {
    return state;
  }
  if (state.campaign === null) {
    return state;
  }

  return {
    ...state,
    status: 'saving',
    pendingAction: { kind, streamId, offerId },
    actionError: null,
  };
}

export function streamEditorReducer(
  state: StreamEditorState,
  action: StreamEditorAction,
): StreamEditorState {
  switch (action.type) {
    case 'RESET_EDITOR':
      return INITIAL_STREAM_EDITOR_STATE;

    case 'LOAD_CAMPAIGN_START':
      return {
        status: 'loading',
        selectedCampaignId: action.campaignId,
        campaign: null,
        pendingAction: null,
        loadError: null,
        actionError: null,
      };

    case 'LOAD_CAMPAIGN_SUCCESS':
      if (state.selectedCampaignId !== action.campaignId) {
        return state;
      }
      return {
        status: deriveEditorStatus(action.campaign),
        selectedCampaignId: action.campaignId,
        campaign: action.campaign,
        pendingAction: null,
        loadError: null,
        actionError: null,
      };

    case 'LOAD_CAMPAIGN_FAILURE':
      if (state.selectedCampaignId !== action.campaignId) {
        return state;
      }
      return {
        status: 'error',
        selectedCampaignId: action.campaignId,
        campaign: null,
        pendingAction: null,
        loadError: action.error,
        actionError: null,
      };

    case 'FETCH_STREAMS':
      return startMutation(state, 'FETCH_STREAMS');

    case 'ADD_OFFER':
      return startMutation(state, 'ADD_OFFER', action.streamId, action.offerId);

    case 'REMOVE_OFFER':
      return startMutation(state, 'REMOVE_OFFER', action.streamId, action.offerId);

    case 'BRING_BACK_OFFER':
      return startMutation(state, 'BRING_BACK_OFFER', action.streamId, action.offerId);

    case 'TOGGLE_PIN':
      return startMutation(state, 'TOGGLE_PIN', action.streamId, action.offerId);

    case 'REBALANCE_STREAM':
      return startMutation(state, 'REBALANCE_STREAM', action.streamId);

    case 'CANCEL_CHANGES':
      return startMutation(state, 'CANCEL_CHANGES', action.streamId);

    case 'PUSH_TO_KT': {
      if (isEditorBusy(state.status) || state.campaign === null) {
        return state;
      }
      const targetStream = state.campaign.streams.find((stream) => stream.id === action.streamId);
      if (
        !targetStream ||
        !targetStream.has_offers ||
        !targetStream.is_dirty ||
        !targetStream.can_push
      ) {
        return state;
      }
      return startMutation(state, 'PUSH_TO_KT', action.streamId);
    }

    case 'FETCH_STREAMS_SUCCESS':
      if (state.selectedCampaignId !== action.campaignId) {
        return state;
      }
      return {
        ...state,
        status: deriveEditorStatus(action.campaign),
        campaign: action.campaign,
        pendingAction: null,
        actionError: null,
      };

    case 'STREAM_MUTATION_SUCCESS': {
      if (state.selectedCampaignId !== action.campaignId || state.campaign === null) {
        return state;
      }
      const updatedCampaign = replaceStreamInCampaign(state.campaign, action.stream);
      return {
        ...state,
        status: deriveEditorStatus(updatedCampaign),
        campaign: updatedCampaign,
        pendingAction: null,
        actionError: null,
      };
    }

    case 'MUTATION_FAILURE': {
      if (state.selectedCampaignId !== action.campaignId) {
        return state;
      }
      const recoveredStatus =
        state.campaign !== null ? deriveEditorStatus(state.campaign) : 'error';
      return {
        ...state,
        status: recoveredStatus,
        pendingAction: null,
        actionError: action.error,
      };
    }

    case 'DISMISS_ACTION_ERROR':
      return {
        ...state,
        actionError: null,
      };

    default:
      return state;
  }
}
