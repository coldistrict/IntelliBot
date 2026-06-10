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
    return "text-ink/62";
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
        <h2 className="page-title">Did the desk actually call it? Track every resolved market.</h2>
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
          {refreshNote ? <p className="text-sm text-ink/62">{refreshNote}</p> : null}
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Panel className="p-4">
          <p className="section-label">Resolved runs</p>
          <p className="mt-2 text-3xl font-semibold text-ink">{summary?.resolved_runs ?? 0}</p>
          <p className="mt-1 text-sm text-ink/58">
            {summary?.pending_runs ?? 0} awaiting resolution · {summary?.unlinked_runs ?? 0} without
            a linked market
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Model vs market (Brier)</p>
          <p className="mt-2 text-3xl font-semibold text-ink">
            {formatBrier(summary?.head_to_head_model_brier)}
            <span className="text-base font-normal text-ink/55">
              {" "}
              vs {formatBrier(summary?.head_to_head_market_brier)}
            </span>
          </p>
          <p className="mt-1 text-sm text-ink/58">
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
          <p className="mt-2 text-3xl font-semibold text-ink">
            {formatPercent(summary?.direction_hit_rate)}
          </p>
          <p className="mt-1 text-sm text-ink/58">
            {summary?.direction_calls ?? 0} directional call(s) scored
          </p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Virtual P&amp;L</p>
          <p className={cn("mt-2 text-3xl font-semibold", pnlTone(summary?.total_pnl))}>
            {formatPnl(summary?.total_pnl ?? 0)}
          </p>
          <p className="mt-1 text-sm text-ink/58">
            {summary?.trade_count ?? 0} virtual trade(s) · {summary?.trade_wins ?? 0} won ·{" "}
            {summary?.roi_per_trade !== null && summary?.roi_per_trade !== undefined
              ? `${(summary.roi_per_trade * 100).toFixed(1)}% per trade`
              : "no trades yet"}
          </p>
        </Panel>
      </section>

      {!hasLoaded ? (
        <Panel className="p-7">
          <p className="text-sm leading-7 text-ink/58">Loading the scoreboard...</p>
        </Panel>
      ) : !hasResolved ? (
        <Panel className="p-7">
          <p className="section-label">No resolved markets yet</p>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/62">
            Run analyses against live Polymarket markets, then come back after they resolve. Use
            “Check for resolutions” any time — once a market closes with a final outcome, the run is
            scored here automatically. Custom claims without a linked market cannot be scored.
          </p>
        </Panel>
      ) : (
        <>
          <Panel className="p-5">
            <div className="border-b border-black/8 pb-3">
              <p className="section-label">Calibration</p>
              <h3 className="mt-1.5 font-serif text-2xl text-ink">
                When the desk says 70%, does it happen 70% of the time?
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full min-w-[34rem] text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-ink/46">
                    <th className="py-2 pr-4 font-semibold">Forecast bucket</th>
                    <th className="py-2 pr-4 font-semibold">Runs</th>
                    <th className="py-2 pr-4 font-semibold">Avg forecast</th>
                    <th className="py-2 pr-4 font-semibold">Actually resolved YES</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreboard?.buckets.map((bucket) => (
                    <tr key={bucket.label} className="border-t border-black/6">
                      <td className="py-2.5 pr-4 font-semibold text-ink">{bucket.label}</td>
                      <td className="py-2.5 pr-4 text-ink/68">{bucket.count}</td>
                      <td className="py-2.5 pr-4 text-ink/68">{formatProbability(bucket.avg_p_hat)}</td>
                      <td className="py-2.5 pr-4 text-ink/68">
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
              <div className="border-b border-black/8 pb-3">
                <p className="section-label">By template</p>
              </div>
              <SliceTable slices={scoreboard?.template_slices ?? []} />
            </Panel>
            <Panel className="p-5">
              <div className="border-b border-black/8 pb-3">
                <p className="section-label">By confidence</p>
              </div>
              <SliceTable slices={scoreboard?.confidence_slices ?? []} />
            </Panel>
          </section>

          <Panel className="p-5">
            <div className="border-b border-black/8 pb-3">
              <p className="section-label">Resolved runs</p>
              <h3 className="mt-1.5 font-serif text-2xl text-ink">Every scored call</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full min-w-[56rem] text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-ink/46">
                    <th className="py-2 pr-4 font-semibold">Market</th>
                    <th className="py-2 pr-4 font-semibold">Model</th>
                    <th className="py-2 pr-4 font-semibold">Market price</th>
                    <th className="py-2 pr-4 font-semibold">Outcome</th>
                    <th className="py-2 pr-4 font-semibold">Hit</th>
                    <th className="py-2 pr-4 font-semibold">Brier</th>
                    <th className="py-2 pr-4 font-semibold">Trade</th>
                    <th className="py-2 pr-4 font-semibold">P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreboard?.resolved.map((row) => (
                    <tr key={row.analysis_run_id} className="border-t border-black/6">
                      <td className="max-w-[22rem] py-2.5 pr-4">
                        <Link
                          href={`/analyses/${row.analysis_request_id}`}
                          className="font-semibold text-ink underline-offset-2 hover:underline"
                        >
                          {row.title}
                        </Link>
                        <p className="mt-0.5 text-xs text-ink/52">
                          {formatLabel(row.template)} · {formatLabel(row.recommendation_label)}
                        </p>
                      </td>
                      <td className="py-2.5 pr-4 text-ink/68">{formatProbability(row.p_hat)}</td>
                      <td className="py-2.5 pr-4 text-ink/68">
                        {formatProbability(row.market_mid_prob)}
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge variant={row.outcome === "yes" ? "yes" : "no"}>
                          {row.outcome.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        {row.direction_hit === null || row.direction_hit === undefined ? (
                          <span className="text-ink/45">—</span>
                        ) : row.direction_hit ? (
                          <Badge variant="yes">Hit</Badge>
                        ) : (
                          <Badge variant="no">Miss</Badge>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-ink/68">{formatBrier(row.model_brier)}</td>
                      <td className="py-2.5 pr-4 text-ink/68">
                        {row.trade_side
                          ? `${row.trade_side.toUpperCase()} @ ${formatProbability(row.trade_entry_price)}`
                          : "—"}
                      </td>
                      <td className={cn("py-2.5 pr-4 font-semibold", pnlTone(row.trade_pnl))}>
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
          <div className="border-b border-black/8 pb-3">
            <p className="section-label">Awaiting resolution</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">
              Open calls that will be scored later
            </h3>
          </div>
          <div className="divide-y divide-black/6">
            {scoreboard?.pending.map((row) => (
              <Link
                key={row.analysis_run_id}
                href={`/analyses/${row.analysis_request_id}`}
                className="flex flex-wrap items-center justify-between gap-3 py-3 transition hover:bg-black/[0.015]"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-ink">{row.title}</p>
                  <p className="mt-0.5 text-xs text-ink/52">
                    {formatLabel(row.recommendation_label)}
                    {row.market_expiry_at
                      ? ` · closes ${new Date(row.market_expiry_at).toLocaleDateString()}`
                      : ""}
                  </p>
                </div>
                <p className="text-sm font-semibold text-ink/68">
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
    return <p className="py-4 text-sm leading-7 text-ink/58">No resolved runs in this view yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="mt-2 w-full min-w-[24rem] text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-ink/46">
            <th className="py-2 pr-4 font-semibold">Slice</th>
            <th className="py-2 pr-4 font-semibold">Runs</th>
            <th className="py-2 pr-4 font-semibold">Brier</th>
            <th className="py-2 pr-4 font-semibold">Hit rate</th>
            <th className="py-2 pr-4 font-semibold">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((slice) => (
            <tr key={slice.key} className="border-t border-black/6">
              <td className="py-2.5 pr-4 font-semibold capitalize text-ink">
                {formatLabel(slice.key)}
              </td>
              <td className="py-2.5 pr-4 text-ink/68">{slice.resolved_runs}</td>
              <td className="py-2.5 pr-4 text-ink/68">{formatBrier(slice.avg_model_brier)}</td>
              <td className="py-2.5 pr-4 text-ink/68">{formatPercent(slice.direction_hit_rate)}</td>
              <td className={cn("py-2.5 pr-4 font-semibold", pnlTone(slice.total_pnl))}>
                {formatPnl(slice.total_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
