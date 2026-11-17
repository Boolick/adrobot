import { useMemo, useState } from 'react';
import { OfferRow, PinIcon, type StreamOfferDto } from '@/entities/offer';
import { StreamHeader, type StreamDto } from '@/entities/stream';
import { AlertBanner, Button } from '@/shared/ui';
import type { PendingEditorAction } from '../model/types';
import { AddOfferPanel } from './AddOfferPanel';

export interface StreamCardProps {
  stream: StreamDto;
  isBusy: boolean;
  pendingAction: PendingEditorAction | null;
  onAddOffer: (streamId: number, offerId: number, offerName: string) => Promise<boolean>;
  onRemoveOffer: (streamId: number, offerId: number) => Promise<boolean>;
  onBringBackOffer: (streamId: number, offerId: number) => Promise<boolean>;
  onTogglePin: (streamId: number, offerId: number, share?: number) => Promise<boolean>;
  onCancelChanges: (streamId: number) => Promise<boolean>;
  onPushToKt: (streamId: number) => Promise<boolean>;
}

interface ShareEditorControlProps {
  offer: StreamOfferDto;
  isBusy: boolean;
  onSaveShare: (share: number) => Promise<boolean>;
}

function ShareEditorControl({ offer, isBusy, onSaveShare }: ShareEditorControlProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(offer.share));
  const [inputError, setInputError] = useState<string | null>(null);

  if (!editing) {
    return (
      <button
        type="button"
        className="share-pill-btn"
        disabled={isBusy}
        title="Click to pin an explicit share percentage (1-100)"
        onClick={() => {
          setDraft(String(offer.share));
          setInputError(null);
          setEditing(true);
        }}
      >
        {offer.share}%
      </button>
    );
  }

  const handleApply = async () => {
    const parsed = Number(draft.trim());
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 100) {
      setInputError('1-100');
      return;
    }
    const ok = await onSaveShare(parsed);
    if (ok) {
      setEditing(false);
    }
  };

  return (
    <div className="share-inline-edit">
      <input
        type="number"
        min={1}
        max={100}
        step={1}
        className={`share-inline-edit__input ${inputError ? 'input--error' : ''}`.trim()}
        value={draft}
        disabled={isBusy}
        aria-label={`Pinned share for ${offer.offer_name}`}
        onChange={(e) => {
          setDraft(e.target.value);
          setInputError(null);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void handleApply();
          } else if (e.key === 'Escape') {
            setEditing(false);
          }
        }}
      />
      <span className="share-inline-edit__pct">%</span>
      <Button size="sm" variant="primary" disabled={isBusy} onClick={() => void handleApply()}>
        Pin
      </Button>
      <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => setEditing(false)}>
        ✕
      </Button>
    </div>
  );
}

export function StreamCard({
  stream,
  isBusy,
  pendingAction,
  onAddOffer,
  onRemoveOffer,
  onBringBackOffer,
  onTogglePin,
  onCancelChanges,
  onPushToKt,
}: StreamCardProps) {
  const activeOfferIds = useMemo(() => {
    const ids = new Set<number>();
    for (const offer of stream.offers) {
      if (offer.status === 'active') {
        ids.add(offer.keitaro_offer_id);
      }
    }
    return ids;
  }, [stream.offers]);

  if (!stream.has_offers) {
    return (
      <section className="stream-card stream-card--readonly" aria-label={`Stream ${stream.name}`}>
        <StreamHeader stream={stream} />
      </section>
    );
  }

  const isStreamPending = pendingAction?.streamId === stream.id;
  const isPushing = isStreamPending && pendingAction?.kind === 'PUSH_TO_KT';
  const isCanceling = isStreamPending && pendingAction?.kind === 'CANCEL_CHANGES';
  const isAdding = isStreamPending && pendingAction?.kind === 'ADD_OFFER';

  return (
    <section
      className={`stream-card ${stream.is_dirty ? 'stream-card--dirty' : ''}`.trim()}
      aria-label={`Editable stream ${stream.name}`}
    >
      <StreamHeader
        stream={stream}
        actions={
          stream.is_dirty ? (
            <div className="stream-card__header-actions">
              <Button
                variant="secondary"
                size="sm"
                disabled={isBusy}
                isLoading={isCanceling}
                onClick={() => void onCancelChanges(stream.id)}
              >
                CANCEL
              </Button>
              <Button
                variant="primary"
                size="sm"
                disabled={!stream.can_push || isBusy}
                isLoading={isPushing}
                onClick={() => void onPushToKt(stream.id)}
              >
                PUSH TO KT
              </Button>
            </div>
          ) : undefined
        }
      />

      {!stream.can_push && stream.validation_error && (
        <div className="stream-card__validation">
          <AlertBanner
            variant="warning"
            title="Cannot push stream to Keitaro"
            message={stream.validation_error}
          />
        </div>
      )}

      <div className="stream-card__offers">
        {stream.offers.length === 0 ? (
          <p className="stream-card__empty">No offers staged in this stream yet.</p>
        ) : (
          stream.offers.map((offer) => {
            const isOfferPending =
              isStreamPending && pendingAction?.offerId === offer.keitaro_offer_id;
            const isRemoving = isOfferPending && pendingAction?.kind === 'REMOVE_OFFER';
            const isBringingBack = isOfferPending && pendingAction?.kind === 'BRING_BACK_OFFER';

            if (offer.status === 'removed') {
              return (
                <OfferRow
                  key={offer.id}
                  offer={offer}
                  actions={
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={isBusy}
                      isLoading={isBringingBack}
                      onClick={() => void onBringBackOffer(stream.id, offer.keitaro_offer_id)}
                    >
                      BRING BACK
                    </Button>
                  }
                />
              );
            }

            return (
              <OfferRow
                key={offer.id}
                offer={offer}
                shareControl={
                  <ShareEditorControl
                    offer={offer}
                    isBusy={isBusy}
                    onSaveShare={(share) => onTogglePin(stream.id, offer.keitaro_offer_id, share)}
                  />
                }
                pinControl={
                  <button
                    type="button"
                    className={`pin-btn ${offer.is_pinned ? 'pin-btn--pinned' : ''}`.trim()}
                    disabled={isBusy}
                    aria-pressed={offer.is_pinned}
                    aria-label={
                      offer.is_pinned
                        ? `Unpin offer ${offer.offer_name}`
                        : `Pin offer ${offer.offer_name} at ${offer.share}%`
                    }
                    title={offer.is_pinned ? 'Pinned (click to unpin)' : 'Pin current share'}
                    onClick={() => void onTogglePin(stream.id, offer.keitaro_offer_id)}
                  >
                    <PinIcon filled={offer.is_pinned} />
                  </button>
                }
                actions={
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={isBusy}
                    isLoading={isRemoving}
                    onClick={() => void onRemoveOffer(stream.id, offer.keitaro_offer_id)}
                  >
                    REMOVE
                  </Button>
                }
              />
            );
          })
        )}
      </div>

      <AddOfferPanel
        activeOfferIds={activeOfferIds}
        disabled={isBusy}
        isAdding={isAdding}
        onAdd={(offerId, offerName) => onAddOffer(stream.id, offerId, offerName)}
      />
    </section>
  );
}
