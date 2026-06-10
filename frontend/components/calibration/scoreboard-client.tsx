"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import {
  CalibrationScoreboard,
  OutcomeRefreshSummary,
  fetchCalibrationScoreboard,
  refreshCalibrationOutcomes,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function formatProbability(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  const percent = value * 100;
  if (percent > 99 && percent < 100) {
    return ">99%";
  }
  if (percent > 0 && percent < 1) {
    return "<1%";
  }
  return `${percent.toFixed(0)}%`;
}

function formatBrier(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  if (value > 0 && value < 0.001) {
    return "<0.001";
  }
  return value.toFixed(3);
}

function formatPnl(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "—";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}$${value.toFixed(2)}`;
}

function pnlTone(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) {
    return "text-ink/60";
  }
  return value > 0 ? "text-pine" : "text-ember";
}

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return "—";
  }
  return value.replaceAll("_", " ");
}

export function ScoreboardClient() {
  const [scoreboard, setScoreboard] = useState<CalibrationScoreboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = await fetchCalibrationScoreboard();
      setScoreboard(payload);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load the scoreboard.");
    } finally {
      setHasLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRefresh() {
    setIsRefreshing(true);
    setRefreshNote(null);
    try {
      const summary: OutcomeRefreshSummary = await refreshCalibrationOutcomes();
      const parts = [
        `${summary.markets_checked} market(s) checked`,
        `${summary.newly_resolved} newly resolved`,
        `${summary.still_open} still open`,
      ];
      if (summary.lookup_failures > 0) {
        parts.push(`${summary.lookup_failures} lookup failure(s)`);
      }
      setRefreshNote(parts.join(" · "));
      await load();
    } catch (refreshError) {
      setRefreshNote(
        refreshError instanceof Error ? refreshError.message : "Outcome refresh failed.",
      );
    } finally {
      setIsRefreshing(false);
    }
  }

  if (error) {
    return (
      <Panel className="p-7">
        <p className="eyebrow">Scoreboard</p>
        <p className="mt-4 text-sm text-ember">{error}</p>
      </Panel>
    );
  }

  const summary = scoreboard?.summary;
  const hasResolved = (summary?.resolved_runs ?? 0) > 0;
  const headToHeadDelta =
    summary &&
    summary.head_to_head_model_brier !== null &&
    summary.head_to_head_model_brier !== undefined &&
    summary.head_to_head_market_brier !== null &&
    summary.head_to_head_market_brier !== undefined
      ? summary.head_to_head_market_brier - summary.head_to_head_model_brier
      : null;

  return (
    <div className="space-y-6">
      <section className="max-w-5xl space-y-4">
        <p className="eyebrow">Scoreboard</p>
        <h1 className="page-title">Did the desk actually call it? Track every resolved market.</h1>
        <p className="page-intro">
          Once an analyzed market resolves on Polymarket, the run is scored against reality: Brier
          accuracy, direction hit rate, and the virtual P&amp;L of following every lean with $100.
          Lower Brier is better; 0.25 is what always guessing 50/50 scores.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="primary-action disabled:opacity-60"
          >
            {isRefreshing ? "Checking resolutions..." : "Check for resolutions"}
          </button>
          {refreshNote ? <p className="text-sm text-ink/60">{refreshNote}</p> : null}
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Panel className="p-4">
          <p className="section-label">Resolved runs</p>
          <p className="stat-number mt-2">{summary?.resolved_runs ?? 0}</p>
          <p className="mt-1 text-sm text-ink/60">
            {summary?.pending_runs ?? 0} awaiting resolution · {summary?.unlinked_runs ?? 0} without
            a linked market
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Model vs market (Brier)</p>
          <p className="stat-number mt-2">
            {formatBrier(summary?.head_to_head_model_brier)}
            <span className="text-base font-normal text-ink/60">
              {" "}
              vs {formatBrier(summary?.head_to_head_market_brier)}
            </span>
          </p>
          <p className="mt-1 text-sm text-ink/60">
            {headToHeadDelta === null
              ? "Needs resolved runs with a market prior"
              : headToHeadDelta > 0
                ? "Model is beating the market price"
                : headToHeadDelta < 0
                  ? "Market price is still more accurate"
                  : "Dead even with the market"}
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Direction hit rate</p>
          <p className="stat-number mt-2">
            {formatPercent(summary?.direction_hit_rate)}
          </p>
          <p className="mt-1 text-sm text-ink/60">
            {summary?.direction_calls ?? 0} directional call(s) scored
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Virtual P&amp;L</p>
          <p
            className={cn(
              "mt-2 font-serif text-4xl font-medium leading-none tracking-[-0.01em] lining-nums tabular-nums",
              pnlTone(summary?.total_pnl),
            )}
          >
            {formatPnl(summary?.total_pnl ?? 0)}
          </p>
          <p className="mt-1 text-sm text-ink/60">
            {summary?.trade_count ?? 0} virtual trade(s) · {summary?.trade_wins ?? 0} won ·{" "}
            {summary?.roi_per_trade !== null && summary?.roi_per_trade !== undefined
              ? `${(summary.roi_per_trade * 100).toFixed(1)}% per trade`
              : "no trades yet"}
          </p>
        </Panel>
      </section>

      {!hasLoaded ? (
        <Panel className="p-7">
          <p className="text-sm leading-7 text-ink/60">Loading the scoreboard...</p>
        </Panel>
      ) : !hasResolved ? (
        <Panel className="p-7">
          <p className="section-label">No resolved markets yet</p>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/60">
            Run analyses against live Polymarket markets, then come back after they resolve. Use
            “Check for resolutions” any time — once a market closes with a final outcome, the run is
            scored here automatically. Custom claims without a linked market cannot be scored.
          </p>
        </Panel>
      ) : (
        <>
          <Panel className="p-5">
            <div className="border-b border-black/10 pb-3">
              <p className="section-label">Calibration</p>
              <h3 className="mt-1.5 font-serif text-2xl text-ink">
                When the desk says 70%, does it happen 70% of the time?
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table mt-2 min-w-[34rem]">
                <thead>
                  <tr>
                    <th>Forecast bucket</th>
                    <th>Runs</th>
                    <th>Avg forecast</th>
                    <th>Actually resolved YES</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreboard?.buckets.map((bucket) => (
                    <tr key={bucket.label}>
                      <td className="font-semibold text-ink">{bucket.label}</td>
                      <td className="text-ink/70">{bucket.count}</td>
                      <td className="text-ink/70">{formatProbability(bucket.avg_p_hat)}</td>
                      <td className="text-ink/70">
                        {formatPercent(bucket.actual_yes_rate)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <section className="grid gap-3 lg:grid-cols-2">
            <Panel className="p-5">
              <div className="border-b border-black/10 pb-3">
                <p className="section-label">By template</p>
              </div>
              <SliceTable slices={scoreboard?.template_slices ?? []} />
            </Panel>
            <Panel className="p-5">
              <div className="border-b border-black/10 pb-3">
                <p className="section-label">By confidence</p>
              </div>
              <SliceTable slices={scoreboard?.confidence_slices ?? []} />
            </Panel>
          </section>

          <Panel className="p-5">
            <div className="border-b border-black/10 pb-3">
              <p className="section-label">Resolved runs</p>
              <h3 className="mt-1.5 font-serif text-2xl text-ink">Every scored call</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="data-table mt-2 min-w-[56rem]">
                <thead>
                  <tr>
                    <th>Market</th>
                    <th>Model</th>
                    <th>Market price</th>
                    <th>Outcome</th>
                    <th>Hit</th>
                    <th>Brier</th>
                    <th>Trade</th>
                    <th>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreboard?.resolved.map((row) => (
                    <tr key={row.analysis_run_id}>
                      <td className="max-w-[22rem]">
                        <Link
                          href={`/analyses/${row.analysis_request_id}`}
                          className="font-semibold text-ink underline-offset-2 hover:underline"
                        >
                          {row.title}
                        </Link>
                        <p className="mt-0.5 text-xs text-ink/50">
                          {formatLabel(row.template)} · {formatLabel(row.recommendation_label)}
                        </p>
                      </td>
                      <td className="text-ink/70">{formatProbability(row.p_hat)}</td>
                      <td className="text-ink/70">
                        {formatProbability(row.market_mid_prob)}
                      </td>
                      <td>
                        <Badge variant={row.outcome === "yes" ? "yes" : "no"}>
                          {row.outcome.toUpperCase()}
                        </Badge>
                      </td>
                      <td>
                        {row.direction_hit === null || row.direction_hit === undefined ? (
                          <span className="text-ink/50">—</span>
                        ) : row.direction_hit ? (
                          <Badge variant="yes">Hit</Badge>
                        ) : (
                          <Badge variant="no">Miss</Badge>
                        )}
                      </td>
                      <td className="text-ink/70">{formatBrier(row.model_brier)}</td>
                      <td className="text-ink/70">
                        {row.trade_side
                          ? `${row.trade_side.toUpperCase()} @ ${formatProbability(row.trade_entry_price)}`
                          : "—"}
                      </td>
                      <td className={cn("font-semibold tabular-nums", pnlTone(row.trade_pnl))}>
                        {formatPnl(row.trade_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}

      {hasLoaded && (scoreboard?.pending.length ?? 0) > 0 ? (
        <Panel className="p-5">
          <div className="border-b border-black/10 pb-3">
            <p className="section-label">Awaiting resolution</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">
              Open calls that will be scored later
            </h3>
          </div>
          <div className="divide-y divide-black/5">
            {scoreboard?.pending.map((row) => (
              <Link
                key={row.analysis_run_id}
                href={`/analyses/${row.analysis_request_id}`}
                className="flex flex-wrap items-center justify-between gap-3 py-3 transition hover:bg-black/[0.015]"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-ink">{row.title}</p>
                  <p className="mt-0.5 text-xs text-ink/50">
                    {formatLabel(row.recommendation_label)}
                    {row.market_expiry_at
                      ? ` · closes ${new Date(row.market_expiry_at).toLocaleDateString()}`
                      : ""}
                  </p>
                </div>
                <p className="text-sm font-semibold text-ink/70">
                  model {formatProbability(row.p_hat)}
                </p>
              </Link>
            ))}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function SliceTable({
  slices,
}: {
  slices: Array<{
    key: string;
    resolved_runs: number;
    avg_model_brier: number | null;
    direction_hit_rate: number | null;
    trades: number;
    total_pnl: number;
  }>;
}) {
  if (!slices.length) {
    return <p className="py-4 text-sm leading-7 text-ink/60">No resolved runs in this view yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table mt-2 min-w-[24rem]">
        <thead>
          <tr>
            <th>Slice</th>
            <th>Runs</th>
            <th>Brier</th>
            <th>Hit rate</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((slice) => (
            <tr key={slice.key}>
              <td className="font-semibold capitalize text-ink">
                {formatLabel(slice.key)}
              </td>
              <td className="text-ink/70">{slice.resolved_runs}</td>
              <td className="text-ink/70">{formatBrier(slice.avg_model_brier)}</td>
              <td className="text-ink/70">{formatPercent(slice.direction_hit_rate)}</td>
              <td className={cn("font-semibold tabular-nums", pnlTone(slice.total_pnl))}>
                {formatPnl(slice.total_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
