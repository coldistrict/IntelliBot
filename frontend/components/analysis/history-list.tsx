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
      className="grid gap-4 border-b border-black/8 py-5 transition last:border-b-0 hover:bg-black/[0.015] md:grid-cols-[minmax(0,1fr)_13rem]"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badgeVariant(item.status)}>{item.status}</Badge>
          {item.template_selected ? <Badge variant="muted">{item.template_selected}</Badge> : null}
          {item.latest_confidence_label ? <Badge variant="muted">{item.latest_confidence_label}</Badge> : null}
        </div>
        <h3 className="mt-3 font-serif text-2xl leading-tight text-ink">{item.input_text}</h3>
        <p className="mt-2 max-w-4xl text-sm leading-7 text-ink/62">
          {item.display_summary ??
            item.current_stage_note ??
            "Open the run to watch the memo and inspector unlock."}
        </p>
      </div>

      <div className="space-y-3 text-sm text-ink/56">
        <p>{new Date(item.updated_at).toLocaleString()}</p>
        <p>
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

  useEffect(() => {
    async function load() {
      try {
        const payload = await fetchAnalyses();
        setItems(payload.items);
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load analyses.");
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

  if (error) {
    return (
      <Panel className="p-7">
        <p className="text-[10px] uppercase tracking-[0.22em] text-ember/76">History</p>
        <p className="mt-4 text-sm text-ember">{error}</p>
      </Panel>
    );
  }

  return (
    <div className="space-y-8">
      <section className="max-w-5xl space-y-4">
        <p className="text-[10px] uppercase tracking-[0.28em] text-ember/76">Research Log</p>
        <h2 className="max-w-4xl font-serif text-5xl leading-[0.98] text-ink md:text-6xl">
          Track what is still moving and what already resolved into a memo.
        </h2>
        <p className="max-w-3xl text-base leading-8 text-ink/68">
          Running analyses stay visible with progress context, while completed runs compress into a
          denser reading log you can reopen at any time.
        </p>
      </section>

      <Panel className="p-6">
        <div className="border-b border-black/8 pb-4">
          <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Running</p>
          <h3 className="mt-2 font-serif text-2xl text-ink">Analyses in motion</h3>
        </div>
        <div>
          {running.length ? (
            running.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : (
            <p className="py-6 text-sm leading-7 text-ink/58">
              No active analyses right now. Start one from Manual Analysis.
            </p>
          )}
        </div>
      </Panel>

      <Panel className="p-6">
        <div className="border-b border-black/8 pb-4">
          <p className="text-[10px] uppercase tracking-[0.22em] text-ink/46">Completed</p>
          <h3 className="mt-2 font-serif text-2xl text-ink">Finished runs</h3>
        </div>
        <div>
          {completed.length ? (
            completed.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : (
            <p className="py-6 text-sm leading-7 text-ink/58">
              Completed analyses will appear here once the desk has some history.
            </p>
          )}
        </div>
      </Panel>
    </div>
  );
}
