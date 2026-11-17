import { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  addStreamOffer,
  bringBackStreamOffer,
  cancelStreamChanges,
  extractErrorInfo,
  fetchCampaignStreams,
  getCampaignDetail,
  isAbortError,
  pinStreamOffer,
  pushStreamToKt,
  removeStreamOffer,
} from '@/shared/api';
import type { StreamDto } from '@/entities/stream';
import { INITIAL_STREAM_EDITOR_STATE, isEditorBusy, streamEditorReducer } from './fsm';
import type { StreamEditorAction, StreamEditorState } from './types';

export interface StreamEditorCommands {
  reloadCampaign: () => void;
  fetchStreamsFromKt: () => Promise<boolean>;
  addOffer: (streamId: number, offerId: number, offerName: string) => Promise<boolean>;
  removeOffer: (streamId: number, offerId: number) => Promise<boolean>;
  bringBackOffer: (streamId: number, offerId: number) => Promise<boolean>;
  togglePin: (streamId: number, offerId: number, share?: number) => Promise<boolean>;
  cancelChanges: (streamId: number) => Promise<boolean>;
  pushToKt: (streamId: number) => Promise<boolean>;
  dismissActionError: () => void;
}

export interface UseStreamEditorResult {
  state: StreamEditorState;
  commands: StreamEditorCommands;
}

export function useStreamEditor(campaignId: number | null): UseStreamEditorResult {
  const [state, dispatch] = useReducer(streamEditorReducer, INITIAL_STREAM_EDITOR_STATE);

  const statusRef = useRef(state.status);
  statusRef.current = state.status;

  const campaignRef = useRef(state.campaign);
  campaignRef.current = state.campaign;

  const inFlightMutationRef = useRef(false);
  const campaignEpochRef = useRef(0);
  const loadSeqRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);

  const loadCampaign = useCallback((targetId: number) => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    const seq = ++loadSeqRef.current;

    dispatch({ type: 'LOAD_CAMPAIGN_START', campaignId: targetId });

    void getCampaignDetail(targetId, controller.signal)
      .then((campaign) => {
        if (seq !== loadSeqRef.current) {
          return;
        }
        dispatch({ type: 'LOAD_CAMPAIGN_SUCCESS', campaignId: targetId, campaign });
      })
      .catch((err: unknown) => {
        if (isAbortError(err) || seq !== loadSeqRef.current) {
          return;
        }
        dispatch({
          type: 'LOAD_CAMPAIGN_FAILURE',
          campaignId: targetId,
          error: extractErrorInfo(err, 'Failed to load campaign details.'),
        });
      });
  }, []);

  useEffect(() => {
    campaignEpochRef.current += 1;
    inFlightMutationRef.current = false;

    if (campaignId === null) {
      loadAbortRef.current?.abort();
      loadSeqRef.current += 1;
      dispatch({ type: 'RESET_EDITOR' });
      return;
    }
    loadCampaign(campaignId);

    return () => {
      loadAbortRef.current?.abort();
    };
  }, [campaignId, loadCampaign]);

  const runStreamMutation = useCallback(
    async (
      action: StreamEditorAction,
      requestFn: () => Promise<StreamDto>,
      fallbackMessage: string,
    ): Promise<boolean> => {
      const activeCampaign = campaignRef.current;
      if (inFlightMutationRef.current || isEditorBusy(statusRef.current) || !activeCampaign) {
        return false;
      }

      const epoch = campaignEpochRef.current;
      const targetCampaignId = activeCampaign.id;
      inFlightMutationRef.current = true;
      dispatch(action);

      try {
        const updatedStream = await requestFn();
        if (epoch !== campaignEpochRef.current) {
          return false;
        }
        dispatch({
          type: 'STREAM_MUTATION_SUCCESS',
          campaignId: targetCampaignId,
          stream: updatedStream,
        });
        return true;
      } catch (err) {
        if (epoch !== campaignEpochRef.current) {
          return false;
        }
        dispatch({
          type: 'MUTATION_FAILURE',
          campaignId: targetCampaignId,
          error: extractErrorInfo(err, fallbackMessage),
        });
        return false;
      } finally {
        if (epoch === campaignEpochRef.current) {
          inFlightMutationRef.current = false;
        }
      }
    },
    [],
  );

  const fetchStreamsFromKt = useCallback(async (): Promise<boolean> => {
    const activeCampaign = campaignRef.current;
    if (inFlightMutationRef.current || isEditorBusy(statusRef.current) || !activeCampaign) {
      return false;
    }

    const epoch = campaignEpochRef.current;
    const targetCampaignId = activeCampaign.id;
    inFlightMutationRef.current = true;
    dispatch({ type: 'FETCH_STREAMS' });

    try {
      const updatedCampaign = await fetchCampaignStreams(targetCampaignId);
      if (epoch !== campaignEpochRef.current) {
        return false;
      }
      dispatch({
        type: 'FETCH_STREAMS_SUCCESS',
        campaignId: targetCampaignId,
        campaign: updatedCampaign,
      });
      return true;
    } catch (err) {
      if (epoch !== campaignEpochRef.current) {
        return false;
      }
      dispatch({
        type: 'MUTATION_FAILURE',
        campaignId: targetCampaignId,
        error: extractErrorInfo(err, 'Failed to fetch streams from Keitaro.'),
      });
      return false;
    } finally {
      if (epoch === campaignEpochRef.current) {
        inFlightMutationRef.current = false;
      }
    }
  }, []);

  const addOffer = useCallback(
    (streamId: number, offerId: number, offerName: string) =>
      runStreamMutation(
        { type: 'ADD_OFFER', streamId, offerId },
        () => addStreamOffer(streamId, { offer_id: offerId, offer_name: offerName }),
        'Failed to stage offer onto stream.',
      ),
    [runStreamMutation],
  );

  const removeOffer = useCallback(
    (streamId: number, offerId: number) =>
      runStreamMutation(
        { type: 'REMOVE_OFFER', streamId, offerId },
        () => removeStreamOffer(streamId, offerId),
        'Failed to remove offer from stream.',
      ),
    [runStreamMutation],
  );

  const bringBackOffer = useCallback(
    (streamId: number, offerId: number) =>
      runStreamMutation(
        { type: 'BRING_BACK_OFFER', streamId, offerId },
        () => bringBackStreamOffer(streamId, offerId),
        'Failed to bring back offer.',
      ),
    [runStreamMutation],
  );

  const togglePin = useCallback(
    (streamId: number, offerId: number, share?: number) =>
      runStreamMutation(
        { type: 'TOGGLE_PIN', streamId, offerId },
        () => pinStreamOffer(streamId, offerId, share !== undefined ? { share } : undefined),
        'Failed to update offer pin.',
      ),
    [runStreamMutation],
  );

  const cancelChanges = useCallback(
    (streamId: number) =>
      runStreamMutation(
        { type: 'CANCEL_CHANGES', streamId },
        () => cancelStreamChanges(streamId),
        'Failed to cancel staged changes.',
      ),
    [runStreamMutation],
  );

  const pushToKt = useCallback(
    (streamId: number) => {
      const targetStream = campaignRef.current?.streams.find((stream) => stream.id === streamId);
      if (
        !targetStream ||
        !targetStream.has_offers ||
        !targetStream.is_dirty ||
        !targetStream.can_push
      ) {
        return Promise.resolve(false);
      }
      return runStreamMutation(
        { type: 'PUSH_TO_KT', streamId },
        () => pushStreamToKt(streamId),
        'Failed to push stream changes to Keitaro.',
      );
    },
    [runStreamMutation],
  );

  const reloadCampaign = useCallback(() => {
    if (campaignId !== null) {
      loadCampaign(campaignId);
    }
  }, [campaignId, loadCampaign]);

  const dismissActionError = useCallback(() => {
    dispatch({ type: 'DISMISS_ACTION_ERROR' });
  }, []);

  return {
    state,
    commands: {
      reloadCampaign,
      fetchStreamsFromKt,
      addOffer,
      removeOffer,
      bringBackOffer,
      togglePin,
      cancelChanges,
      pushToKt,
      dismissActionError,
    },
  };
}
