"use client";

import { useEffect } from "react";

import { AnalysisAudit, Document, Passage, Source } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

type AuditFocus = {
  section?: "scoring" | "uncertainty" | "recommendation" | "grounding" | "factors";
  factorId?: number | null;
  passageId?: number | null;
};

type AnalysisAuditDrawerProps = {
  audit: AnalysisAudit | null;
  documents: Document[];
  open: boolean;
  onClose: () => void;
  passages: Passage[];
  sources: Source[];
  focus?: AuditFocus | null;
};

function humanize(value: string | null | undefined) {
  if (!value) {
    return "Unavailable";
  }
  return value.replaceAll("_", " ");
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  return `${Math.round(value * 100)}%`;
}

function complementProbability(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return null;
  }
  return Math.min(Math.max(1 - value, 0), 1);
}

function formatSigned(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

function scrollToAuditTarget(focus: AuditFocus | null | undefined) {
  if (!focus) {
    return;
  }

  const targetId = focus.factorId
    ? `audit-factor-${focus.factorId}`
    : focus.passageId
      ? `audit-passage-${focus.passageId}`
      : focus.section
        ? `audit-section-${focus.section}`
        : null;
  if (!targetId) {
    return;
  }

  window.requestAnimationFrame(() => {
    document.getElementById(targetId)?.scrollIntoView({ block: "start", behavior: "smooth" });
  });
}

export function AnalysisAuditDrawer({
  audit,
  documents,
  open,
  onClose,
  passages,
  sources,
  focus,
}: AnalysisAuditDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [onClose, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    scrollToAuditTarget(focus);
  }, [focus, open]);

  if (!open) {
    return null;
  }

  const passageSourceLookup = new Map(sources.map((source) => [source.id, source]));
  const documentsBySource = new Map<number, Document[]>();
  for (const document of documents) {
    const current = documentsBySource.get(document.source_id) ?? [];
    current.push(document);
    documentsBySource.set(document.source_id, current);
  }
  const passagesBySource = new Map<number, Passage[]>();
  for (const passage of passages) {
    const current = passagesBySource.get(passage.source_id) ?? [];
    current.push(passage);
    passagesBySource.set(passage.source_id, current);
  }

  const navItems: Array<{ key: AuditFocus["section"]; label: string }> = [
    { key: "scoring", label: "Scoring" },
    { key: "uncertainty", label: "Uncertainty" },
    { key: "recommendation", label: "Recommendation" },
    { key: "grounding", label: "Source grounding" },
    { key: "factors", label: "Factor details" },
  ];

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close calculation audit"
        onClick={onClose}
        className="absolute inset-0 bg-black/28 backdrop-blur-[1px]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="How this was calculated"
        className="absolute inset-x-0 bottom-0 top-12 overflow-y-auto border border-black/8 bg-[rgba(249,245,238,0.98)] px-5 pb-10 pt-5 shadow-[0_-12px_40px_rgba(22,17,12,0.12)] md:inset-y-0 md:left-auto md:right-0 md:top-0 md:w-[min(48rem,100vw)] md:border-l"
      >
        <div className="mx-auto max-w-4xl space-y-8">
          <div className="border-b border-black/8 pb-5">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-[0.22em] text-ember/78">
                  Layered audit
                </p>
                <h2 className="font-serif text-3xl text-ink">How this was calculated</h2>
                <p className="max-w-2xl text-sm leading-7 text-ink/66">
                  This inspector shows structured scoring, uncertainty, recommendation, and source
                  grounding details. It does not expose hidden model chain-of-thought.
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-black/10 px-4 py-2 text-sm font-medium text-ink transition hover:bg-black/5"
              >
                Close
              </button>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {navItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => scrollToAuditTarget({ section: item.key })}
                  className="rounded-full border border-black/10 bg-white/60 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-ink/62 transition hover:bg-white"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {audit ? (
            <>
              <section id="audit-section-scoring" className="space-y-4">
                <div className="border-b border-black/8 pb-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Scoring</p>
                  <h3 className="mt-2 font-serif text-2xl text-ink">Rule interpretation and probability inputs</h3>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <article className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Template</p>
                    <p className="mt-2 text-lg font-semibold text-ink">{humanize(audit.rule_interpretation.template)}</p>
                    <p className="mt-3 text-sm leading-7 text-ink/62">
                      {audit.rule_interpretation.resolution_definition ?? "No rule definition stored."}
                    </p>
                  </article>
                  <article className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">YES / NO conditions</p>
                    <p className="mt-2 text-sm leading-7 text-ink/66">
                      <span className="font-semibold text-ink">YES:</span> {audit.rule_interpretation.yes_condition}
                    </p>
                    <p className="mt-2 text-sm leading-7 text-ink/66">
                      <span className="font-semibold text-ink">NO:</span> {audit.rule_interpretation.no_condition}
                    </p>
                  </article>
                  <article className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Evidence mix</p>
                    <div className="mt-3 space-y-2 text-sm text-ink/64">
                      <p>Prior: {formatPercent(audit.probability?.prior_probability)}</p>
                      <p>Non-social evidence: {audit.probability ? formatSigned(audit.probability.non_social_evidence) : "Unavailable"}</p>
                      <p>Capped social evidence: {audit.probability ? formatSigned(audit.probability.capped_social_evidence) : "Unavailable"}</p>
                      <p>{audit.probability?.numeric_estimate_available ? "Approved p_hat" : "Model p_hat"}: {formatPercent(audit.probability?.p_hat)}</p>
                      <p>Model NO complement: {formatPercent(complementProbability(audit.probability?.p_hat))}</p>
                    </div>
                  </article>
                  <article className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                    <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Source lanes</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-ink/64">
                      <p>Official: {audit.source_lanes.official}</p>
                      <p>News: {audit.source_lanes.news}</p>
                      <p>Premium: {audit.source_lanes.premium}</p>
                      <p>Live social: {audit.source_lanes.live_social}</p>
                      <p>Manual social: {audit.source_lanes.manual_social}</p>
                      <p>Contributing: {audit.source_lanes.contributing_sources}</p>
                    </div>
                  </article>
                </div>
              </section>

              <section id="audit-section-uncertainty" className="space-y-4">
                <div className="border-b border-black/8 pb-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Uncertainty</p>
                  <h3 className="mt-2 font-serif text-2xl text-ink">Why the range widened or stayed tight</h3>
                </div>
                <div className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                  <div className="grid gap-4 md:grid-cols-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Base</p>
                      <p className="mt-2 text-lg font-semibold text-ink">
                        {audit.uncertainty?.base_uncertainty?.toFixed(4) ?? "Unavailable"}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Total</p>
                      <p className="mt-2 text-lg font-semibold text-ink">
                        {audit.uncertainty?.total_uncertainty?.toFixed(4) ?? "Unavailable"}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Range</p>
                      <p className="mt-2 text-lg font-semibold text-ink">
                        {formatPercent(audit.uncertainty?.p_low)} - {formatPercent(audit.uncertainty?.p_high)}
                      </p>
                    </div>
                  </div>
                  <div className="mt-5 space-y-3">
                    {(audit.uncertainty?.adjustments ?? []).length ? (
                      (audit.uncertainty?.adjustments ?? []).map((adjustment) => (
                        <article key={adjustment.key} className="border-b border-black/6 pb-3 last:border-b-0 last:pb-0">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-ink">{adjustment.label}</p>
                            <p className="text-sm font-semibold text-ink">{formatSigned(adjustment.amount)}</p>
                          </div>
                          <p className="mt-2 text-sm leading-7 text-ink/62">{adjustment.note}</p>
                        </article>
                      ))
                    ) : (
                      <p className="text-sm leading-7 text-ink/58">No explicit uncertainty adjustments were stored.</p>
                    )}
                  </div>
                </div>
              </section>

              <section id="audit-section-recommendation" className="space-y-4">
                <div className="border-b border-black/8 pb-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Recommendation</p>
                  <h3 className="mt-2 font-serif text-2xl text-ink">Executable prices and final label</h3>
                </div>
                <div className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Chosen label</p>
                      <p className="mt-2 text-lg font-semibold text-ink">{humanize(audit.recommendation_math?.chosen_label)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Confidence</p>
                      <p className="mt-2 text-lg font-semibold text-ink">{humanize(audit.confidence?.final_label)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">YES / NO executable prices</p>
                      <p className="mt-2 text-sm leading-7 text-ink/62">
                        YES {audit.recommendation_math?.yes_exec_price ?? "n/a"} · NO {audit.recommendation_math?.no_exec_price ?? "n/a"}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.16em] text-ink/42">Friction buffer</p>
                      <p className="mt-2 text-sm leading-7 text-ink/62">
                        {audit.recommendation_math?.friction_buffer ?? "Unavailable"}
                      </p>
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-7 text-ink/62">
                    {audit.recommendation_math?.note ?? audit.confidence?.reason ?? "No recommendation note stored."}
                  </p>
                </div>
              </section>

              <section id="audit-section-grounding" className="space-y-4">
                <div className="border-b border-black/8 pb-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Source grounding</p>
                  <h3 className="mt-2 font-serif text-2xl text-ink">Ranked passages behind the memo</h3>
                </div>
                <div className="space-y-4">
                  {sources
                    .filter((source) => !["live_social", "manual_social"].includes(source.source_kind))
                    .map((source) => {
                      const groundedDocuments = documentsBySource.get(source.id) ?? [];
                      const groundedPassages = (passagesBySource.get(source.id) ?? []).sort(
                        (left, right) =>
                          right.relevance_score - left.relevance_score || left.passage_index - right.passage_index,
                      );
                      return (
                        <article key={source.id} className="rounded-[16px] border border-black/8 bg-white/70 p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-ink">{source.title ?? source.domain ?? "Source"}</p>
                            <Badge variant="muted">{source.source_tier}</Badge>
                            {groundedDocuments[0]?.extractor ? <Badge variant="muted">{groundedDocuments[0].extractor}</Badge> : null}
                          </div>
                          {groundedPassages.length ? (
                            <div className="mt-4 space-y-3">
                              {groundedPassages.slice(0, 3).map((passage) => (
                                <article
                                  key={passage.id}
                                  id={`audit-passage-${passage.id}`}
                                  className={`rounded-[14px] border px-4 py-3 ${
                                    focus?.passageId === passage.id
                                      ? "border-pine/30 bg-pine/8"
                                      : "border-black/6 bg-[rgba(247,242,233,0.9)]"
                                  }`}
                                >
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant="muted">passage {passage.passage_index}</Badge>
                                    <span className="text-[10px] uppercase tracking-[0.16em] text-ink/42">
                                      relevance {passage.relevance_score.toFixed(2)}
                                    </span>
                                  </div>
                                  <p className="mt-3 text-sm leading-7 text-ink/66">{passage.text}</p>
                                </article>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-3 text-sm leading-7 text-ink/58">
                              No grounded passages were persisted for this source.
                            </p>
                          )}
                        </article>
                      );
                    })}
                </div>
              </section>

              <section id="audit-section-factors" className="space-y-4">
                <div className="border-b border-black/8 pb-3">
                  <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Factor details</p>
                  <h3 className="mt-2 font-serif text-2xl text-ink">Every contribution that touched the score</h3>
                </div>
                <div className="space-y-3">
                  {(audit.factor_contributions ?? []).map((factor) => (
                    <article
                      key={factor.factor_id}
                      id={`audit-factor-${factor.factor_id}`}
                      className={`rounded-[16px] border p-4 ${
                        focus?.factorId === factor.factor_id
                          ? "border-pine/30 bg-pine/8"
                          : "border-black/8 bg-white/70"
                      }`}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          variant={
                            factor.stance === "yes"
                              ? "yes"
                              : factor.stance === "no"
                                ? "no"
                                : "muted"
                          }
                        >
                          {humanize(factor.stance)}
                        </Badge>
                        <Badge variant="muted">{humanize(factor.source_tier)}</Badge>
                        <Badge variant="muted">{humanize(factor.evidence_role)}</Badge>
                        <Badge variant={factor.used_in_scoring ? "yes" : "muted"}>
                          {factor.used_in_scoring ? "scored" : "context"}
                        </Badge>
                      </div>
                      <p className="mt-3 text-sm font-semibold text-ink">
                        {factor.rationale ?? "No factor rationale stored."}
                      </p>
                      <div className="mt-3 grid gap-2 text-sm text-ink/62 md:grid-cols-2">
                        <p>Source: {factor.source_title ?? "Unavailable"}</p>
                        <p>Signed contribution: {formatSigned(factor.signed_contribution)}</p>
                        <p>Strength: {humanize(factor.strength)}</p>
                        <p>Directness: {humanize(factor.directness)}</p>
                        <p>Verifier: {humanize(factor.verifier_status)}</p>
                        <p>Weight: {factor.final_weight.toFixed(4)}</p>
                      </div>
                      {factor.exclusion_reason ? (
                        <p className="mt-3 text-sm leading-7 text-ink/58">
                          Exclusion reason: {factor.exclusion_reason}
                        </p>
                      ) : null}
                    </article>
                  ))}
                </div>
              </section>
            </>
          ) : (
            <p className="text-sm leading-7 text-ink/58">
              The inspector will unlock once the analysis has produced a run.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}
