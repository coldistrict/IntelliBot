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

function statusCopy(summary: AnalysisSummary) {
  return summary.current_stage_note ?? summary.display_summary ?? "Waiting for the next artifact.";
}

function CompactRunRow({ item }: { item: AnalysisSummary }) {
  return (
    <Link href={`/analyses/${item.id}`} className="surface-row block transition hover:bg-black/[0.015]">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={analysisBadge(item)}>{item.status}</Badge>
        {item.template_selected ? (
          <Badge variant="muted">{item.template_selected.replaceAll("_", " ")}</Badge>
        ) : null}
        {item.latest_confidence_label ? (
          <Badge variant="muted">{item.latest_confidence_label.replaceAll("_", " ")}</Badge>
        ) : null}
      </div>
      <h4 className="mt-2 line-clamp-2 text-base font-semibold leading-6 text-ink">{item.input_text}</h4>
      <p className="mt-1 line-clamp-2 text-sm leading-6 text-ink/60">{statusCopy(item)}</p>
    </Link>
  );
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
  const rows = providerRows(status);
  const readyCount = rows.filter(([, ready]) => ready).length;
  const coreReady = rows.length >= 3 && rows.slice(0, 3).every(([, ready]) => ready);

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-5">
          <div className="max-w-5xl space-y-4">
            <p className="eyebrow">Desk Launchpad</p>
            <h2 className="page-title">
              Read one market deeply, then inspect exactly how the memo got there.
            </h2>
            <p className="page-intro">
              Manual analyses stay the center of the product. Start a claim, follow the live run,
              then open the memo and layered inspector once the evidence is ready.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/markets"
              className="primary-action w-full sm:w-auto"
            >
              Browse markets
            </Link>
            <Link
              href="/manual"
              className="secondary-action w-full sm:w-auto"
            >
              Start a manual analysis
            </Link>
            <Link
              href="/history"
              className="secondary-action w-full sm:w-auto"
            >
              Open research log
            </Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Panel className="p-4">
              <p className="section-label">Active</p>
              <p className="stat-number mt-2">{running.length}</p>
              <p className="mt-1 text-sm text-ink/60">Queued or running</p>
            </Panel>
            <Panel className="p-4">
              <p className="section-label">Recent</p>
              <p className="stat-number mt-2">{recent.length}</p>
              <p className="mt-1 text-sm text-ink/60">Finished memos shown</p>
            </Panel>
            <Panel className="p-4">
              <p className="section-label">Core path</p>
              <p className="stat-number mt-2">
                {status ? (coreReady ? "Ready" : "Setup") : "Check"}
              </p>
              <p className="mt-1 text-sm text-ink/60">
                {status ? `${readyCount}/${rows.length} providers available` : "Checking providers"}
              </p>
            </Panel>
          </div>
        </div>

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Readiness</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Providers</h3>
          </div>
          <div>
            {rows.length ? (
              rows.map(([label, ready]) => (
                <div key={label} className="surface-row flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-ink">{label}</p>
                    <p className="mt-0.5 text-sm text-ink/60">
                      {ready ? "Configured" : "Needs setup"}
                    </p>
                  </div>
                  <Badge variant={ready ? "yes" : "warning"}>{ready ? "ready" : "missing"}</Badge>
                </div>
              ))
            ) : (
              <p className="text-sm leading-7 text-ink/60">Loading provider readiness…</p>
            )}
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Panel className="space-y-4 p-5">
          <div className="flex items-center justify-between gap-4 border-b border-black/10 pb-3">
            <div>
              <p className="section-label">Active</p>
              <h3 className="mt-1.5 font-serif text-2xl text-ink">Runs in motion</h3>
            </div>
            <Link href="/history" className="text-sm font-semibold text-pine">
              View all
            </Link>
          </div>
          <div>
            {running.length ? (
              running.map((item) => <CompactRunRow key={item.id} item={item} />)
            ) : (
              <div className="py-5">
                <p className="text-sm leading-7 text-ink/60">
                  No active analyses right now. Start one from Manual Analysis.
                </p>
                <Link href="/manual" className="mt-3 secondary-action">
                  Start a run
                </Link>
              </div>
            )}
          </div>
        </Panel>

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Recent</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Latest completed memos</h3>
          </div>
          <div>
            {recent.length ? (
              recent.map((item) => <CompactRunRow key={item.id} item={item} />)
            ) : (
              <div className="py-5">
                <p className="text-sm leading-7 text-ink/60">
                  Completed analyses will show up here once you start using the desk.
                </p>
              </div>
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}
