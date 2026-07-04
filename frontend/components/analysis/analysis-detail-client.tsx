"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  SocialIntelSummary,
  Passage,
  PresentationArtifactStatus,
  PresentationEvidenceItem,
  Source,
} from "@/lib/api";
import { AnalysisAuditDrawer } from "@/components/analysis/analysis-audit-drawer";
import { useAnalysisDetail } from "@/components/analysis/use-analysis-detail";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/ui/data-state";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

type AnalysisDetailClientProps = {
  analysisId: string;
};

type AuditFocus = {
  section?: "scoring" | "uncertainty" | "recommendation" | "grounding" | "factors";
  factorId?: number | null;
  passageId?: number | null;
};

const detailNavItems = [
  { id: "analysis-summary", label: "Summary" },
  { id: "analysis-memo", label: "Memo" },
  { id: "analysis-social", label: "Social" },
  { id: "analysis-sources", label: "Sources" },
  { id: "analysis-status", label: "Status" },
  { id: "analysis-market", label: "Market" },
  { id: "analysis-rules", label: "Rules" },
];

function badgeVariant(label: string | null | undefined) {
  if (!label) {
    return "muted" as const;
  }
  if (
    label.includes("yes") ||
    label === "high" ||
    label === "complete" ||
    label === "supported" ||
    label === "bullish" ||
    label === "ready"
  ) {
    return "yes" as const;
  }
  if (label.includes("no") || label === "failed" || label === "rejected" || label === "bearish") {
    return "no" as const;
  }
  return "warning" as const;
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "Pending";
  }
  const percentage = value * 100;
  const rounded = Math.round(percentage);
  if (Math.abs(percentage - rounded) >= 0.05) {
    return `${percentage.toFixed(1)}%`;
  }
  return `${rounded}%`;
}

function complementProbability(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return null;
  }
  return Math.min(Math.max(1 - value, 0), 1);
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleString();
}

function humanizeLabel(value: string | null | undefined) {
  if (!value) {
    return "Unavailable";
  }
  return value.replaceAll("_", " ");
}

function articleForPhrase(value: string) {
  return /^[aeiou]/i.test(value.trim()) ? "an" : "a";
}

function sentenceCaseLabel(value: string | null | undefined) {
  const humanized = humanizeLabel(value);
  if (!humanized) {
    return "Unavailable";
  }
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
}

function decisionHeadlineFromRead(
  pHat: number | null | undefined,
  qualitativeLabel: string | null | undefined,
) {
  if (pHat !== null && pHat !== undefined) {
    if (pHat > 0.5) {
      return "Most likely: YES";
    }
    if (pHat < 0.5) {
      return "Most likely: NO";
    }
    return "Near coin flip";
  }
  if (qualitativeLabel === "leans_yes") {
    return "Most likely: YES";
  }
  if (qualitativeLabel === "leans_no") {
    return "Most likely: NO";
  }
  if (qualitativeLabel === "mixed") {
    return "Near coin flip";
  }
  return "No directional read yet";
}

function formatCount(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`;
}

function formatEdgePoints(value: number) {
  const points = value * 100;
  const sign = points > 0 ? "+" : "";
  return `${sign}${points.toFixed(1)} pts`;
}

function edgeTone(value: number) {
  if (Math.abs(value) < 0.005) {
    return "text-ink/60";
  }
  return value > 0 ? "text-pine" : "text-ember";
}

function edgeNote(value: number) {
  if (Math.abs(value) < 0.005) {
    return "The desk read matches the market price — no edge either way.";
  }
  if (value > 0) {
    return "The desk sees YES as more likely than the market is pricing.";
  }
  return "The desk sees YES as less likely than the market is pricing.";
}

function formatElapsed(startedAt: string | null | undefined, completedAt?: string | null | undefined) {
  if (!startedAt) {
    return "Not started";
  }
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const totalSeconds = Math.max(0, Math.floor((end - start) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function sourceMeta(source: Source, key: string): unknown {
  return source.metadata_json?.[key];
}

function sourceMetaString(source: Source, key: string): string | null {
  const value = sourceMeta(source, key);
  return typeof value === "string" && value.trim() ? value : null;
}

function sourceMetaNumber(source: Source, key: string): number | null {
  const value = sourceMeta(source, key);
  return typeof value === "number" ? value : null;
}

function normalizeSocialHandle(value: string | null): string | null {
  const normalized = value?.replace(/^@+/, "").trim();
  return normalized || null;
}

function scrollToDetailSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ block: "start", behavior: "smooth" });
}

function SectionPlaceholder({ title, note }: { title: string; note: string }) {
  return (
    <article className="rounded-lg border border-dashed border-black/10 bg-white/60 p-4">
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm leading-6 text-ink/60">{note}</p>
      <div className="mt-4 space-y-2 animate-pulse">
        <div className="h-2.5 w-3/4 rounded-full bg-black/5" />
        <div className="h-2.5 w-5/6 rounded-full bg-black/5" />
        <div className="h-2.5 w-2/3 rounded-full bg-black/5" />
      </div>
    </article>
  );
}

function MemoEvidenceItem({
  item,
  onInspect,
}: {
  item: PresentationEvidenceItem;
  onInspect: () => void;
}) {
  return (
    <article className="border-b border-black/10 py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-base font-semibold text-ink">{item.title}</p>
          {item.note ? <p className="mt-1 text-sm leading-6 text-ink/60">{item.note}</p> : null}
        </div>
        {item.factor_id ? (
          <button
            type="button"
            onClick={onInspect}
            className="quiet-action shrink-0"
          >
            Inspect
          </button>
        ) : null}
      </div>
    </article>
  );
}

function SocialTimelineCard({ source }: { source: Source }) {
  const displayName = sourceMetaString(source, "display_name") ?? source.title ?? "Trusted account";
  const trustReason = sourceMetaString(source, "trust_reason");
  const relevanceReason = sourceMetaString(source, "relevance_reason");
  const handle = normalizeSocialHandle(sourceMetaString(source, "handle"));
  const trustConfidence = sourceMetaNumber(source, "trust_confidence");

  return (
    <article className="border-b border-black/10 py-4 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={badgeVariant(source.source_tier)}>{source.source_tier}</Badge>
        <span className="text-[10px] uppercase tracking-[0.16em] text-ink/40">
          {formatDate(source.published_at)}
        </span>
      </div>
      <p className="mt-2 text-base font-semibold text-ink">{displayName}</p>
      <p className="mt-1 text-sm leading-6 text-ink/70">{source.excerpt}</p>
      {trustReason ? (
        <p className="mt-2 text-sm leading-6 text-ink/60">
          <span className="font-semibold text-ink">Why trusted:</span> {trustReason}
        </p>
      ) : null}
      {relevanceReason ? (
        <p className="mt-2 text-sm leading-6 text-ink/60">
          <span className="font-semibold text-ink">Why relevant:</span> {relevanceReason}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-ink/60">
        {handle ? <span>@{handle}</span> : null}
        {trustConfidence !== null ? <span>{Math.round(trustConfidence * 100)}% trust confidence</span> : null}
        {source.url ? (
          <Link
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-pine"
          >
            Open post
          </Link>
        ) : null}
      </div>
    </article>
  );
}

function SocialConsensusSnapshot({ summary }: { summary: SocialIntelSummary }) {
  const consensusLabel = humanizeLabel(summary.consensus_label);
  const consensusStrength = humanizeLabel(summary.consensus_strength);
  const narrativePhase = humanizeLabel(summary.narrative_phase);
  const themes = summary.key_themes ?? [];
  const crowdTreatment =
    summary.broad_posts_sampled <= 0
      ? "No crowd signal"
      : summary.consensus_label === "bullish"
        ? "Capped YES nudge"
        : summary.consensus_label === "bearish"
          ? "Capped NO nudge"
          : "Uncertainty only";

  return (
    <article className="rounded-lg border border-black/10 bg-white/70 p-4">
      <p className="section-label">Broader X consensus</p>
      <p className="mt-3 text-xl font-semibold text-ink">
        {sentenceCaseLabel(consensusLabel)} with {consensusStrength} conviction
      </p>
      <p className="mt-2 max-w-4xl text-sm leading-6 text-ink/60">
        Broader X discussion currently reads as {consensusLabel} with {consensusStrength} conviction in{" "}
        {articleForPhrase(narrativePhase)}{" "}
        {narrativePhase} phase.
      </p>
      <p className="mt-3 max-w-4xl text-sm leading-6 text-ink/70">{summary.summary}</p>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-l border-black/10 pl-3">
          <p className="section-label">Consensus</p>
          <p className="mt-2 text-sm font-semibold capitalize text-ink">{consensusLabel}</p>
        </div>
        <div className="border-l border-black/10 pl-3">
          <p className="section-label">Posts sampled</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {formatCount(summary.broad_posts_sampled, "post")}
          </p>
        </div>
        <div className="border-l border-black/10 pl-3">
          <p className="section-label">Trusted accounts retained</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {formatCount(summary.trusted_accounts_count, "account")}
          </p>
        </div>
        <div className="border-l border-black/10 pl-3">
          <p className="section-label">Crowd lane</p>
          <p className="mt-2 text-sm font-semibold text-ink">{crowdTreatment}</p>
        </div>
      </div>

      {themes.length ? (
        <div className="mt-5 space-y-3">
          <p className="section-label">Key themes</p>
          <div className="flex flex-wrap gap-2">
            {themes.map((theme) => (
              <Badge key={theme} variant="muted">
                {theme}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function ArtifactRow({ artifact }: { artifact: PresentationArtifactStatus }) {
  return (
    <article className="border-b border-black/10 py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-ink">{artifact.label}</p>
        <Badge variant={badgeVariant(artifact.status)}>{artifact.status}</Badge>
      </div>
      <p className="mt-1 text-sm leading-6 text-ink/60">{artifact.note ?? "No stage note stored."}</p>
    </article>
  );
}

export function AnalysisDetailClient({ analysisId }: AnalysisDetailClientProps) {
  const { detail, error, isRerunning, handleRerun, refreshDetail } = useAnalysisDetail(analysisId);
  const [isAuditOpen, setIsAuditOpen] = useState(false);
  const [auditFocus, setAuditFocus] = useState<AuditFocus | null>(null);

  const artifactStatusMap = useMemo(() => {
    const map = new Map<string, PresentationArtifactStatus>();
    for (const item of detail?.presentation.artifact_statuses ?? []) {
      map.set(item.key, item);
    }
    return map;
  }, [detail]);

  const trustedSocialSources = useMemo(
    () =>
      [...(detail?.trusted_social_sources ?? [])].sort((left, right) =>
        (right.published_at ?? "").localeCompare(left.published_at ?? ""),
      ),
    [detail],
  );
  const nonSocialSources = useMemo(
    () =>
      (detail?.sources ?? []).filter((source) => !["manual_social", "live_social"].includes(source.source_kind)),
    [detail],
  );
  const documentsBySource = useMemo(() => {
    const grouped = new Map<number, { extractor: string | null; wordCount: number }>();
    for (const document of detail?.documents ?? []) {
      grouped.set(document.source_id, {
        extractor: document.extractor,
        wordCount: document.word_count,
      });
    }
    return grouped;
  }, [detail]);
  const passagesBySource = useMemo(() => {
    const grouped = new Map<number, Passage[]>();
    for (const passage of detail?.passages ?? []) {
      const existing = grouped.get(passage.source_id) ?? [];
      existing.push(passage);
      grouped.set(passage.source_id, existing);
    }
    for (const [sourceId, passages] of grouped.entries()) {
      grouped.set(
        sourceId,
        [...passages].sort(
          (left, right) => right.relevance_score - left.relevance_score || left.passage_index - right.passage_index,
        ),
      );
    }
    return grouped;
  }, [detail]);

  if (error) {
    return (
      <Panel className="p-8">
        <p className="eyebrow">Analysis detail</p>
        <p className="mt-4 text-sm leading-7 text-ember">{error}</p>
      </Panel>
    );
  }

  if (!detail) {
    return (
      <Panel className="p-8">
        <p className="eyebrow">Analysis detail</p>
        <div className="mt-5 animate-pulse space-y-4">
          <div className="h-3 w-32 rounded-full bg-black/10" />
          <div className="h-12 w-5/6 rounded-lg bg-black/10" />
          <div className="h-4 w-4/5 rounded-full bg-black/10" />
        </div>
      </Panel>
    );
  }

  const isRunning = ["queued", "running"].includes(detail.request.status);
  const isFailed = detail.request.status === "failed";
  const hasProbabilityRange =
    detail.latest_run?.p_low !== null &&
    detail.latest_run?.p_low !== undefined &&
    detail.latest_run?.p_high !== null &&
    detail.latest_run?.p_high !== undefined;
  const hasPointEstimate =
    detail.latest_run?.p_hat !== null && detail.latest_run?.p_hat !== undefined;
  const qualitativeLabel = detail.latest_run?.qualitative_label ?? detail.request.qualitative_label ?? null;
  const lastUpdated = detail.last_updated_at ?? detail.progress.last_updated_at;
  const displayedStartedAt = detail.request.started_at ?? detail.latest_run?.created_at ?? null;
  const whyYes = detail.presentation.brief_sections.why_yes ?? [];
  const whyNo = detail.presentation.brief_sections.why_no ?? [];
  const contextItems = detail.presentation.brief_sections.context ?? [];
  const artifactStatuses = detail.presentation.artifact_statuses ?? [];
  const noPointEstimate = complementProbability(detail.latest_run?.p_hat);
  const recommendationLabel =
    detail.recommendation?.recommendation_label ??
    detail.latest_run?.recommendation_label ??
    detail.request.latest_recommendation_label ??
    null;
  const isAnalysisOnlyRecommendation = recommendationLabel === "analysis_only";
  const decisionHeadline = decisionHeadlineFromRead(detail.latest_run?.p_hat, qualitativeLabel);
  const recommendationHeadline = isAnalysisOnlyRecommendation
    ? decisionHeadline
    : sentenceCaseLabel(recommendationLabel ?? "pending");
  const recommendationNote = isAnalysisOnlyRecommendation
    ? hasPointEstimate
      ? detail.market
        ? "Trade edge is separate; this card shows the model's directional read."
        : "No linked Polymarket market was available, so this is a decision read rather than an executable trade call."
      : detail.market
        ? "The model could not form a directional read from the available evidence yet."
        : "No linked Polymarket market was available, and the available evidence did not form a directional read yet."
    : null;
  const marketPrior = detail.latest_run?.market_mid_prob;
  const hasMarketPrior = marketPrior !== null && marketPrior !== undefined;
  const probabilityTitle = hasPointEstimate ? "Model YES read" : hasProbabilityRange ? "Probability range" : "Probability";
  const probabilityValue = hasPointEstimate
    ? formatPercent(detail.latest_run?.p_hat)
    : hasProbabilityRange
      ? `${formatPercent(detail.latest_run?.p_low)} - ${formatPercent(detail.latest_run?.p_high)}`
      : "No estimate";
  const probabilityNote =
    !hasPointEstimate && !hasProbabilityRange && qualitativeLabel
      ? `Qualitative read: ${humanizeLabel(qualitativeLabel)}.`
      : null;
  const openAudit = (focus?: AuditFocus) => {
    refreshDetail();
    setAuditFocus(focus ?? null);
    setIsAuditOpen(true);
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_21rem]">
      <AnalysisAuditDrawer
        audit={detail.audit ?? null}
        documents={detail.documents ?? []}
        open={isAuditOpen}
        onClose={() => setIsAuditOpen(false)}
        passages={detail.passages ?? []}
        sources={detail.sources ?? []}
        focus={auditFocus}
      />

      <div className="min-w-0 space-y-6 break-words">
        <section id="analysis-summary" className="scroll-mt-24 border-b border-black/10 pb-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={badgeVariant(detail.request.status)}>{detail.request.status}</Badge>
            {detail.request.template_selected ? (
              <Badge variant="muted">{humanizeLabel(detail.request.template_selected)}</Badge>
            ) : null}
            {detail.latest_run?.confidence_label ? (
              <Badge variant={badgeVariant(detail.latest_run.confidence_label)}>
                {humanizeLabel(detail.latest_run.confidence_label)}
              </Badge>
            ) : null}
            {detail.latest_run?.priced_in_risk_label ? (
              <Badge variant={badgeVariant(detail.latest_run.priced_in_risk_label)}>
                priced-in {humanizeLabel(detail.latest_run.priced_in_risk_label)}
              </Badge>
            ) : null}
          </div>
          <h1 className="mt-4 max-w-5xl font-serif text-3xl leading-[1.06] text-ink sm:text-4xl">
            {detail.presentation.headline}
          </h1>
          <p className="mt-3 max-w-4xl text-base leading-7 text-ink/70">{detail.presentation.thesis}</p>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-ink/60">{detail.presentation.status_note}</p>
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-ink/60">
            <span>Last updated {formatDate(lastUpdated)}</span>
            <span>Elapsed {formatElapsed(displayedStartedAt, detail.request.completed_at)}</span>
            {detail.progress.current_label ? <span>Current stage: {detail.progress.current_label}</span> : null}
          </div>
          {isRunning || isFailed ? (
            <div className="mt-4 max-w-4xl">
              <div className="mb-2 flex items-center justify-between gap-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink/50">
                <span>{isFailed ? "Stopped" : detail.progress.current_label ?? "Running"}</span>
                <span>{detail.progress.percent_complete}%</span>
              </div>
              <div className="h-2 rounded-full bg-black/5">
                <div
                  className={`h-2 rounded-full transition-all ${isFailed ? "bg-ember" : "bg-pine"}`}
                  style={{ width: `${Math.max(8, detail.progress.percent_complete)}%` }}
                />
              </div>
            </div>
          ) : null}
          {isFailed ? (
            <DataState
              variant="error"
              title="This run failed before completing"
              note={detail.request.error_message ?? "The run stopped before completion."}
              onRetry={isRerunning ? undefined : () => void handleRerun()}
              retryLabel={isRerunning ? "Rerunning..." : "Rerun analysis"}
              className="mt-4 max-w-4xl"
            />
          ) : null}
        </section>

        <Panel className="p-4 xl:hidden">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="section-label">Run status</p>
              <p className="mt-1 text-sm font-semibold text-ink">
                {detail.progress.percent_complete}%
                {" · "}
                {isFailed ? "Stopped" : detail.progress.current_label ?? detail.request.status}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => openAudit({ section: "scoring" })}
                disabled={!detail.audit}
                className="primary-action"
              >
                How this was calculated
              </button>
              <button
                type="button"
                onClick={handleRerun}
                disabled={isRerunning || isRunning}
                className="secondary-action"
              >
                {isRerunning ? "Rerunning..." : "Rerun"}
              </button>
            </div>
          </div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {detailNavItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => scrollToDetailSection(item.id)}
                className="quiet-action shrink-0 whitespace-nowrap"
              >
                {item.label}
              </button>
            ))}
          </div>
        </Panel>

        <Panel className="p-5">
          <div className="grid gap-5 sm:grid-cols-3">
            <div>
              <p className="section-label">{probabilityTitle}</p>
              <p className="stat-number mt-2">{probabilityValue}</p>
              <p className="mt-2 text-sm leading-6 text-ink/60">
                {hasPointEstimate
                  ? `NO ${formatPercent(noPointEstimate)}`
                  : hasProbabilityRange
                    ? "This run produced a probability band without a single-point estimate."
                    : [probabilityNote, detail.latest_run?.numeric_estimate_reason]
                        .filter(Boolean)
                        .join(" ") || "This run stayed qualitative-only."}
              </p>
            </div>
            {hasPointEstimate && hasMarketPrior && marketPrior !== null && marketPrior !== undefined ? (
              <>
                <div>
                  <p className="section-label">Edge vs market</p>
                  <p
                    className={cn(
                      "mt-2 font-serif text-4xl font-medium leading-none tracking-[-0.01em] lining-nums tabular-nums",
                      edgeTone((detail.latest_run?.p_hat ?? 0) - marketPrior),
                    )}
                  >
                    {formatEdgePoints((detail.latest_run?.p_hat ?? 0) - marketPrior)}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-ink/60">
                    {edgeNote((detail.latest_run?.p_hat ?? 0) - marketPrior)}
                  </p>
                </div>
                <div>
                  <p className="section-label">Polymarket prior</p>
                  <p className="stat-number mt-2">{formatPercent(marketPrior)}</p>
                  <p className="mt-2 text-sm leading-6 text-ink/60">
                    YES midpoint before evidence adjustments.
                  </p>
                </div>
              </>
            ) : (
              <div className="sm:col-span-2 sm:border-l sm:border-black/10 sm:pl-5">
                <p className="section-label">Edge vs market</p>
                <p className="mt-2 text-sm leading-7 text-ink/60">
                  {hasMarketPrior
                    ? "The market prior is linked, but this run has no point estimate to compare against it yet."
                    : "No linked Polymarket market — this is an analysis-only read. There is no executable edge, and nothing here implies a trade."}
                </p>
                {hasMarketPrior ? (
                  <p className="mt-2 text-sm leading-6 text-ink/60">
                    Market prior: <span className="font-semibold text-ink">{formatPercent(marketPrior)}</span>
                  </p>
                ) : null}
              </div>
            )}
          </div>
        </Panel>

        <section className="grid gap-3 sm:grid-cols-2">
          <Panel className="p-4">
            <p className="section-label">Recommendation</p>
            <p className="mt-3 text-lg font-semibold text-ink">
              {recommendationHeadline}
            </p>
            {recommendationNote ? <p className="mt-2 text-sm leading-6 text-ink/60">{recommendationNote}</p> : null}
          </Panel>
          <Panel className="p-4">
            <p className="section-label">Confidence</p>
            <p className="mt-3 text-lg font-semibold capitalize text-ink">
              {humanizeLabel(detail.latest_run?.confidence_label ?? "pending")}
            </p>
          </Panel>
        </section>

        <Panel id="analysis-memo" className="scroll-mt-24 space-y-5 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Working memo</p>
            <h2 className="mt-1.5 font-serif text-3xl text-ink">What this means</h2>
          </div>
          {artifactStatusMap.get("brief_generation")?.available || !isRunning ? (
            <p className="max-w-4xl text-base leading-7 text-ink/70">
              {detail.presentation.brief_sections.what_it_means}
            </p>
          ) : (
            <SectionPlaceholder
              title="Brief being written"
              note={artifactStatusMap.get("brief_generation")?.note ?? "The final memo language will replace this placeholder once the brief stage finishes."}
            />
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-serif text-2xl text-ink">Why yes</h3>
                {whyYes.length ? <Badge variant="yes">scored evidence</Badge> : null}
              </div>
              {whyYes.length ? (
                whyYes.map((item) => (
                  <MemoEvidenceItem
                    key={`yes-${item.factor_id ?? item.title}`}
                    item={item}
                    onInspect={() => openAudit({ section: "factors", factorId: item.factor_id })}
                  />
                ))
              ) : (
                <SectionPlaceholder
                  title={isFailed ? "Factor scoring did not finish" : "Factors being scored"}
                  note={
                    isRunning
                      ? artifactStatusMap.get("factor_mapping")?.note ?? "Directional YES evidence will appear here after factor mapping finishes."
                      : isFailed
                        ? "The run stopped before YES-side evidence could be scored. Rerun the analysis to complete it."
                        : "This run did not surface scored YES-side evidence."
                  }
                />
              )}
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-serif text-2xl text-ink">Why no</h3>
                {whyNo.length ? <Badge variant="no">scored evidence</Badge> : null}
              </div>
              {whyNo.length ? (
                whyNo.map((item) => (
                  <MemoEvidenceItem
                    key={`no-${item.factor_id ?? item.title}`}
                    item={item}
                    onInspect={() => openAudit({ section: "factors", factorId: item.factor_id })}
                  />
                ))
              ) : (
                <SectionPlaceholder
                  title={isFailed ? "Factor scoring did not finish" : "Factors being scored"}
                  note={
                    isRunning
                      ? artifactStatusMap.get("factor_mapping")?.note ?? "Directional NO evidence will appear here after factor mapping finishes."
                      : isFailed
                        ? "The run stopped before NO-side evidence could be scored. Rerun the analysis to complete it."
                        : "This run did not surface scored NO-side evidence."
                  }
                />
              )}
            </div>
          </div>

          <div className="memo-rule space-y-4 pt-5">
            <h3 className="font-serif text-2xl text-ink">Context / not scored</h3>
            {contextItems.length ? (
              <div>
                {contextItems.map((item) => (
                  <MemoEvidenceItem
                    key={`context-${item.factor_id ?? item.title}`}
                    item={item}
                    onInspect={() => openAudit({ section: "factors", factorId: item.factor_id })}
                  />
                ))}
              </div>
            ) : (
              <SectionPlaceholder
                title={isFailed ? "Context assembly did not finish" : "Context still assembling"}
                note={
                  isRunning
                    ? artifactStatusMap.get("factor_mapping")?.note ?? "Contextual and non-scored evidence will appear here once factor mapping finishes."
                    : isFailed
                      ? "The run stopped before contextual evidence was assembled."
                      : "No contextual-only evidence was stored for this run."
                }
              />
            )}
          </div>

          <div className="memo-rule space-y-3 pt-5">
            <h3 className="font-serif text-2xl text-ink">Why this could be wrong</h3>
            <p className="max-w-4xl text-sm leading-7 text-ink/70">
              {detail.presentation.brief_sections.caveats}
            </p>
          </div>
        </Panel>

        <Panel id="analysis-social" className="scroll-mt-24 space-y-5 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Social intelligence</p>
            <h2 className="mt-1.5 font-serif text-3xl text-ink">Trusted accounts and narrative context</h2>
          </div>
          {detail.social_intel_summary ? (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <Badge variant={badgeVariant(detail.social_intel_summary.consensus_label)}>
                  {humanizeLabel(detail.social_intel_summary.consensus_label)}
                </Badge>
                <Badge variant={badgeVariant(detail.social_intel_summary.consensus_strength)}>
                  {humanizeLabel(detail.social_intel_summary.consensus_strength)}
                </Badge>
                <Badge variant={badgeVariant(detail.social_intel_summary.narrative_phase)}>
                  {humanizeLabel(detail.social_intel_summary.narrative_phase)}
                </Badge>
              </div>
              <SocialConsensusSnapshot summary={detail.social_intel_summary} />
              {trustedSocialSources.length ? (
                <div>
                  {trustedSocialSources.map((source) => (
                    <SocialTimelineCard key={source.id} source={source} />
                  ))}
                </div>
              ) : (
                <SectionPlaceholder
                  title="Trusted-account timeline unavailable"
                  note="Broader X consensus was captured above, but no trusted live-account posts met the persistence threshold for timeline display in this run."
                />
              )}
            </div>
          ) : (
            <SectionPlaceholder
              title={artifactStatusMap.get("social_intelligence")?.label ?? "Social intelligence"}
              note={
                artifactStatusMap.get("social_intelligence")?.note ??
                "Live X intelligence was skipped or not available for this run."
              }
            />
          )}
        </Panel>

        <Panel id="analysis-sources" className="scroll-mt-24 space-y-5 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Sources</p>
            <h2 className="mt-1.5 font-serif text-3xl text-ink">Source material and grounded passages</h2>
          </div>

          {nonSocialSources.length ? (
            <div>
              {nonSocialSources.map((source) => {
                const grounding = documentsBySource.get(source.id);
                const passages = passagesBySource.get(source.id) ?? [];
                return (
                  <article key={source.id} className="border-b border-black/10 py-5 first:pt-0 last:border-b-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="muted">{source.source_kind}</Badge>
                      <Badge variant="muted">{source.source_tier}</Badge>
                      {grounding?.extractor ? <Badge variant="muted">{grounding.extractor}</Badge> : null}
                    </div>
                    <p className="mt-3 text-lg font-semibold text-ink">{source.title ?? source.domain ?? "Untitled source"}</p>
                    <p className="mt-1 text-sm leading-6 text-ink/70">{source.excerpt}</p>

                    {passages.length ? (
                      <div className="mt-4 space-y-3">
                        <div className="flex items-center justify-between gap-4">
                          <p className="section-label">
                            Ranked grounding passages
                          </p>
                          <button
                            type="button"
                            onClick={() => openAudit({ section: "grounding", passageId: passages[0].id })}
                            className="quiet-action"
                          >
                            Inspect grounding
                          </button>
                        </div>
                        {passages.slice(0, 2).map((passage) => (
                          <article key={passage.id} className="rounded-lg border border-black/10 bg-white/70 px-4 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="muted">passage {passage.passage_index}</Badge>
                              <span className="text-[10px] uppercase tracking-[0.16em] text-ink/40">
                                relevance {passage.relevance_score.toFixed(2)}
                              </span>
                            </div>
                            <p className="mt-3 text-sm leading-6 text-ink/70">{passage.text}</p>
                          </article>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-ink/60">
                      {grounding ? <span>{grounding.wordCount} words grounded</span> : null}
                      {source.url ? (
                        <Link
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-pine"
                        >
                          Open source
                        </Link>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <SectionPlaceholder
              title={artifactStatusMap.get("retrieval")?.label ?? "Sources grounded"}
              note={
                artifactStatusMap.get("retrieval")?.note ??
                "Sources will appear here once retrieval and grounding finish."
              }
            />
          )}
        </Panel>
      </div>

      <aside className="min-w-0 space-y-5 break-words xl:sticky xl:top-24 xl:self-start">
        <Panel className="space-y-4 p-4">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Actions</p>
            <p className="mt-2 text-sm leading-6 text-ink/60">
              Open the inspector, rerun the desk, or return to the research log.
            </p>
          </div>
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => openAudit({ section: "scoring" })}
              disabled={!detail.audit}
              className="primary-action w-full"
            >
              How this was calculated
            </button>
            <button
              type="button"
              onClick={handleRerun}
              disabled={isRerunning || isRunning}
              className="secondary-action w-full"
            >
              {isRerunning ? "Rerunning..." : isRunning ? "Analysis running" : "Rerun analysis"}
            </button>
            <Link
              href="/history"
              className="secondary-action w-full"
            >
              Back to research log
            </Link>
          </div>
        </Panel>

        <Panel className="space-y-4 p-4">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Jump to</p>
            <p className="mt-2 text-sm leading-6 text-ink/60">
              Move between the main read, evidence, and run metadata.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {detailNavItems.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => scrollToDetailSection(item.id)}
                className="quiet-action justify-center"
              >
                {item.label}
              </button>
            ))}
          </div>
        </Panel>

        <Panel id="analysis-status" className="scroll-mt-24 space-y-4 p-4">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Run status</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{detail.progress.percent_complete}%</p>
            <p className="mt-2 text-sm leading-6 text-ink/60">
              {isFailed
                ? detail.request.error_message ?? "The run stopped before completion."
                : detail.progress.current_note ?? "Waiting for the next stage."}
            </p>
          </div>
          <div className="h-1.5 rounded-full bg-black/5">
            <div
              className={`h-1.5 rounded-full transition-all ${
                isFailed ? "bg-ember" : "bg-pine"
              }`}
              style={{ width: `${Math.max(8, detail.progress.percent_complete)}%` }}
            />
          </div>
          <div className="space-y-3">
            {artifactStatuses.map((artifact) => (
              <ArtifactRow key={artifact.key} artifact={artifact} />
            ))}
          </div>
        </Panel>

        <Panel id="analysis-market" className="scroll-mt-24 space-y-4 p-4">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Market context</p>
            <h3 className="mt-2 text-lg font-semibold text-ink">
              {detail.market?.title ?? "Analysis-only run"}
            </h3>
          </div>
          <div className="space-y-2 text-sm leading-7 text-ink/60">
            <p>{detail.market?.url ? "Linked to a Polymarket market." : "No linked market was used for this run."}</p>
            {detail.market ? (
              <>
                <p>Liquidity: {detail.market.liquidity ?? "n/a"}</p>
                <p>Spread: {detail.market.spread ?? "n/a"}</p>
                <p>Status: {detail.market.status ?? "n/a"}</p>
              </>
            ) : null}
          </div>
        </Panel>

        <Panel id="analysis-rules" className="scroll-mt-24 space-y-4 p-4">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Rule parse</p>
            <h3 className="mt-2 text-lg font-semibold text-ink">
              {detail.latest_rule_parse?.template_detected ?? "Pending"}
            </h3>
          </div>
          {detail.latest_rule_parse ? (
            <div className="space-y-3 text-sm leading-7 text-ink/60">
              <p>
                <span className="font-semibold text-ink">Claim family:</span>{" "}
                {humanizeLabel(detail.latest_rule_parse.claim_family)}
              </p>
              <p>
                <span className="font-semibold text-ink">YES:</span> {detail.latest_rule_parse.yes_condition}
              </p>
              <p>
                <span className="font-semibold text-ink">NO:</span> {detail.latest_rule_parse.no_condition}
              </p>
              <p>
                <span className="font-semibold text-ink">Clarity / risk:</span>{" "}
                {detail.latest_rule_parse.clarity_score.toFixed(2)} / {detail.latest_rule_parse.resolution_risk.toFixed(2)}
              </p>
            </div>
          ) : (
            <SectionPlaceholder
              title={artifactStatusMap.get("rule_parse")?.label ?? "Rules interpreted"}
              note={artifactStatusMap.get("rule_parse")?.note ?? "The parsed proposition will appear here."}
            />
          )}
        </Panel>
      </aside>
    </div>
  );
}
