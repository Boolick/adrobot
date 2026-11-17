import { useState } from 'react';
import { OfferSearchInput, type OfferDto } from '@/entities/offer';
import { Button } from '@/shared/ui';

export interface AddOfferPanelProps {
  activeOfferIds: ReadonlySet<number>;
  disabled: boolean;
  isAdding: boolean;
  onAdd: (offerId: number, offerName: string) => Promise<boolean>;
}

export function AddOfferPanel({ activeOfferIds, disabled, isAdding, onAdd }: AddOfferPanelProps) {
  const [selectedOffer, setSelectedOffer] = useState<OfferDto | null>(null);

  const handleAdd = async () => {
    if (!selectedOffer || disabled) {
      return;
    }
    const ok = await onAdd(selectedOffer.id, selectedOffer.name);
    if (ok) {
      setSelectedOffer(null);
    }
  };

  return (
    <div className="add-offer-panel">
      <div className="add-offer-panel__search">
        <OfferSearchInput
          placeholder="Search offers to add (by ID or name)..."
          selectedOffer={selectedOffer}
          onSelect={setSelectedOffer}
          excludeOfferIds={activeOfferIds}
          disabled={disabled}
        />
      </div>
      <div className="add-offer-panel__action">
        <Button
          variant="secondary"
          size="md"
          disabled={disabled || !selectedOffer}
          isLoading={isAdding}
          onClick={() => void handleAdd()}
        >
          ADD
        </Button>
      </div>
    </div>
  );
}
