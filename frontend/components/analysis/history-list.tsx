"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { AnalysisSummary, fetchAnalyses } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | "active" | "complete" | "failed";

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "complete", label: "Complete" },
  { value: "failed", label: "Failed" },
];

function badgeVariant(status: string) {
  if (status === "complete") {
    return "yes" as const;
  }
  if (status === "failed") {
    return "no" as const;
  }
  return "warning" as const;
}

function isActiveStatus(status: string) {
  return status === "queued" || status === "running";
}

function itemSearchText(item: AnalysisSummary) {
  return [
    item.input_text,
    item.display_summary,
    item.current_stage_note,
    item.current_stage_label,
    item.template_selected,
    item.latest_confidence_label,
    item.status,
    item.mode,
    item.input_type,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function hasTemplate(value: AnalysisSummary["template_selected"]): value is NonNullable<AnalysisSummary["template_selected"]> {
  return value !== null && value !== undefined;
}

function AnalysisRow({ item }: { item: AnalysisSummary }) {
  const progressPercent = item.progress_percent ?? 0;

  return (
    <Link
      href={`/analyses/${item.id}`}
      className="grid gap-4 border-b border-black/10 py-4 transition last:border-b-0 hover:bg-black/[0.015] md:grid-cols-[minmax(0,1fr)_13rem]"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badgeVariant(item.status)}>{item.status}</Badge>
          {item.template_selected ? (
            <Badge variant="muted">{item.template_selected.replaceAll("_", " ")}</Badge>
          ) : null}
          {item.latest_confidence_label ? (
            <Badge variant="muted">{item.latest_confidence_label.replaceAll("_", " ")}</Badge>
          ) : null}
        </div>
        <h3 className="mt-2 text-base font-semibold leading-6 text-ink">{item.input_text}</h3>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-ink/60">
          {item.display_summary ??
            item.current_stage_note ??
            "Open the run to watch the memo and inspector unlock."}
        </p>
      </div>

      <div className="space-y-2 text-sm text-ink/55 md:text-right">
        <p className="font-medium text-ink/70">{new Date(item.updated_at).toLocaleString()}</p>
        <p className="capitalize">
          {item.mode} · {item.input_type}
        </p>
        {(item.status === "queued" || item.status === "running") && item.progress_percent !== null ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3 text-[10px] uppercase tracking-[0.16em] text-ink/45">
              <span>{item.current_stage_label ?? "Queued"}</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-black/5">
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
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [templateFilter, setTemplateFilter] = useState("all");

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

  const templateOptions = useMemo(
    () =>
      [...new Set(items.map((item) => item.template_selected).filter(hasTemplate))]
        .sort((left, right) => left.localeCompare(right)),
    [items],
  );
  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return items.filter((item) => {
      if (statusFilter === "active" && !isActiveStatus(item.status)) {
        return false;
      }
      if (statusFilter === "complete" && item.status !== "complete") {
        return false;
      }
      if (statusFilter === "failed" && item.status !== "failed") {
        return false;
      }
      if (templateFilter !== "all" && item.template_selected !== templateFilter) {
        return false;
      }
      if (normalizedQuery && !itemSearchText(item).includes(normalizedQuery)) {
        return false;
      }
      return true;
    });
  }, [items, query, statusFilter, templateFilter]);
  const running = useMemo(
    () => items.filter((item) => isActiveStatus(item.status)),
    [items],
  );
  const filteredRunning = useMemo(
    () => filteredItems.filter((item) => isActiveStatus(item.status)),
    [filteredItems],
  );
  const filteredCompleted = useMemo(
    () => filteredItems.filter((item) => !isActiveStatus(item.status)),
    [filteredItems],
  );
  const failedCount = useMemo(() => items.filter((item) => item.status === "failed").length, [items]);
  const hasFilters = query.trim().length > 0 || statusFilter !== "all" || templateFilter !== "all";

  function resetFilters() {
    setQuery("");
    setStatusFilter("all");
    setTemplateFilter("all");
  }

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

      <Panel className="p-5">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <label className="block">
            <span className="section-label">Search</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="field-control mt-2"
              placeholder="Search claims, summaries, stages, templates..."
              type="search"
            />
          </label>

          <div className="flex flex-wrap items-end gap-3">
            <label className="block w-full sm:w-64">
              <span className="section-label">Template</span>
              <select
                value={templateFilter}
                onChange={(event) => setTemplateFilter(event.target.value)}
                className="field-control mt-2"
              >
                <option value="all">All templates</option>
                {templateOptions.map((template) => (
                  <option key={template} value={template}>
                    {template.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={resetFilters}
              disabled={!hasFilters}
              className="secondary-action disabled:bg-white/45"
            >
              Reset
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-black/10 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-1.5">
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => setStatusFilter(filter.value)}
                className={cn(
                  "filter-chip",
                  statusFilter === filter.value ? "filter-chip-active" : "filter-chip-idle",
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <p className="text-sm text-ink/55">
            Showing {filteredItems.length} of {items.length} runs
          </p>
        </div>
      </Panel>

      <section className="grid gap-3 sm:grid-cols-3">
        <Panel className="p-4">
          <p className="section-label">Total</p>
          <p className="stat-number mt-2">{items.length}</p>
          <p className="mt-1 text-sm text-ink/60">Runs in the log</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Running</p>
          <p className="stat-number mt-2">{running.length}</p>
          <p className="mt-1 text-sm text-ink/60">Currently moving</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Needs review</p>
          <p className="stat-number mt-2">{failedCount}</p>
          <p className="mt-1 text-sm text-ink/60">Failed runs</p>
        </Panel>
      </section>

      <Panel className="p-5">
        <div className="border-b border-black/10 pb-3">
          <p className="section-label">Running</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Analyses in motion</h3>
        </div>
        <div>
          {!hasLoaded ? (
            <p className="py-5 text-sm leading-7 text-ink/60">Loading active analyses...</p>
          ) : filteredRunning.length ? (
            filteredRunning.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : hasFilters ? (
            <p className="py-5 text-sm leading-7 text-ink/60">
              No active analyses match the current filters.
            </p>
          ) : (
            <p className="py-5 text-sm leading-7 text-ink/60">
              No active analyses right now. Start one from Manual Analysis.
            </p>
          )}
        </div>
      </Panel>

      <Panel className="p-5">
        <div className="border-b border-black/10 pb-3">
          <p className="section-label">Completed</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Finished runs</h3>
        </div>
        <div>
          {!hasLoaded ? (
            <p className="py-5 text-sm leading-7 text-ink/60">Loading finished runs...</p>
          ) : filteredCompleted.length ? (
            filteredCompleted.map((item) => <AnalysisRow key={item.id} item={item} />)
          ) : hasFilters ? (
            <p className="py-5 text-sm leading-7 text-ink/60">
              No finished runs match the current filters.
            </p>
          ) : (
            <p className="py-5 text-sm leading-7 text-ink/60">
              Completed analyses will appear here once the desk has some history.
            </p>
          )}
        </div>
      </Panel>
    </div>
  );
}
