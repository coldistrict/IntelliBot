"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AnalysisSummary, fetchAnalyses } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

function badgeVariant(status: string) {
  if (status === "complete") {
    return "yes" as const;
  }
  if (status === "failed") {
    return "no" as const;
  }
  return "warning" as const;
}

function AnalysisRow({ item }: { item: AnalysisSummary }) {
  const progressPercent = item.progress_percent ?? 0;

  return (
    <Link
      href={`/analyses/${item.id}`}
      className="grid gap-4 border-b border-black/8 py-4 transition last:border-b-0 hover:bg-black/[0.015] md:grid-cols-[minmax(0,1fr)_13rem]"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badgeVariant(item.status)}>{item.status}</Badge>
          {item.template_selected ? <Badge variant="muted">{item.template_selected}</Badge> : null}
          {item.latest_confidence_label ? <Badge variant="muted">{item.latest_confidence_label}</Badge> : null}
        </div>
        <h3 className="mt-2 text-base font-semibold leading-6 text-ink">{item.input_text}</h3>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-ink/62">
          {item.display_summary ??
            item.current_stage_note ??
            "Open the run to watch the memo and inspector unlock."}
        </p>
      </div>

      <div className="space-y-2 text-sm text-ink/56 md:text-right">
        <p className="font-medium text-ink/68">{new Date(item.updated_at).toLocaleString()}</p>
        <p className="capitalize">
          {item.mode} · {item.input_type}
        </p>
        {(item.status === "queued" || item.status === "running") && item.progress_percent !== null ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.16em] text-ink/46">
              <span>{item.current_stage_label ?? "Queued"}</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-black/6">
              <div
                className="h-1.5 rounded-full bg-pine transition-all"
                style={{ width: `${Math.max(8, progressPercent)}%` }}
              />
            </div>
          </div>
        ) : null}
      </div>
    </Link>
  );
}

export function HistoryList() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const payload = await fetchAnalyses();
        setItems(payload.items);
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load analyses.");
      } finally {
        setHasLoaded(true);
      }
    }

    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(interval);
  }, []);

  const running = useMemo(
    () => items.filter((item) => item.status === "queued" || item.status === "running"),
    [items],
  );
  const completed = useMemo(
    () => items.filter((item) => item.status !== "queued" && item.status !== "running"),
    [items],
  );
  const failedCount = useMemo(() => items.filter((item) => item.status === "failed").length, [items]);

  if (error) {
    return (
      <Panel className="p-7">
        <p className="eyebrow">History</p>
        <p className="mt-4 text-sm text-ember">{error}</p>
      </Panel>
    );
  }

  return (
    <div className="space-y-6">
      <section className="max-w-5xl space-y-4">
        <p className="eyebrow">Research Log</p>
        <h2 className="page-title">
          Track what is still moving and what already resolved into a memo.
        </h2>
        <p className="page-intro">
          Running analyses stay visible with progress context, while completed runs compress into a
          denser reading log you can reopen at any time.
        </p>
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <Panel className="p-4">
          <p className="section-label">Total</p>
          <p className="mt-2 text-3xl font-semibold text-ink">{items.length}</p>
          <p className="mt-1 text-sm text-ink/58">Runs in the log</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Running</p>
          <p className="mt-2 text-3xl font-semibold text-ink">{running.length}</p>
          <p className="mt-1 text-sm text-ink/58">Currently moving</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Needs review</p>
          <p className="mt-2 text-3xl font-semibold text-ink">{failedCount}</p>
          <p className="mt-1 text-sm text-ink/58">Failed runs</p>
        </Panel>
      </section>

      <Panel className="p-5">
        <div className="border-b border-black/8 pb-3">
          <p className="section-label">Running</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Analyses in motion</h3>
        </div>
        <div>
          {!hasLoaded ? (
            <p className="py-5 text-sm leading-7 text-ink/58">Loading active analyses...</p>
          ) : running.length ? (
            running.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : (
            <p className="py-5 text-sm leading-7 text-ink/58">
              No active analyses right now. Start one from Manual Analysis.
            </p>
          )}
        </div>
      </Panel>

      <Panel className="p-5">
        <div className="border-b border-black/8 pb-3">
          <p className="section-label">Completed</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Finished runs</h3>
        </div>
        <div>
          {!hasLoaded ? (
            <p className="py-5 text-sm leading-7 text-ink/58">Loading finished runs...</p>
          ) : completed.length ? (
            completed.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : (
            <p className="py-5 text-sm leading-7 text-ink/58">
              Completed analyses will appear here once the desk has some history.
            </p>
          )}
        </div>
      </Panel>
    </div>
  );
}
