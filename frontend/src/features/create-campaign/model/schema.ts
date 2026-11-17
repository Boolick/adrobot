import { z } from 'zod';
import type { CreateCampaignPayload } from '@/shared/api';

export const CAMPAIGN_NAME_REGEX = /^test_[a-zA-Z0-9_-]+$/;
export const ISO2_GEO_REGEX = /^[A-Z]{2}$/;
export const DEFAULT_GEO_CODES = ['AU', 'MX'] as const;

export interface ParsedGeoResult {
  codes: string[];
  invalidTokens: string[];
}

export function parseGeoInput(raw: string): ParsedGeoResult {
  const tokens = raw
    .split(/[\s,;]+/)
    .map((part) => part.trim().toUpperCase())
    .filter(Boolean);

  const codes: string[] = [];
  const invalidTokens: string[] = [];
  const seen = new Set<string>();

  for (const token of tokens) {
    if (!ISO2_GEO_REGEX.test(token)) {
      invalidTokens.push(token);
      continue;
    }
    if (!seen.has(token)) {
      seen.add(token);
      codes.push(token);
    }
  }

  return { codes, invalidTokens };
}

export const createCampaignSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Campaign name is required.')
    .max(255, 'Campaign name must be 255 characters or fewer.')
    .regex(
      CAMPAIGN_NAME_REGEX,
      'Name must match ^test_[a-zA-Z0-9_-]+$ (e.g., test_bullo_campaign1).',
    ),
  alias: z
    .string()
    .trim()
    .max(100, 'Alias must be 100 characters or fewer.')
    .transform((val) => (val.length > 0 ? val : null)),
  geo: z
    .array(z.string().regex(ISO2_GEO_REGEX, 'Each GEO must be a 2-letter uppercase ISO code.'))
    .min(1, 'At least one valid 2-letter ISO country code is required (e.g., AU, MX).'),
  domain_id: z.number().int().positive('Please select a valid domain.'),
  group_id: z.number().int().positive('Please select a valid campaign group.'),
  traffic_source_id: z.number().int().positive('Please select a valid traffic source.'),
  initial_offer_id: z
    .number({
      required_error: 'Please search and select an initial offer.',
      invalid_type_error: 'Please search and select an initial offer.',
    })
    .int()
    .positive('Please select a valid initial offer.'),
});

export type CreateCampaignFormValues = z.infer<typeof createCampaignSchema>;

export interface CreateCampaignFieldErrors {
  name?: string;
  alias?: string;
  geo?: string;
  domain_id?: string;
  group_id?: string;
  traffic_source_id?: string;
  initial_offer_id?: string;
}

export function validateCreateCampaignForm(input: {
  name: string;
  alias: string;
  geoInput: string;
  domainId: number;
  groupId: number;
  trafficSourceId: number;
  initialOfferId: number | null;
}):
  | { success: true; payload: CreateCampaignPayload }
  | { success: false; fieldErrors: CreateCampaignFieldErrors } {
  const parsedGeo = parseGeoInput(input.geoInput);
  if (parsedGeo.invalidTokens.length > 0) {
    return {
      success: false,
      fieldErrors: {
        geo: `Invalid GEO code(s): ${parsedGeo.invalidTokens.join(', ')}. Use 2-letter ISO codes like AU, MX.`,
      },
    };
  }

  const result = createCampaignSchema.safeParse({
    name: input.name,
    alias: input.alias,
    geo: parsedGeo.codes,
    domain_id: input.domainId,
    group_id: input.groupId,
    traffic_source_id: input.trafficSourceId,
    initial_offer_id: input.initialOfferId,
  });

  if (!result.success) {
    const fieldErrors: CreateCampaignFieldErrors = {};
    for (const issue of result.error.issues) {
      const key = issue.path[0];
      if (typeof key === 'string' && !(key in fieldErrors)) {
        fieldErrors[key as keyof CreateCampaignFieldErrors] = issue.message;
      }
    }
    return { success: false, fieldErrors };
  }

  return {
    success: true,
    payload: {
      name: result.data.name,
      alias: result.data.alias,
      geo: result.data.geo,
      domain_id: result.data.domain_id,
      group_id: result.data.group_id,
      traffic_source_id: result.data.traffic_source_id,
      initial_offer_id: result.data.initial_offer_id,
    },
  };
}
