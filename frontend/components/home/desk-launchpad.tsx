"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AnalysisSummary, ProviderStatus, fetchAnalyses, fetchProviderStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/ui/data-state";
import { Panel } from "@/components/ui/panel";

const REFRESH_INTERVAL_MS = 15000;

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

function runTitle(summary: AnalysisSummary) {
  return summary.market_title ?? summary.input_text;
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
        <span className="text-xs text-ink/40">
          {new Date(item.updated_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          })}
        </span>
      </div>
      <h4 className="mt-2 line-clamp-2 break-words text-base font-semibold leading-6 text-ink">
        {runTitle(item)}
      </h4>
      <p className="mt-1 line-clamp-2 break-words text-sm leading-6 text-ink/60">{statusCopy(item)}</p>
    </Link>
  );
}

export function DeskLaunchpad() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [analyses, providerStatus] = await Promise.all([
        fetchAnalyses(),
        fetchProviderStatus(),
      ]);
      setItems(analyses.items);
      setStatus(providerStatus);
      setError(null);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Unable to reach the backend.",
      );
    } finally {
      setHasLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void load();
      }
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  const allRunning = useMemo(
    () => items.filter((item) => item.status === "queued" || item.status === "running"),
    [items],
  );
  const allFinished = useMemo(
    () => items.filter((item) => item.status === "complete" || item.status === "failed"),
    [items],
  );
  const running = allRunning.slice(0, 3);
  const recent = allFinished.slice(0, 4);
  const rows = providerRows(status);
  const readyCount = rows.filter(([, ready]) => ready).length;
  const coreReady = rows.length >= 3 && rows.slice(0, 3).every(([, ready]) => ready);
  const isUnavailable = error !== null;

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-5">
          <div className="max-w-5xl space-y-4">
            <p className="eyebrow">Desk Launchpad</p>
            <h1 className="page-title">
              Read one market deeply, then inspect exactly how the memo got there.
            </h1>
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

          {isUnavailable ? (
            <DataState
              variant="error"
              title="The desk cannot reach the backend"
              note={`Runs, provider status, and counts below are unavailable. ${error}`}
              onRetry={() => void load()}
            />
          ) : null}

          <div className="grid gap-3 sm:grid-cols-3">
            <Panel className="p-4">
              <p className="section-label">Active</p>
              <p className="stat-number mt-2">{isUnavailable || !hasLoaded ? "—" : allRunning.length}</p>
              <p className="mt-1 text-sm text-ink/60">Queued or running</p>
            </Panel>
            <Panel className="p-4">
              <p className="section-label">Finished</p>
              <p className="stat-number mt-2">{isUnavailable || !hasLoaded ? "—" : allFinished.length}</p>
              <p className="mt-1 text-sm text-ink/60">Completed or failed runs</p>
            </Panel>
            <Panel className="p-4">
              <p className="section-label">Core path</p>
              <p className="stat-number mt-2">
                {isUnavailable ? "—" : status ? (coreReady ? "Ready" : "Setup") : "Check"}
              </p>
              <p className="mt-1 text-sm text-ink/60">
                {isUnavailable
                  ? "Backend unreachable"
                  : status
                    ? `${readyCount}/${rows.length} providers available`
                    : "Checking providers"}
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
            {isUnavailable ? (
              <DataState
                variant="error"
                title="Provider status unavailable"
                note="Reconnect the backend to see readiness."
                onRetry={() => void load()}
              />
            ) : rows.length ? (
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
              <DataState variant="loading" note="Loading provider readiness…" />
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
            {isUnavailable ? (
              <DataState
                variant="error"
                note="Active runs cannot be loaded while the backend is unreachable."
                onRetry={() => void load()}
              />
            ) : !hasLoaded ? (
              <DataState variant="loading" note="Loading active analyses…" />
            ) : running.length ? (
              running.map((item) => <CompactRunRow key={item.id} item={item} />)
            ) : (
              <DataState
                variant="empty"
                note="No active analyses right now. Start one from Manual Analysis."
                action={
                  <Link href="/manual" className="secondary-action">
                    Start a run
                  </Link>
                }
              />
            )}
          </div>
        </Panel>

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Recent</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Latest completed memos</h3>
          </div>
          <div>
            {isUnavailable ? (
              <DataState
                variant="error"
                note="Recent memos cannot be loaded while the backend is unreachable."
                onRetry={() => void load()}
              />
            ) : !hasLoaded ? (
              <DataState variant="loading" note="Loading recent memos…" />
            ) : recent.length ? (
              recent.map((item) => <CompactRunRow key={item.id} item={item} />)
            ) : (
              <DataState
                variant="empty"
                note="Completed analyses will show up here once you start using the desk."
              />
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}
