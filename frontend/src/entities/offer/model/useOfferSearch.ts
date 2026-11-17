import { useEffect, useMemo, useState } from 'react';
import { extractErrorInfo, isAbortError, searchOffers } from '@/shared/api';
import { useDebouncedValue } from '@/shared/lib';
import type { OfferDto } from './types';

export interface UseOfferSearchOptions {
  query: string;
  enabled: boolean;
  excludeOfferIds?: ReadonlySet<number>;
  debounceMs?: number;
}

export interface UseOfferSearchResult {
  offers: OfferDto[];
  isLoading: boolean;
  error: string | null;
}

export function useOfferSearch({
  query,
  enabled,
  excludeOfferIds,
  debounceMs = 280,
}: UseOfferSearchOptions): UseOfferSearchResult {
  const debouncedQuery = useDebouncedValue(query, debounceMs);
  const [rawOffers, setRawOffers] = useState<OfferDto[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    void searchOffers(debouncedQuery, controller.signal)
      .then((results) => {
        setRawOffers(results);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (isAbortError(err)) {
          return;
        }
        setError(extractErrorInfo(err, 'Failed to search offers.').message);
        setIsLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [debouncedQuery, enabled]);

  const offers = useMemo(() => {
    if (!excludeOfferIds || excludeOfferIds.size === 0) {
      return rawOffers;
    }
    return rawOffers.filter((offer) => !excludeOfferIds.has(offer.id));
  }, [rawOffers, excludeOfferIds]);

  return { offers, isLoading, error };
}
