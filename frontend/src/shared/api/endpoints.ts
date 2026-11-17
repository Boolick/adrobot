import { apiRequest, type ApiPaths, type ApiSchemas } from './client';

export type HealthResponse =
  ApiPaths['/health']['get']['responses']['200']['content']['application/json'];
export type DictionariesResponse =
  ApiPaths['/api/v1/dictionaries']['get']['responses']['200']['content']['application/json'];
export type OfferListResponse =
  ApiPaths['/api/v1/offers']['get']['responses']['200']['content']['application/json'];
export type CampaignListResponse =
  ApiPaths['/api/v1/campaigns']['get']['responses']['200']['content']['application/json'];
export type CreateCampaignPayload =
  ApiPaths['/api/v1/campaigns']['post']['requestBody']['content']['application/json'];
export type CampaignDetailResponse =
  ApiPaths['/api/v1/campaigns']['post']['responses']['201']['content']['application/json'];
export type StreamResponse =
  ApiPaths['/api/v1/streams/{stream_id}/cancel']['post']['responses']['200']['content']['application/json'];
export type AddStreamOfferPayload =
  ApiPaths['/api/v1/streams/{stream_id}/offers']['post']['requestBody']['content']['application/json'];
export type PinOfferPayload = ApiSchemas['PinOfferRequest'];

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/health', { signal });
}

export function getDictionaries(signal?: AbortSignal): Promise<DictionariesResponse> {
  return apiRequest<DictionariesResponse>('/api/v1/dictionaries', { signal });
}

export function searchOffers(q?: string, signal?: AbortSignal): Promise<OfferListResponse> {
  const trimmed = q?.trim() ?? '';
  const query = trimmed ? `?${new URLSearchParams({ q: trimmed }).toString()}` : '';
  return apiRequest<OfferListResponse>(`/api/v1/offers${query}`, { signal });
}

export function listCampaigns(signal?: AbortSignal): Promise<CampaignListResponse> {
  return apiRequest<CampaignListResponse>('/api/v1/campaigns', { signal });
}

export function createCampaign(payload: CreateCampaignPayload): Promise<CampaignDetailResponse> {
  return apiRequest<CampaignDetailResponse>('/api/v1/campaigns', {
    method: 'POST',
    body: payload,
  });
}

export function getCampaignDetail(
  campaignId: number,
  signal?: AbortSignal,
): Promise<CampaignDetailResponse> {
  return apiRequest<CampaignDetailResponse>(`/api/v1/campaigns/${campaignId}`, { signal });
}

export function fetchCampaignStreams(campaignId: number): Promise<CampaignDetailResponse> {
  return apiRequest<CampaignDetailResponse>(`/api/v1/campaigns/${campaignId}/streams/fetch`, {
    method: 'POST',
  });
}

export function addStreamOffer(
  streamId: number,
  payload: AddStreamOfferPayload,
): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/offers`, {
    method: 'POST',
    body: payload,
  });
}

export function removeStreamOffer(streamId: number, offerId: number): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/offers/${offerId}/remove`, {
    method: 'POST',
  });
}

export function bringBackStreamOffer(streamId: number, offerId: number): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/offers/${offerId}/bring-back`, {
    method: 'POST',
  });
}

export function pinStreamOffer(
  streamId: number,
  offerId: number,
  payload?: PinOfferPayload,
): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/offers/${offerId}/pin`, {
    method: 'POST',
    body: payload,
  });
}

export function cancelStreamChanges(streamId: number): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/cancel`, {
    method: 'POST',
  });
}

export function pushStreamToKt(streamId: number): Promise<StreamResponse> {
  return apiRequest<StreamResponse>(`/api/v1/streams/${streamId}/push`, {
    method: 'POST',
  });
}
