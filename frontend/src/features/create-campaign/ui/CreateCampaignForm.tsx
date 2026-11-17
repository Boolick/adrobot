import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import type { CampaignDetailDto, DictionariesResponse } from '@/entities/campaign';
import { OfferSearchInput, type OfferDto } from '@/entities/offer';
import { createCampaign, extractErrorInfo, getDictionaries, isAbortError } from '@/shared/api';
import { AlertBanner, Badge, Button, Input, Select, Spinner } from '@/shared/ui';
import {
  DEFAULT_GEO_CODES,
  parseGeoInput,
  validateCreateCampaignForm,
  type CreateCampaignFieldErrors,
} from '../model/schema';

export interface CreateCampaignFormProps {
  onCreated: (campaign: CampaignDetailDto) => void;
  onCancel?: () => void;
}

function buildOptionsWithFallback(
  items: Array<{ id: number; name: string }>,
  selectedId: number,
  fallbackLabel: string,
) {
  const options = items.map((item) => ({
    value: item.id,
    label: `${item.name} (#${item.id})`,
  }));
  if (selectedId > 0 && !items.some((item) => item.id === selectedId)) {
    options.unshift({ value: selectedId, label: `${fallbackLabel} (#${selectedId})` });
  }
  return options;
}

export function CreateCampaignForm({ onCreated, onCancel }: CreateCampaignFormProps) {
  const [dictionaries, setDictionaries] = useState<DictionariesResponse | null>(null);
  const [dictLoading, setDictLoading] = useState(true);
  const [dictError, setDictError] = useState<{
    message: string;
    code?: string;
    details?: Record<string, string> | null;
  } | null>(null);

  const [name, setName] = useState('test_bullo_');
  const [alias, setAlias] = useState('');
  const [geoInput, setGeoInput] = useState(DEFAULT_GEO_CODES.join(', '));
  const [domainId, setDomainId] = useState<number>(0);
  const [groupId, setGroupId] = useState<number>(0);
  const [trafficSourceId, setTrafficSourceId] = useState<number>(0);
  const [selectedOffer, setSelectedOffer] = useState<OfferDto | null>(null);

  const [fieldErrors, setFieldErrors] = useState<CreateCampaignFieldErrors>({});
  const [submitError, setSubmitError] = useState<{
    message: string;
    code?: string;
    details?: Record<string, string> | null;
  } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const loadDictionaries = useCallback((signal?: AbortSignal) => {
    setDictLoading(true);
    setDictError(null);

    void getDictionaries(signal)
      .then((data) => {
        setDictionaries(data);
        setName((prev) =>
          prev === 'test_bullo_' || prev.trim() === '' ? data.defaults.campaign_prefix : prev,
        );
        setDomainId(data.defaults.domain_id);
        setGroupId(data.defaults.group_id);
        setTrafficSourceId(data.defaults.traffic_source_id);
        setDictLoading(false);
      })
      .catch((err: unknown) => {
        if (isAbortError(err)) {
          return;
        }
        setDictError(extractErrorInfo(err, 'Failed to load Keitaro dictionaries.'));
        setDictLoading(false);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadDictionaries(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadDictionaries]);

  const parsedGeo = useMemo(() => parseGeoInput(geoInput), [geoInput]);

  const domainOptions = useMemo(
    () => buildOptionsWithFallback(dictionaries?.domains ?? [], domainId, 'Default Domain'),
    [dictionaries, domainId],
  );
  const groupOptions = useMemo(
    () => buildOptionsWithFallback(dictionaries?.groups ?? [], groupId, 'Default Group'),
    [dictionaries, groupId],
  );
  const sourceOptions = useMemo(
    () =>
      buildOptionsWithFallback(
        dictionaries?.traffic_sources ?? [],
        trafficSourceId,
        'Default Source',
      ),
    [dictionaries, trafficSourceId],
  );

  const handleRemoveGeoTag = (codeToRemove: string) => {
    const remaining = parsedGeo.codes.filter((code) => code !== codeToRemove);
    setGeoInput(remaining.join(', '));
    setFieldErrors((prev) => ({ ...prev, geo: undefined }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submittingRef.current || isSubmitting || dictLoading) {
      return;
    }

    setSubmitError(null);
    const validation = validateCreateCampaignForm({
      name,
      alias,
      geoInput,
      domainId,
      groupId,
      trafficSourceId,
      initialOfferId: selectedOffer?.id ?? null,
    });

    if (!validation.success) {
      setFieldErrors(validation.fieldErrors);
      return;
    }

    setFieldErrors({});
    submittingRef.current = true;
    setIsSubmitting(true);

    try {
      const created = await createCampaign(validation.payload);
      onCreated(created);
    } catch (err) {
      setSubmitError(extractErrorInfo(err, 'Failed to create campaign.'));
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  if (dictLoading) {
    return (
      <div className="panel-loading">
        <Spinner size="md" label="Loading Keitaro dictionaries" />
        <span>Loading Keitaro domains, groups, and traffic sources...</span>
      </div>
    );
  }

  if (dictError && !dictionaries) {
    return (
      <div className="stack-md">
        <AlertBanner
          variant="error"
          title="Could not load Keitaro dictionaries"
          code={dictError.code}
          message={dictError.message}
          details={dictError.details}
        />
        <div>
          <Button variant="secondary" onClick={() => loadDictionaries()}>
            Retry loading dictionaries
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form className="form-grid" onSubmit={(e) => void handleSubmit(e)} noValidate>
      {submitError && (
        <AlertBanner
          variant="error"
          title="Campaign creation failed"
          code={submitError.code}
          message={submitError.message}
          details={submitError.details}
          onDismiss={() => setSubmitError(null)}
        />
      )}

      <div className="form-row-2">
        <Input
          label="Campaign Name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setFieldErrors((prev) => ({ ...prev, name: undefined }));
          }}
          placeholder="test_bullo_campaign1"
          hint="Must start with test_ and use letters, digits, underscores, or hyphens."
          error={fieldErrors.name}
          disabled={isSubmitting}
          required
        />

        <Input
          label="URL Alias (optional)"
          value={alias}
          onChange={(e) => {
            setAlias(e.target.value);
            setFieldErrors((prev) => ({ ...prev, alias: undefined }));
          }}
          placeholder="test-bullo-campaign1"
          hint="Optional — auto-generated if left blank."
          error={fieldErrors.alias}
          disabled={isSubmitting}
        />
      </div>

      <div className="stack-xs">
        <Input
          label="Target GEO Codes (ISO-2)"
          value={geoInput}
          onChange={(e) => {
            setGeoInput(e.target.value);
            setFieldErrors((prev) => ({ ...prev, geo: undefined }));
          }}
          placeholder="AU, MX"
          hint="Comma- or space-separated 2-letter ISO country codes for Flow 1 (Geo -> Google)."
          error={fieldErrors.geo}
          disabled={isSubmitting}
          required
        />
        {parsedGeo.codes.length > 0 && (
          <div className="geo-pills" aria-label="Selected GEO codes">
            {parsedGeo.codes.map((code) => (
              <Badge key={code} variant="accent" className="geo-pill">
                <span>{code}</span>
                <button
                  type="button"
                  className="geo-pill__remove"
                  onClick={() => handleRemoveGeoTag(code)}
                  disabled={isSubmitting}
                  aria-label={`Remove ${code}`}
                >
                  ×
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      <OfferSearchInput
        label="Initial Offer (Flow 2 — 100% share)"
        placeholder="Search Keitaro offers by ID or name..."
        selectedOffer={selectedOffer}
        onSelect={(offer) => {
          setSelectedOffer(offer);
          setFieldErrors((prev) => ({ ...prev, initial_offer_id: undefined }));
        }}
        disabled={isSubmitting}
        error={fieldErrors.initial_offer_id}
      />

      <div className="form-row-3">
        <Select
          label="Domain"
          value={domainId}
          options={domainOptions}
          onChange={(e) => {
            setDomainId(Number(e.target.value));
            setFieldErrors((prev) => ({ ...prev, domain_id: undefined }));
          }}
          error={fieldErrors.domain_id}
          disabled={isSubmitting}
        />

        <Select
          label="Campaign Group"
          value={groupId}
          options={groupOptions}
          onChange={(e) => {
            setGroupId(Number(e.target.value));
            setFieldErrors((prev) => ({ ...prev, group_id: undefined }));
          }}
          error={fieldErrors.group_id}
          disabled={isSubmitting}
        />

        <Select
          label="Traffic Source"
          value={trafficSourceId}
          options={sourceOptions}
          onChange={(e) => {
            setTrafficSourceId(Number(e.target.value));
            setFieldErrors((prev) => ({ ...prev, traffic_source_id: undefined }));
          }}
          error={fieldErrors.traffic_source_id}
          disabled={isSubmitting}
        />
      </div>

      <div className="form-actions">
        {onCancel && (
          <Button variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}
        <Button type="submit" variant="primary" isLoading={isSubmitting}>
          Create 2-Stream Campaign
        </Button>
      </div>
    </form>
  );
}
