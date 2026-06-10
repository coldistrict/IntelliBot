"use client";

import { useEffect, useState } from "react";

import { ProviderStatus, fetchProviderStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

const rows: Array<{
  key: keyof ProviderStatus;
  label: string;
  note: string;
  nextStep: string;
}> = [
  {
    key: "openai_configured",
    label: "OpenAI",
    note: "Primary structured output model for rules, facts, verification, and the memo brief.",
    nextStep: "Add OPENAI_API_KEY to the root .env file.",
  },
  {
    key: "grok_configured",
    label: "Grok",
    note: "Live X intelligence and secondary narrative review.",
    nextStep: "Add XAI_API_KEY to the root .env file.",
  },
  {
    key: "search_configured",
    label: "Search",
    note: "Web discovery and retrieval for official sources and news coverage.",
    nextStep: "Add TAVILY_API_KEY so the desk can discover sources.",
  },
  {
    key: "fred_configured",
    label: "FRED",
    note: "Optional macro data feed for stronger economic-policy analysis.",
    nextStep: "Optional: add FRED_API_KEY for richer macro data.",
  },
  {
    key: "premium_session_available",
    label: "Premium session",
    note: "Optional session state for on-demand premium article fetches.",
    nextStep: "Optional: save a Playwright session file when you want premium retrieval.",
  },
];

export function ProviderStatusPanel() {
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const payload = await fetchProviderStatus();
        setStatus(payload);
        setError(null);
      } catch (loadError) {
        setError(
          loadError instanceof Error ? loadError.message : "Unable to load provider status.",
        );
      }
    }

    void load();
  }, []);

  return (
    <Panel className="p-5">
      <div className="border-b border-black/10 pb-3">
        <p className="section-label">Provider readiness</p>
        <h3 className="mt-1.5 font-serif text-2xl text-ink">What the desk can use right now</h3>
      </div>
      {error ? <p className="mt-4 text-sm text-ember">{error}</p> : null}
      {status ? (
        <div className="mt-2">
          {rows.map((row) => (
            <div
              key={row.key}
              className="grid gap-3 border-b border-black/10 py-4 last:border-b-0 last:pb-0 md:grid-cols-[minmax(0,1fr)_11rem]"
            >
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-ink">{row.label}</p>
                  <Badge variant={status[row.key] ? "yes" : "warning"}>
                    {status[row.key] ? "ready" : "missing"}
                  </Badge>
                </div>
                <p className="mt-1 text-sm leading-6 text-ink/60">{row.note}</p>
              </div>
              <div className="text-sm leading-6 text-ink/55 md:text-right">
                {status[row.key] ? "No action needed." : row.nextStep}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-ink/55">Loading provider readiness…</p>
      )}
    </Panel>
  );
}
