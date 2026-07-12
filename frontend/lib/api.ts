import type { components } from "@/lib/generated/api-types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Schema<TName extends keyof components["schemas"]> = components["schemas"][TName];

export type ProviderStatus = Schema<"ProviderStatusResponse">;
export type ProviderBilling = Schema<"ProviderBillingResponse">;
export type ProviderBillingItem = Schema<"ProviderBillingItem">;
export type AnalysisSummary = Schema<"AnalysisRequestSummary">;
export type AnalysisRun = Schema<"AnalysisRunResponse">;
export type RuleParse = Schema<"RuleParseResponse">;
export type Recommendation = Schema<"RecommendationResponse">;
export type SocialIntelSummary = Schema<"SocialIntelSummaryResponse">;
export type Source = Schema<"SourceResponse">;
export type Document = Schema<"DocumentResponse">;
export type Passage = Schema<"PassageResponse">;
export type FactClaim = Schema<"FactClaimResponse">;
export type Factor = Schema<"FactorResponse">;
export type Review = Schema<"ReviewResponse">;
export type AnalysisStage = Schema<"AnalysisStageResponse">;
export type AnalysisProgress = Schema<"AnalysisProgressResponse">;
export type FactorContribution = Schema<"FactorContributionResponse">;
export type UncertaintyAdjustment = Schema<"UncertaintyAdjustmentResponse">;
export type AnalysisAudit = Schema<"AnalysisAuditResponse">;
export type PresentationEvidenceItem = Schema<"PresentationEvidenceItemResponse">;
export type PresentationArtifactStatus = Schema<"PresentationArtifactStatusResponse">;
export type AnalysisPresentation = Schema<"AnalysisPresentationResponse">;
export type AnalysisProgressPresentation = Schema<"AnalysisProgressPresentationResponse">;
export type AnalysisDetail = Schema<"AnalysisDetailResponse">;
export type AnalysisProgressPayload = Schema<"AnalysisProgressPollResponse">;
export type ManualAnalysisPayload = Schema<"ManualAnalysisCreateRequest">;
export type QueuedAnalysisResponse = Schema<"AnalysisQueuedResponse">;
export type PublicMarket = Schema<"PublicMarketResponse">;
export type PublicMarketList = Schema<"PublicMarketListResponse">;
export type ResearchEdgeSignal = Schema<"ResearchEdgeSignalResponse">;

function extractValidationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) {
    return null;
  }

  const first = detail[0];
  if (!first || typeof first !== "object") {
    return null;
  }

  const payload = first as { loc?: unknown; msg?: unknown };
  const location = Array.isArray(payload.loc) ? payload.loc.join(".") : null;
  const message = typeof payload.msg === "string" ? payload.msg : null;
  if (!location && !message) {
    return null;
  }
  return [location, message].filter(Boolean).join(": ");
}

function extractErrorMessage(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  return extractValidationMessage(detail);
}

async function parseError(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const payload = (await response.json()) as unknown;
      return extractErrorMessage(payload) ?? `Request failed with ${response.status}`;
    } catch {
      return `Request failed with ${response.status}`;
    }
  }

  const payload = await response.text();
  return payload.trim() || `Request failed with ${response.status}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as T;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
  });
  return parseResponse<T>(response);
}

export async function fetchProviderStatus(): Promise<ProviderStatus> {
  return fetchJson<ProviderStatus>("/api/providers/status");
}

export async function fetchProviderBilling(refresh = false): Promise<ProviderBilling> {
  return fetchJson<ProviderBilling>(`/api/providers/billing${refresh ? "?refresh=true" : ""}`);
}

export async function fetchAnalyses(): Promise<Schema<"AnalysisListResponse">> {
  return fetchJson<Schema<"AnalysisListResponse">>("/api/analyses");
}

export async function fetchAnalysis(id: string | number): Promise<AnalysisDetail> {
  return fetchJson<AnalysisDetail>(`/api/analyses/${id}`);
}

export async function fetchAnalysisProgress(
  id: string | number,
): Promise<AnalysisProgressPayload> {
  return fetchJson<AnalysisProgressPayload>(`/api/analyses/${id}/progress`);
}

export async function createManualAnalysis(
  payload: ManualAnalysisPayload,
): Promise<QueuedAnalysisResponse> {
  return fetchJson<QueuedAnalysisResponse>("/api/analyses/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function rerunAnalysis(
  id: string | number,
): Promise<QueuedAnalysisResponse> {
  return fetchJson<QueuedAnalysisResponse>(`/api/analyses/${id}/rerun`, {
    method: "POST",
  });
}

export async function fetchPublicMarkets(params?: {
  q?: string;
  view?: string;
  limit?: number;
  offset?: number;
}): Promise<PublicMarketList> {
  const searchParams = new URLSearchParams();
  if (params?.q) {
    searchParams.set("q", params.q);
  }
  if (params?.view) {
    searchParams.set("view", params.view);
  }
  if (params?.limit) {
    searchParams.set("limit", String(params.limit));
  }
  if (params?.offset) {
    searchParams.set("offset", String(params.offset));
  }
  const suffix = searchParams.toString() ? `?${searchParams.toString()}` : "";
  return fetchJson<PublicMarketList>(`/api/markets/discover${suffix}`);
}

export async function fetchPublicMarket(polymarketId: string): Promise<PublicMarket> {
  return fetchJson<PublicMarket>(`/api/markets/remote/${encodeURIComponent(polymarketId)}`);
}
