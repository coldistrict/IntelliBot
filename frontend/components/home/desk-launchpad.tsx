"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AnalysisSummary, ProviderStatus, fetchAnalyses, fetchProviderStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

function providerRows(status: ProviderStatus | null) {
  if (!status) {
    return [];
  }
  return [
    ["OpenAI", status.openai_configured],
    ["Grok", status.grok_configured],
    ["Search", status.search_configured],
    ["FRED", status.fred_configured],
    ["Premium", status.premium_session_available],
  ] as const;
}

function analysisBadge(summary: AnalysisSummary) {
  if (summary.status === "failed") {
    return "no" as const;
  }
  if (summary.status === "complete") {
    return "yes" as const;
  }
  return "warning" as const;
}

export function DeskLaunchpad() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [status, setStatus] = useState<ProviderStatus | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [analyses, providerStatus] = await Promise.all([
          fetchAnalyses(),
          fetchProviderStatus(),
        ]);
        setItems(analyses.items);
        setStatus(providerStatus);
      } catch {
        // Keep the launchpad resilient and quiet.
      }
    }

    void load();
  }, []);

  const running = useMemo(
    () => items.filter((item) => item.status === "queued" || item.status === "running").slice(0, 3),
    [items],
  );
  const recent = useMemo(
    () => items.filter((item) => item.status === "complete" || item.status === "failed").slice(0, 4),
    [items],
  );

  return (
    <div className="space-y-10">
      <section className="grid gap-10 xl:grid-cols-[minmax(0,1.1fr)_24rem]">
        <div className="max-w-5xl space-y-5">
          <p className="text-[10px] uppercase tracking-[0.28em] text-ember/76">
            Desk Launchpad
          </p>
          <h2 className="max-w-4xl font-serif text-5xl leading-[0.98] text-ink md:text-6xl">
            Read one market deeply, then inspect exactly how the memo got there.
          </h2>
          <p className="max-w-3xl text-base leading-8 text-ink/68">
            Manual analyses stay the center of the product. Start a claim, follow the live run,
            then open the memo and layered inspector once the evidence is ready.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/manual"
              className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ink/92"
            >
              Start a manual analysis
            </Link>
            <Link
              href="/history"
              className="rounded-full border border-black/10 bg-white/60 px-5 py-3 text-sm font-semibold text-ink transition hover:bg-white"
            >
              Open research log
            </Link>
          </div>
        </div>

        <Panel className="space-y-4 p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Readiness</p>
            <h3 className="mt-2 font-serif text-2xl text-ink">Providers at a glance</h3>
          </div>
          <div className="space-y-3">
            {providerRows(status).length ? (
              providerRows(status).map(([label, ready]) => (
                <div key={label} className="flex items-center justify-between gap-4 border-b border-black/6 pb-3 last:border-b-0 last:pb-0">
                  <div>
                    <p className="text-sm font-semibold text-ink">{label}</p>
                    <p className="text-sm text-ink/58">
                      {ready ? "Configured and available." : "Missing or not configured yet."}
                    </p>
                  </div>
                  <Badge variant={ready ? "yes" : "warning"}>{ready ? "ready" : "missing"}</Badge>
                </div>
              ))
            ) : (
              <p className="text-sm leading-7 text-ink/58">Loading provider readiness…</p>
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-8 xl:grid-cols-[1.05fr_0.95fr]">
        <Panel className="space-y-5 p-6">
          <div className="flex items-center justify-between gap-4 border-b border-black/8 pb-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Active</p>
              <h3 className="mt-2 font-serif text-2xl text-ink">Runs in motion</h3>
            </div>
            <Link href="/history" className="text-sm font-semibold text-ember">
              View all
            </Link>
          </div>
          <div className="space-y-4">
            {running.length ? (
              running.map((item) => (
                <Link
                  key={item.id}
                  href={`/analyses/${item.id}`}
                  className="block border-b border-black/6 pb-4 last:border-b-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={analysisBadge(item)}>{item.status}</Badge>
                    {item.template_selected ? <Badge variant="muted">{item.template_selected}</Badge> : null}
                  </div>
                  <h4 className="mt-3 text-lg font-semibold text-ink">{item.input_text}</h4>
                  <p className="mt-2 text-sm leading-7 text-ink/62">
                    {item.current_stage_note ?? item.display_summary ?? "Waiting for the next artifact."}
                  </p>
                </Link>
              ))
            ) : (
              <p className="text-sm leading-7 text-ink/58">
                No active analyses right now. Start one from Manual Analysis.
              </p>
            )}
          </div>
        </Panel>

        <Panel className="space-y-5 p-6">
          <div className="border-b border-black/8 pb-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Recent</p>
            <h3 className="mt-2 font-serif text-2xl text-ink">Latest completed memos</h3>
          </div>
          <div className="space-y-4">
            {recent.length ? (
              recent.map((item) => (
                <Link
                  key={item.id}
                  href={`/analyses/${item.id}`}
                  className="block border-b border-black/6 pb-4 last:border-b-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={analysisBadge(item)}>{item.status}</Badge>
                    {item.latest_confidence_label ? (
                      <Badge variant="muted">{item.latest_confidence_label}</Badge>
                    ) : null}
                  </div>
                  <h4 className="mt-3 text-lg font-semibold text-ink">{item.input_text}</h4>
                  <p className="mt-2 text-sm leading-7 text-ink/62">
                    {item.display_summary ?? "Open the memo for the full read."}
                  </p>
                </Link>
              ))
            ) : (
              <p className="text-sm leading-7 text-ink/58">
                Completed analyses will show up here once you start using the desk.
              </p>
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}
