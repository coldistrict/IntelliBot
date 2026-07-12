import Link from "next/link";

import { ResearchEdgeSignal } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  const percent = value * 100;
  return `${Math.abs(percent - Math.round(percent)) < 0.05 ? Math.round(percent) : percent.toFixed(1)}%`;
}

function formatEdge(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value >= 0 ? "+" : ""}${formatPercent(value)}`;
}

export function ResearchEdgeSignalCard({
  signal,
  compact = false,
  priceLabel = "Live price",
}: {
  signal: ResearchEdgeSignal;
  compact?: boolean;
  priceLabel?: string;
}) {
  const hasEdge = signal.status === "favorable";
  const needsAnalysis = signal.status === "analysis_needed";

  return (
    <section
      aria-label="Research edge check"
      className={cn(
        "rounded-lg border p-4",
        hasEdge
          ? "border-pine/25 bg-pine/[0.07]"
          : needsAnalysis
            ? "border-black/10 bg-black/[0.025]"
            : "border-pine/12 bg-pine/[0.025]",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant={hasEdge ? "yes" : "muted"}>
          {hasEdge ? "Research edge" : needsAnalysis ? "Research not run" : "No research edge"}
        </Badge>
        {signal.confidence ? (
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink/48">
            {signal.confidence} confidence
          </span>
        ) : null}
      </div>

      {hasEdge && signal.side ? (
        <>
          <p className={cn("mt-3 font-serif text-ink", compact ? "text-xl" : "text-3xl")}>
            {signal.side.toUpperCase()} has verified edge
          </p>
          <div className={cn("mt-3 grid gap-2", compact ? "grid-cols-2" : "sm:grid-cols-3")}>
            <div>
              <p className="section-label">Conservative chance</p>
              <p className="mt-1 font-semibold text-ink">
                {formatPercent(signal.conservative_probability)}
              </p>
            </div>
            <div>
              <p className="section-label">{priceLabel}</p>
              <p className="mt-1 font-semibold text-ink">{formatPercent(signal.live_price)}</p>
            </div>
            {!compact ? (
              <div>
                <p className="section-label">Edge after buffer</p>
                <p className="mt-1 font-semibold text-pine">
                  {formatEdge(signal.edge_after_buffer)}
                </p>
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <p className={cn("mt-3 font-serif text-ink", compact ? "text-lg" : "text-2xl")}>
          {needsAnalysis ? "Evidence check needed" : "Price edge not verified"}
        </p>
      )}

      <p className="mt-2 text-xs leading-5 text-ink/60">{signal.reason}</p>
      {signal.analyzed_at ? (
        <p className="mt-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink/42">
          Checked {new Date(signal.analyzed_at).toLocaleString()}
        </p>
      ) : null}
      {signal.analysis_id ? (
        <Link
          href={`/analyses/${signal.analysis_id}`}
          className="mt-3 inline-flex text-xs font-semibold text-pine underline decoration-pine/30 underline-offset-4"
        >
          Review the research
        </Link>
      ) : null}
    </section>
  );
}
