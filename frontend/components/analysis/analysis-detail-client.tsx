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
import { Panel } from "@/components/ui/panel";

type AnalysisDetailClientProps = {
  analysisId: string;
};

type AuditFocus = {
  section?: "scoring" | "uncertainty" | "recommendation" | "grounding" | "factors";
  factorId?: number | null;
  passageId?: number | null;
};

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

function formatCount(value: number, singular: string, plural = `${singular}s`) {
  return `${value} ${value === 1 ? singular : plural}`;
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

function SectionPlaceholder({ title, note }: { title: string; note: string }) {
  return (
    <article className="rounded-[16px] border border-dashed border-black/10 bg-[rgba(255,255,255,0.45)] p-5">
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm leading-7 text-ink/58">{note}</p>
      <div className="mt-4 space-y-2 animate-pulse">
        <div className="h-2.5 w-3/4 rounded-full bg-black/7" />
        <div className="h-2.5 w-5/6 rounded-full bg-black/7" />
        <div className="h-2.5 w-2/3 rounded-full bg-black/7" />
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
    <article className="border-b border-black/8 pb-4 last:border-b-0 last:pb-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-base font-semibold text-ink">{item.title}</p>
          {item.note ? <p className="mt-2 text-sm leading-7 text-ink/60">{item.note}</p> : null}
        </div>
        {item.factor_id ? (
          <button
            type="button"
            onClick={onInspect}
            className="rounded-full border border-black/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-ink/62 transition hover:bg-black/5"
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
  const handle = sourceMetaString(source, "handle");
  const trustConfidence = sourceMetaNumber(source, "trust_confidence");

  return (
    <article className="border-b border-black/8 pb-4 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={badgeVariant(source.source_tier)}>{source.source_tier}</Badge>
        <span className="text-[10px] uppercase tracking-[0.16em] text-ink/42">
          {formatDate(source.published_at)}
        </span>
      </div>
      <p className="mt-3 text-base font-semibold text-ink">{displayName}</p>
      <p className="mt-2 text-sm leading-7 text-ink/66">{source.excerpt}</p>
      {trustReason ? (
        <p className="mt-2 text-sm leading-7 text-ink/58">
          <span className="font-semibold text-ink">Why trusted:</span> {trustReason}
        </p>
      ) : null}
      {relevanceReason ? (
        <p className="mt-2 text-sm leading-7 text-ink/58">
          <span className="font-semibold text-ink">Why relevant:</span> {relevanceReason}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-ink/54">
        {handle ? <span>@{handle}</span> : null}
        {trustConfidence !== null ? <span>{Math.round(trustConfidence * 100)}% trust confidence</span> : null}
        {source.url ? (
          <Link href={source.url} target="_blank" className="font-medium text-ember">
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

  return (
    <article className="rounded-[18px] border border-black/8 bg-[rgba(255,255,255,0.56)] p-5">
      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Broader X consensus</p>
      <p className="mt-3 text-xl font-semibold capitalize text-ink">
        {consensusLabel} with {consensusStrength} conviction
      </p>
      <p className="mt-2 max-w-4xl text-sm leading-7 text-ink/60">
        Broader X discussion currently reads as {consensusLabel} with {consensusStrength} conviction in an{" "}
        {narrativePhase} phase.
      </p>
      <p className="mt-3 max-w-4xl text-sm leading-7 text-ink/66">{summary.summary}</p>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-[14px] border border-black/8 bg-white/55 px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Consensus</p>
          <p className="mt-2 text-sm font-semibold capitalize text-ink">{consensusLabel}</p>
        </div>
        <div className="rounded-[14px] border border-black/8 bg-white/55 px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Posts sampled</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {formatCount(summary.broad_posts_sampled, "post")}
          </p>
        </div>
        <div className="rounded-[14px] border border-black/8 bg-white/55 px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Trusted accounts retained</p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {formatCount(summary.trusted_accounts_count, "account")}
          </p>
        </div>
      </div>

      {themes.length ? (
        <div className="mt-5 space-y-3">
          <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Key themes</p>
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
    <article className="border-b border-black/8 pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-ink">{artifact.label}</p>
        <Badge variant={badgeVariant(artifact.status)}>{artifact.status}</Badge>
      </div>
      <p className="mt-2 text-sm leading-7 text-ink/58">{artifact.note ?? "No stage note stored."}</p>
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
        <p className="text-[10px] uppercase tracking-[0.22em] text-ember/76">Analysis detail</p>
        <p className="mt-4 text-sm leading-7 text-ember">{error}</p>
      </Panel>
    );
  }

  if (!detail) {
    return (
      <Panel className="p-8">
        <p className="text-[10px] uppercase tracking-[0.22em] text-ember/76">Analysis detail</p>
        <div className="mt-5 animate-pulse space-y-4">
          <div className="h-3 w-32 rounded-full bg-black/8" />
          <div className="h-12 w-5/6 rounded-[18px] bg-black/8" />
          <div className="h-4 w-4/5 rounded-full bg-black/8" />
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
  const whyYes = detail.presentation.brief_sections.why_yes ?? [];
  const whyNo = detail.presentation.brief_sections.why_no ?? [];
  const contextItems = detail.presentation.brief_sections.context ?? [];
  const artifactStatuses = detail.presentation.artifact_statuses ?? [];
  const noPointEstimate = complementProbability(detail.latest_run?.p_hat);
  const openAudit = (focus?: AuditFocus) => {
    refreshDetail();
    setAuditFocus(focus ?? null);
    setIsAuditOpen(true);
  };

  return (
    <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <AnalysisAuditDrawer
        audit={detail.audit ?? null}
        documents={detail.documents ?? []}
        open={isAuditOpen}
        onClose={() => setIsAuditOpen(false)}
        passages={detail.passages ?? []}
        sources={detail.sources ?? []}
        focus={auditFocus}
      />

      <div className="space-y-8">
        <section className="border-b border-black/8 pb-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={badgeVariant(detail.request.status)}>{detail.request.status}</Badge>
            {detail.request.template_selected ? <Badge variant="muted">{detail.request.template_selected}</Badge> : null}
            {detail.latest_run?.confidence_label ? (
              <Badge variant={badgeVariant(detail.latest_run.confidence_label)}>{detail.latest_run.confidence_label}</Badge>
            ) : null}
            {detail.latest_run?.priced_in_risk_label ? (
              <Badge variant={badgeVariant(detail.latest_run.priced_in_risk_label)}>
                priced-in {detail.latest_run.priced_in_risk_label}
              </Badge>
            ) : null}
          </div>
          <h1 className="mt-5 max-w-5xl font-serif text-5xl leading-[0.98] text-ink md:text-6xl">
            {detail.presentation.headline}
          </h1>
          <p className="mt-4 max-w-4xl text-lg leading-8 text-ink/72">{detail.presentation.thesis}</p>
          <p className="mt-3 max-w-4xl text-sm leading-7 text-ink/58">{detail.presentation.status_note}</p>
          <div className="mt-5 flex flex-wrap gap-4 text-sm text-ink/54">
            <span>Last updated {formatDate(lastUpdated)}</span>
            <span>Elapsed {formatElapsed(detail.request.started_at, detail.request.completed_at)}</span>
            {detail.progress.current_label ? <span>Current stage: {detail.progress.current_label}</span> : null}
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          <Panel className="p-5">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Recommendation</p>
            <p className="mt-3 text-lg font-semibold capitalize text-ink">
              {humanizeLabel(detail.recommendation?.recommendation_label ?? "pending")}
            </p>
          </Panel>
          <Panel className="p-5">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Confidence</p>
            <p className="mt-3 text-lg font-semibold capitalize text-ink">
              {humanizeLabel(detail.latest_run?.confidence_label ?? "pending")}
            </p>
          </Panel>
          <Panel className="p-5">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">
              {hasPointEstimate ? "YES probability" : hasProbabilityRange ? "Probability view" : "Qualitative view"}
            </p>
            <p className="mt-3 text-lg font-semibold text-ink">
              {hasPointEstimate
                ? formatPercent(detail.latest_run?.p_hat)
                : hasProbabilityRange
                  ? `${formatPercent(detail.latest_run?.p_low)} - ${formatPercent(detail.latest_run?.p_high)}`
                  : humanizeLabel(qualitativeLabel)}
            </p>
          </Panel>
          <Panel className="p-5">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">
              {hasPointEstimate ? "NO probability" : "Model note"}
            </p>
            {hasPointEstimate ? (
              <p className="mt-3 text-lg font-semibold text-ink">{formatPercent(noPointEstimate)}</p>
            ) : (
              <p className="mt-3 text-sm leading-7 text-ink/62">
                {detail.latest_run?.numeric_estimate_reason ?? "This run stayed qualitative-only."}
              </p>
            )}
          </Panel>
        </section>

        <Panel className="space-y-6 p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Working memo</p>
            <h2 className="mt-2 font-serif text-3xl text-ink">What this means</h2>
          </div>
          {artifactStatusMap.get("brief_generation")?.available || !isRunning ? (
            <p className="max-w-4xl text-base leading-8 text-ink/70">
              {detail.presentation.brief_sections.what_it_means}
            </p>
          ) : (
            <SectionPlaceholder
              title="Brief being written"
              note={artifactStatusMap.get("brief_generation")?.note ?? "The final memo language will replace this placeholder once the brief stage finishes."}
            />
          )}

          <div className="grid gap-8 lg:grid-cols-2">
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
                  title="Factors being scored"
                  note={
                    isRunning
                      ? artifactStatusMap.get("factor_mapping")?.note ?? "Directional YES evidence will appear here after factor mapping finishes."
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
                  title="Factors being scored"
                  note={
                    isRunning
                      ? artifactStatusMap.get("factor_mapping")?.note ?? "Directional NO evidence will appear here after factor mapping finishes."
                      : "This run did not surface scored NO-side evidence."
                  }
                />
              )}
            </div>
          </div>

          <div className="memo-rule space-y-4 pt-6">
            <h3 className="font-serif text-2xl text-ink">Context / not scored</h3>
            {contextItems.length ? (
              <div className="space-y-4">
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
                title="Context still assembling"
                note={
                  isRunning
                    ? artifactStatusMap.get("factor_mapping")?.note ?? "Contextual and non-scored evidence will appear here once factor mapping finishes."
                    : "No contextual-only evidence was stored for this run."
                }
              />
            )}
          </div>

          <div className="memo-rule space-y-4 pt-6">
            <h3 className="font-serif text-2xl text-ink">Why this could be wrong</h3>
            <p className="max-w-4xl text-sm leading-8 text-ink/66">
              {detail.presentation.brief_sections.caveats}
            </p>
          </div>
        </Panel>

        <Panel className="space-y-6 p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Social intelligence</p>
            <h2 className="mt-2 font-serif text-3xl text-ink">Trusted accounts and narrative context</h2>
          </div>
          {detail.social_intel_summary ? (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <Badge variant={badgeVariant(detail.social_intel_summary.consensus_label)}>
                  {detail.social_intel_summary.consensus_label}
                </Badge>
                <Badge variant={badgeVariant(detail.social_intel_summary.consensus_strength)}>
                  {detail.social_intel_summary.consensus_strength}
                </Badge>
                <Badge variant={badgeVariant(detail.social_intel_summary.narrative_phase)}>
                  {detail.social_intel_summary.narrative_phase}
                </Badge>
              </div>
              <SocialConsensusSnapshot summary={detail.social_intel_summary} />
              {trustedSocialSources.length ? (
                <div className="space-y-4">
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

        <Panel className="space-y-6 p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Sources</p>
            <h2 className="mt-2 font-serif text-3xl text-ink">Source material and grounded passages</h2>
          </div>

          {nonSocialSources.length ? (
            <div className="space-y-6">
              {nonSocialSources.map((source) => {
                const grounding = documentsBySource.get(source.id);
                const passages = passagesBySource.get(source.id) ?? [];
                return (
                  <article key={source.id} className="border-b border-black/8 pb-6 last:border-b-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="muted">{source.source_kind}</Badge>
                      <Badge variant="muted">{source.source_tier}</Badge>
                      {grounding?.extractor ? <Badge variant="muted">{grounding.extractor}</Badge> : null}
                    </div>
                    <p className="mt-3 text-lg font-semibold text-ink">{source.title ?? source.domain ?? "Untitled source"}</p>
                    <p className="mt-2 text-sm leading-7 text-ink/66">{source.excerpt}</p>

                    {passages.length ? (
                      <div className="mt-4 space-y-3">
                        <div className="flex items-center justify-between gap-4">
                          <p className="text-[10px] uppercase tracking-[0.16em] text-ink/46">
                            Ranked grounding passages
                          </p>
                          <button
                            type="button"
                            onClick={() => openAudit({ section: "grounding", passageId: passages[0].id })}
                            className="rounded-full border border-black/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-ink/62 transition hover:bg-black/5"
                          >
                            Inspect grounding
                          </button>
                        </div>
                        {passages.slice(0, 2).map((passage) => (
                          <article key={passage.id} className="rounded-[14px] border border-black/8 bg-[rgba(255,255,255,0.56)] px-4 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="muted">passage {passage.passage_index}</Badge>
                              <span className="text-[10px] uppercase tracking-[0.16em] text-ink/42">
                                relevance {passage.relevance_score.toFixed(2)}
                              </span>
                            </div>
                            <p className="mt-3 text-sm leading-7 text-ink/64">{passage.text}</p>
                          </article>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-ink/54">
                      {grounding ? <span>{grounding.wordCount} words grounded</span> : null}
                      {source.url ? (
                        <Link href={source.url} target="_blank" className="font-medium text-ember">
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

      <aside className="space-y-6 xl:sticky xl:top-24 xl:self-start">
        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Actions</p>
            <p className="mt-2 text-sm leading-7 text-ink/58">
              Open the inspector, rerun the desk, or return to the research log.
            </p>
          </div>
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => openAudit({ section: "scoring" })}
              disabled={!detail.audit}
              className="w-full rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink/92 disabled:cursor-not-allowed disabled:bg-ink/45"
            >
              How this was calculated
            </button>
            <button
              type="button"
              onClick={handleRerun}
              disabled={isRerunning}
              className="w-full rounded-full border border-black/10 bg-white/70 px-5 py-3 text-sm font-semibold text-ink transition hover:bg-white disabled:cursor-not-allowed disabled:text-ink/45"
            >
              {isRerunning ? "Rerunning..." : "Rerun analysis"}
            </button>
            <Link
              href="/history"
              className="block rounded-full border border-black/10 bg-white/70 px-5 py-3 text-center text-sm font-semibold text-ink transition hover:bg-white"
            >
              Back to research log
            </Link>
          </div>
        </Panel>

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Run status</p>
            <p className="mt-2 text-2xl font-semibold text-ink">{detail.progress.percent_complete}%</p>
            <p className="mt-2 text-sm leading-7 text-ink/58">
              {isFailed
                ? detail.request.error_message ?? "The run stopped before completion."
                : detail.progress.current_note ?? "Waiting for the next stage."}
            </p>
          </div>
          <div className="h-1.5 rounded-full bg-black/6">
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

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Market context</p>
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

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Rule parse</p>
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
