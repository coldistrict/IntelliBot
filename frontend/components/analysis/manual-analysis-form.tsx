"use client";

import { startTransition, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { createManualAnalysis, ManualAnalysisPayload } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

type TemplateSelection =
  | "auto"
  | NonNullable<ManualAnalysisPayload["template_requested"]>;

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
    <div className="space-y-8">
      <section className="max-w-5xl space-y-4">
        <p className="text-[10px] uppercase tracking-[0.28em] text-ember/76">Manual Analysis</p>
        <h2 className="max-w-4xl font-serif text-5xl leading-[0.98] text-ink md:text-6xl">
          Compose the research run, then let the memo build itself.
        </h2>
        <p className="max-w-3xl text-base leading-8 text-ink/68">
          Start with one clear claim, URL, or market ID. The desk will parse the proposition,
          gather sources, verify evidence, and open a live memo page while the run is still
          working.
        </p>
      </section>

      <Panel className="overflow-hidden p-0">
        <form className="space-y-8 p-6 md:p-8" onSubmit={handleSubmit}>
          <section className="space-y-4 border-b border-black/8 pb-6">
            <div className="flex flex-wrap gap-2">
              <Badge variant="yes">Memo-first workflow</Badge>
              <Badge variant="muted">Live X intelligence available</Badge>
              <Badge variant="muted">Compact manual setup</Badge>
            </div>

            <div className="flex flex-wrap gap-2">
              {[
                ["custom_claim", "Custom claim"],
                ["market_id", "Market ID"],
                ["market_url", "Polymarket URL"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setInputMode(value as typeof inputMode)}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    inputMode === value
                      ? "border-ink bg-ink text-white"
                      : "border-black/10 bg-white/60 text-ink hover:bg-white"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <label className="block">
              <span className="text-sm font-semibold text-ink">Primary input</span>
              <textarea
                value={primaryValue}
                onChange={(event) => setPrimaryValue(event.target.value)}
                required
                rows={inputMode === "custom_claim" ? 5 : 2}
                className="mt-3 w-full rounded-[18px] border border-black/10 bg-[rgba(255,255,255,0.72)] px-5 py-4 text-sm text-ink outline-none transition focus:border-black/20"
                placeholder={
                  inputMode === "custom_claim"
                    ? "Will the Fed cut rates by June?"
                    : inputMode === "market_id"
                      ? "fed-cut-june-2026"
                      : "https://polymarket.com/event/fed-cut-june-2026"
                }
              />
              <p className="mt-3 text-sm leading-7 text-ink/58">{helperText}</p>
            </label>
          </section>

          <section className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">
                Analysis settings
              </p>
              <span className="text-sm text-ink/54">Keep this compact unless the claim needs extra framing.</span>
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr_0.9fr_0.9fr]">
              <label className="block">
                <span className="text-sm font-semibold text-ink">Template</span>
                <select
                  value={templateRequested}
                  onChange={(event) => setTemplateRequested(event.target.value as TemplateSelection)}
                  className="mt-2 w-full rounded-[16px] border border-black/10 bg-white/70 px-4 py-3 text-sm text-ink outline-none"
                >
                  <option value="auto">Auto-detect</option>
                  <option value="official_event">official_event</option>
                  <option value="macro_policy">macro_policy</option>
                  <option value="legal_case">legal_case</option>
                  <option value="narrative_manual">narrative_manual</option>
                  <option value="generic_manual">generic_manual</option>
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-semibold text-ink">Optional deadline</span>
                <input
                  value={deadlineText}
                  onChange={(event) => setDeadlineText(event.target.value)}
                  className="mt-2 w-full rounded-[16px] border border-black/10 bg-white/70 px-4 py-3 text-sm text-ink outline-none"
                  placeholder="June 12, 2026"
                />
              </label>

              <label className="flex rounded-[16px] border border-black/10 bg-white/70 px-4 py-3">
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
                  <p className="mt-1 text-xs leading-6 text-ink/56">
                    Grok searches live X and web context for trusted accounts and narrative shifts.
                  </p>
                </div>
              </label>

              <label className="flex rounded-[16px] border border-black/10 bg-white/70 px-4 py-3">
                <input
                  type="checkbox"
                  checked={includePremium}
                  onChange={(event) => setIncludePremium(event.target.checked)}
                  className="mt-1 h-4 w-4 accent-ember"
                />
                <div className="ml-3">
                  <p className="text-sm font-semibold text-ink">Enable premium retrieval</p>
                  <p className="mt-1 text-xs leading-6 text-ink/56">
                    Allow paywalled premium-news search results into the source set when they are relevant.
                  </p>
                </div>
              </label>
            </div>
          </section>

          {error ? (
            <div className="rounded-[16px] border border-ember/18 bg-ember/8 px-5 py-4 text-sm leading-7 text-ember">
              {error}
            </div>
          ) : null}

          <section className="memo-rule space-y-4 pt-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <div>
                <p className="text-sm font-semibold text-ink">What happens next</p>
                <p className="mt-2 text-sm leading-7 text-ink/62">
                  You’ll land on a live memo page that keeps the structure visible while the run is
                  still working. Rules, sources, factors, and the audit inspector unlock as soon as
                  each artifact is ready.
                </p>
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">Tips for stronger inputs</p>
                <p className="mt-2 text-sm leading-7 text-ink/62">
                  Use a direct claim, add a deadline if it matters, and let Grok handle live X
                  discovery instead of hand-curating posts.
                </p>
              </div>
            </div>

            <div className="sticky bottom-4 flex flex-col gap-3 rounded-[18px] border border-black/10 bg-[rgba(251,248,241,0.95)] px-4 py-4 shadow-[0_12px_32px_rgba(22,17,12,0.08)] backdrop-blur-sm md:flex-row md:items-center md:justify-between">
              <p className="text-sm leading-7 text-ink/62">
                The composer is intentionally compact. Most of the product value should happen on
                the live analysis page, not here.
              </p>
              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-ink/92 disabled:cursor-not-allowed disabled:bg-ink/45"
              >
                {isSubmitting ? "Starting analysis..." : "Run manual analysis"}
              </button>
            </div>
          </section>
        </form>
      </Panel>
    </div>
  );
}
