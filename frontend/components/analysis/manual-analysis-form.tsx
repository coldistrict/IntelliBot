"use client";

import { startTransition, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { createManualAnalysis, ManualAnalysisPayload } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

type TemplateSelection =
  | "auto"
  | NonNullable<ManualAnalysisPayload["template_requested"]>;

const inputModeOptions: Array<{ value: "custom_claim" | "market_id" | "market_url"; label: string }> = [
  { value: "custom_claim", label: "Custom claim" },
  { value: "market_id", label: "Market ID" },
  { value: "market_url", label: "Polymarket URL" },
];

const templateOptions: Array<{ value: TemplateSelection; label: string }> = [
  { value: "auto", label: "Auto-detect" },
  { value: "official_event", label: "Official event" },
  { value: "macro_policy", label: "Macro policy" },
  { value: "legal_case", label: "Legal case" },
  { value: "narrative_manual", label: "Narrative manual" },
  { value: "generic_manual", label: "Generic manual" },
];

const customClaimExamples = [
  "Will Trump be impeached after the 2026 midterms?",
  "Will Democrats win both chambers of Congress in the 2026 midterms?",
  "Will Democrats win control of the Senate in the 2026 midterms?",
];

function defaultLiveXValue(templateRequested: TemplateSelection) {
  return templateRequested !== "official_event";
}

export function ManualAnalysisForm() {
  const router = useRouter();
  const [inputMode, setInputMode] = useState<"custom_claim" | "market_id" | "market_url">(
    "custom_claim",
  );
  const [primaryValue, setPrimaryValue] = useState("");
  const [templateRequested, setTemplateRequested] = useState<TemplateSelection>("auto");
  const [deadlineText, setDeadlineText] = useState("");
  const [includePremium, setIncludePremium] = useState(false);
  const [includeLiveXIntelligence, setIncludeLiveXIntelligence] = useState(
    defaultLiveXValue("auto"),
  );
  const [liveXTouched, setLiveXTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!liveXTouched) {
      setIncludeLiveXIntelligence(defaultLiveXValue(templateRequested));
    }
  }, [liveXTouched, templateRequested]);

  const helperText = useMemo(() => {
    if (inputMode === "market_id") {
      return "Use a Polymarket market ID when you already know the exact market you want analyzed.";
    }
    if (inputMode === "market_url") {
      return "Paste a full Polymarket URL to hydrate market rules and pricing context automatically.";
    }
    return "Ask a direct claim, such as “Will the Fed cut rates by June?” or “Will SCOTUS strike this down?”";
  }, [inputMode]);
  const canSubmit = primaryValue.trim().length > 0 && !isSubmitting;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const payload: ManualAnalysisPayload = {
      include_premium: includePremium,
      include_live_x_intelligence: includeLiveXIntelligence,
    };

    if (deadlineText.trim()) {
      payload.deadline_text = deadlineText.trim();
    }
    if (templateRequested !== "auto") {
      payload.template_requested = templateRequested;
    }
    if (inputMode === "custom_claim") {
      payload.custom_claim = primaryValue.trim();
    } else if (inputMode === "market_id") {
      payload.polymarket_market_id = primaryValue.trim();
    } else {
      payload.polymarket_url = primaryValue.trim();
    }

    try {
      const result = await createManualAnalysis(payload);
      startTransition(() => {
        router.push(`/analyses/${result.request.id}`);
      });
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Something went wrong while submitting the analysis.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="max-w-5xl space-y-4">
        <p className="eyebrow">Manual Analysis</p>
        <h1 className="page-title">
          Compose the research run, then let the memo build itself.
        </h1>
        <p className="page-intro">
          Start with one clear claim, URL, or market ID. The desk will parse the proposition,
          gather sources, verify evidence, and open a live memo page while the run is still
          working.
        </p>
      </section>

      <Panel className="overflow-hidden p-0">
        <form className="space-y-0" onSubmit={handleSubmit}>
          <section className="space-y-5 border-b border-black/10 p-5 md:p-6">
            <div className="flex flex-wrap gap-2">
              <Badge variant="yes">Memo-first workflow</Badge>
              <Badge variant="muted">Live X intelligence available</Badge>
              <Badge variant="muted">Compact manual setup</Badge>
            </div>

            <fieldset>
              <legend className="text-sm font-semibold text-ink">Input type</legend>
              <div className="mt-2 grid gap-2 rounded-lg border border-black/10 bg-white/50 p-1 sm:grid-cols-3">
                {inputModeOptions.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={inputMode === value}
                    onClick={() => setInputMode(value as typeof inputMode)}
                    className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
                      inputMode === value
                        ? "bg-ink text-white shadow-sm"
                        : "text-ink/60 hover:bg-white/80 hover:text-ink"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </fieldset>

            <label className="block">
              <span className="text-sm font-semibold text-ink">Primary input</span>
              <textarea
                value={primaryValue}
                onChange={(event) => setPrimaryValue(event.target.value)}
                required
                rows={inputMode === "custom_claim" ? 5 : 2}
                className="field-control mt-2 min-h-28 resize-y"
                placeholder={
                  inputMode === "custom_claim"
                    ? "Will the Fed cut rates by June?"
                    : inputMode === "market_id"
                      ? "fed-cut-june-2026"
                      : "https://polymarket.com/event/fed-cut-june-2026"
                }
              />
              <div className="mt-2 flex flex-col gap-1 text-sm leading-6 text-ink/60 sm:flex-row sm:items-center sm:justify-between">
                <p>{helperText}</p>
                <p className="text-xs uppercase tracking-[0.14em] text-ink/40">{primaryValue.trim().length} chars</p>
              </div>
              {inputMode === "custom_claim" ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {customClaimExamples.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => {
                        setPrimaryValue(example);
                        setTemplateRequested("auto");
                      }}
                      className="quiet-action max-w-full justify-start whitespace-normal break-words text-left leading-5 normal-case tracking-normal"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              ) : null}
            </label>
          </section>

          <div className="mx-5 my-5 flex flex-col gap-3 rounded-lg border border-black/10 bg-white/95 px-4 py-4 shadow-panel backdrop-blur-sm md:mx-6 md:flex-row md:items-center md:justify-between">
            <p className="text-sm leading-7 text-ink/60">
              The composer is intentionally compact. Most of the product value should happen on
              the live analysis page, not here.
            </p>
            <button
              type="submit"
              disabled={!canSubmit}
              className="primary-action md:min-w-44"
            >
              {isSubmitting ? "Starting analysis..." : "Run manual analysis"}
            </button>
          </div>

          {error ? (
            <div
              role="alert"
              className="mx-5 -mt-2 mb-5 rounded-lg border border-ember/20 bg-ember/10 px-5 py-4 text-sm leading-7 text-ember md:mx-6"
            >
              {error}
            </div>
          ) : null}

          <section className="space-y-4 p-5 md:p-6">
            <div className="flex flex-wrap items-center gap-3">
              <p className="section-label">
                Analysis settings
              </p>
              <span className="text-sm text-ink/60">Keep this compact unless the claim needs extra framing.</span>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
              <label className="block">
                <span className="text-sm font-semibold text-ink">Template</span>
                <select
                  value={templateRequested}
                  onChange={(event) => setTemplateRequested(event.target.value as TemplateSelection)}
                  className="field-control mt-2"
                >
                  {templateOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-semibold text-ink">Optional deadline</span>
                <input
                  value={deadlineText}
                  onChange={(event) => setDeadlineText(event.target.value)}
                  className="field-control mt-2"
                  placeholder="June 12, 2026"
                />
              </label>

              <label className="flex rounded-lg border border-black/10 bg-white/75 px-4 py-3">
                <input
                  type="checkbox"
                  aria-label="Include live X intelligence"
                  checked={includeLiveXIntelligence}
                  onChange={(event) => {
                    setLiveXTouched(true);
                    setIncludeLiveXIntelligence(event.target.checked);
                  }}
                  className="mt-1 h-4 w-4 accent-pine"
                />
                <div className="ml-3">
                  <p className="text-sm font-semibold text-ink">Include live X intelligence</p>
                  <p className="mt-1 text-xs leading-6 text-ink/60">
                    Grok searches live X and web context for trusted accounts and narrative shifts.
                  </p>
                </div>
              </label>

              <label className="flex rounded-lg border border-black/10 bg-white/75 px-4 py-3">
                <input
                  type="checkbox"
                  checked={includePremium}
                  onChange={(event) => setIncludePremium(event.target.checked)}
                  className="mt-1 h-4 w-4 accent-ember"
                />
                <div className="ml-3">
                  <p className="text-sm font-semibold text-ink">Enable premium retrieval</p>
                  <p className="mt-1 text-xs leading-6 text-ink/60">
                    Allow paywalled premium-news search results into the source set when they are relevant.
                  </p>
                </div>
              </label>
            </div>
          </section>

          <section className="memo-rule p-5 md:p-6">
            <details className="group">
              <summary className="cursor-pointer list-none text-sm font-semibold text-ink/70 transition hover:text-ink">
                <span aria-hidden="true" className="mr-2 inline-block transition group-open:rotate-90">
                  ›
                </span>
                What happens next & tips for stronger inputs
              </summary>
              <div className="mt-4 grid gap-5 lg:grid-cols-2">
                <div>
                  <p className="text-sm font-semibold text-ink">What happens next</p>
                  <p className="mt-2 text-sm leading-7 text-ink/60">
                    You’ll land on a live memo page that keeps the structure visible while the run
                    is still working. Rules, sources, factors, and the audit inspector unlock as
                    soon as each artifact is ready.
                  </p>
                </div>
                <div>
                  <p className="text-sm font-semibold text-ink">Tips for stronger inputs</p>
                  <p className="mt-2 text-sm leading-7 text-ink/60">
                    Use a direct claim, add a deadline if it matters, and let Grok handle live X
                    discovery instead of hand-curating posts.
                  </p>
                </div>
              </div>
            </details>
          </section>
        </form>
      </Panel>
    </div>
  );
}
