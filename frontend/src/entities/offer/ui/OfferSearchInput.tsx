import { useEffect, useId, useRef, useState } from 'react';
import { Spinner } from '@/shared/ui';
import type { OfferDto } from '../model/types';
import { useOfferSearch } from '../model/useOfferSearch';

export interface OfferSearchInputProps {
  label?: string;
  placeholder?: string;
  selectedOffer: OfferDto | null;
  onSelect: (offer: OfferDto | null) => void;
  excludeOfferIds?: ReadonlySet<number>;
  disabled?: boolean;
  error?: string | null;
}

export function OfferSearchInput({
  label,
  placeholder = 'Search offers by ID or name...',
  selectedOffer,
  onSelect,
  excludeOfferIds,
  disabled = false,
  error,
}: OfferSearchInputProps) {
  const inputId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  const {
    offers,
    isLoading,
    error: searchError,
  } = useOfferSearch({
    query,
    enabled: isOpen && !disabled,
    excludeOfferIds,
  });

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
    };
  }, []);

  const handleChoose = (offer: OfferDto) => {
    onSelect(offer);
    setQuery('');
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="field offer-search">
      {label && (
        <label htmlFor={inputId} className="field__label">
          {label}
        </label>
      )}

      <div className="offer-search__control">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          className={`input ${error ? 'input--error' : ''}`.trim()}
          value={query}
          placeholder={placeholder}
          disabled={disabled}
          onFocus={() => setIsOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setIsOpen(false);
            }
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!isOpen) {
              setIsOpen(true);
            }
          }}
        />
        {isLoading && isOpen && (
          <span className="offer-search__spinner">
            <Spinner size="sm" label="Searching offers" />
          </span>
        )}
      </div>

      {selectedOffer && (
        <div className="offer-search__selected">
          <span>
            Selected: <strong>#{selectedOffer.id}</strong> — {selectedOffer.name}
          </span>
          <button
            type="button"
            className="offer-search__clear"
            onClick={() => onSelect(null)}
            disabled={disabled}
            aria-label="Clear selected offer"
          >
            Clear
          </button>
        </div>
      )}

      {isOpen && !disabled && (
        <div className="offer-search__dropdown" role="listbox">
          {searchError && (
            <div className="offer-search__status offer-search__status--error">{searchError}</div>
          )}
          {!searchError && !isLoading && offers.length === 0 && (
            <div className="offer-search__status">No matching offers found.</div>
          )}
          {offers.slice(0, 50).map((offer) => {
            const isSelected = selectedOffer?.id === offer.id;
            const payout =
              offer.payout_value != null
                ? `${offer.payout_value}${offer.payout_currency ? ` ${offer.payout_currency}` : ''}`
                : null;

            return (
              <button
                key={offer.id}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`offer-search__option ${isSelected ? 'offer-search__option--selected' : ''}`.trim()}
                onClick={() => handleChoose(offer)}
              >
                <span className="offer-search__option-id">#{offer.id}</span>
                <span className="offer-search__option-name">{offer.name}</span>
                {payout && <span className="offer-search__option-meta">{payout}</span>}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
