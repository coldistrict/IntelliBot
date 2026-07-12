"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  createManualAnalysis,
  fetchPublicMarkets,
  PublicMarket,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/ui/data-state";
import { Panel } from "@/components/ui/panel";
import {
  formatCurrency,
  formatDate,
  formatPercent,
  marketNoMidpoint,
  marketYesMidpoint,
} from "@/components/markets/market-format";
import {
  calculateHighChanceReturn,
  DEFAULT_RETURN_SETTINGS,
  HighChanceReturn,
  ReturnSettings,
} from "@/components/markets/high-chance-return";
import { HighChanceReturnCard } from "@/components/markets/high-chance-return-card";
import { ResearchEdgeSignalCard } from "@/components/markets/research-edge-signal";

type MarketView = "popular" | "trending" | "liquidity" | "closing_soon" | "newest";
type SignalFilter = "all" | "higher_chance" | "research_edge";
const MARKET_SCAN_SIZE = 70;

const PAGE_SIZE = MARKET_SCAN_SIZE;

const viewOptions: Array<{ value: MarketView; label: string }> = [
  { value: "popular", label: "Popular" },
  { value: "trending", label: "Trending" },
  { value: "liquidity", label: "High liquidity" },
  { value: "closing_soon", label: "Closing soon" },
  { value: "newest", label: "New" },
];

function marketStatusVariant(status: string | null | undefined) {
  if (status === "active") {
    return "yes" as const;
  }
  if (status === "closed") {
    return "no" as const;
  }
  return "muted" as const;
}

function MarketRow({
  market,
  onAnalyze,
  isAnalyzing,
  isAnalyzeDisabled,
  returnResult,
  returnSettings,
}: {
  market: PublicMarket;
  onAnalyze: (market: PublicMarket) => void;
  isAnalyzing: boolean;
  isAnalyzeDisabled: boolean;
  returnResult: HighChanceReturn;
  returnSettings: ReturnSettings;
}) {
  const yesMidpoint = marketYesMidpoint(market);
  const noMidpoint = marketNoMidpoint(market);
  const isClosed = market.status === "closed";

  return (
    <article className="surface-row grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem] xl:items-start">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={marketStatusVariant(market.status)}>{market.status ?? "market"}</Badge>
          {market.category ? <Badge variant="muted">{market.category}</Badge> : null}
          {market.featured ? <Badge variant="warning">featured</Badge> : null}
          {market.is_new ? <Badge variant="muted">new</Badge> : null}
        </div>
        <Link
          href={`/markets/${encodeURIComponent(market.polymarket_id)}?stake=${returnSettings.stake}&chance=${returnSettings.minimumProbability * 100}&profit=${returnSettings.minimumProfit}`}
          className="mt-2 block text-lg font-semibold leading-7 text-ink transition hover:text-pine"
        >
          {market.title}
        </Link>
        {market.event_title ? (
          <p className="mt-1 text-sm leading-6 text-ink/60">{market.event_title}</p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink/60">
          <p>
            <span className="font-medium text-ink/80">Liquidity</span>{" "}
            <span className="tabular-nums">{formatCurrency(market.liquidity)}</span>
          </p>
          <p>
            <span className="font-medium text-ink/80">24h volume</span>{" "}
            <span className="tabular-nums">{formatCurrency(market.volume_24h)}</span>
          </p>
          <p>
            <span className="font-medium text-ink/80">Ends</span> {formatDate(market.expiry_at)}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <HighChanceReturnCard result={returnResult} settings={returnSettings} compact />
        <ResearchEdgeSignalCard signal={market.research_edge_signal} compact />
        <div className="grid gap-2 grid-cols-[1fr_1fr_auto]">
          <div className="rounded-lg border border-pine/20 bg-pine/5 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-pine/80">YES</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-pine">{formatPercent(yesMidpoint)}</p>
          </div>
          <div className="rounded-lg border border-ember/20 bg-ember/5 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ember/80">NO</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-ember">{formatPercent(noMidpoint)}</p>
          </div>
          <button
            type="button"
            onClick={() => onAnalyze(market)}
            disabled={isAnalyzeDisabled}
            className="primary-action px-3"
          >
            {isClosed
              ? "Closed"
              : isAnalyzing
                ? "Starting..."
                : market.research_edge_signal.status === "analysis_needed"
                  ? "Analyze"
                  : "Refresh"}
          </button>
        </div>
      </div>
    </article>
  );
}

export function MarketBrowserClient() {
  const router = useRouter();
  const [view, setView] = useState<MarketView>("popular");
  const [queryInput, setQueryInput] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [markets, setMarkets] = useState<PublicMarket[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");
  const [stake, setStake] = useState(DEFAULT_RETURN_SETTINGS.stake);
  const [minimumChancePercent, setMinimumChancePercent] = useState(
    DEFAULT_RETURN_SETTINGS.minimumProbability * 100,
  );
  const [minimumProfit, setMinimumProfit] = useState(DEFAULT_RETURN_SETTINGS.minimumProfit);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);

    fetchPublicMarkets({
      q: activeQuery || undefined,
      view,
      limit: PAGE_SIZE,
    })
      .then((payload) => {
        if (!cancelled) {
          setMarkets(payload.items);
          setHasMore(payload.has_more);
        }
      })
      .catch((fetchError) => {
        if (!cancelled) {
          setLoadError(fetchError instanceof Error ? fetchError.message : "Could not load markets.");
          setMarkets([]);
          setHasMore(false);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeQuery, view, reloadKey]);

  const pageTitle = useMemo(
    () => (activeQuery ? `Search: ${activeQuery}` : viewOptions.find((item) => item.value === view)?.label ?? "Markets"),
    [activeQuery, view],
  );
  const returnSettings = useMemo<ReturnSettings>(
    () => ({
      stake: Math.max(stake, 1),
      minimumProbability: Math.min(Math.max(minimumChancePercent / 100, 0.5), 0.999),
      minimumProfit: Math.max(minimumProfit, 0),
    }),
    [minimumChancePercent, minimumProfit, stake],
  );
  const returnResults = useMemo(
    () =>
      new Map(
        markets.map((market) => [
          market.polymarket_id,
          calculateHighChanceReturn(market, returnSettings),
        ]),
      ),
    [markets, returnSettings],
  );
  const displayedMarkets = useMemo(
    () => {
      if (signalFilter === "higher_chance") {
        return markets.filter((market) => returnResults.get(market.polymarket_id)?.qualifies);
      }
      if (signalFilter === "research_edge") {
        return markets.filter((market) => market.research_edge_signal.status === "favorable");
      }
      return markets;
    },
    [markets, returnResults, signalFilter],
  );
  const higherChanceCount = useMemo(
    () => markets.filter((market) => returnResults.get(market.polymarket_id)?.qualifies).length,
    [markets, returnResults],
  );
  const researchEdgeCount = useMemo(
    () => markets.filter((market) => market.research_edge_signal.status === "favorable").length,
    [markets],
  );
  const checkedCount = useMemo(
    () => markets.filter((market) => market.research_edge_signal.status !== "analysis_needed").length,
    [markets],
  );
  const needsAnalysisCount = markets.length - checkedCount;

  async function handleLoadMore() {
    setIsLoadingMore(true);
    setLoadError(null);
    try {
      const payload = await fetchPublicMarkets({
        q: activeQuery || undefined,
        view,
        limit: PAGE_SIZE,
        offset: markets.length,
      });
      setMarkets((current) => [...current, ...payload.items]);
      setHasMore(payload.has_more);
    } catch (fetchError) {
      setLoadError(
        fetchError instanceof Error ? fetchError.message : "Could not load more markets.",
      );
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function handleAnalyze(market: PublicMarket) {
    setAnalyzingId(market.polymarket_id);
    setActionError(null);
    try {
      const result = await createManualAnalysis({
        include_premium: false,
        polymarket_market_id: market.polymarket_id,
      });
      router.push(`/analyses/${result.request.id}`);
    } catch (analysisError) {
      setActionError(
        analysisError instanceof Error
          ? analysisError.message
          : "Could not start analysis for this market.",
      );
      setAnalyzingId(null);
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveQuery(queryInput.trim());
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <p className="eyebrow">Market Browser</p>
          <h1 className="page-title">Find the markets where the numbers favor you.</h1>
          <p className="page-intro">
            Review 70 live markets for higher-chance returns now, then use the research desk to
            separate popular odds from evidence-backed price edge.
          </p>
        </div>
        <Panel className="space-y-3 p-4">
          <p className="section-label">Current view</p>
          <p className="font-serif text-2xl text-ink">{pageTitle}</p>
          <p className="text-sm leading-6 text-ink/58">
            {isLoading
              ? "Loading markets"
              : loadError && markets.length === 0
                ? "Market list unavailable"
                : signalFilter !== "all"
                  ? `${displayedMarkets.length} matching of ${markets.length} loaded`
                  : `${markets.length}${hasMore ? "+" : ""} markets loaded`}
          </p>
        </Panel>
      </section>

      <Panel className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-5">
        <div>
          <p className="section-label">Live universe</p>
          <p className="mt-2 font-serif text-3xl text-ink">{isLoading ? "—" : markets.length}</p>
          <p className="mt-1 text-xs leading-5 text-ink/52">of {MARKET_SCAN_SIZE} requested</p>
        </div>
        <div>
          <p className="section-label">Higher-chance</p>
          <p className="mt-2 font-serif text-3xl text-[#8a6314]">{isLoading ? "—" : higherChanceCount}</p>
          <p className="mt-1 text-xs leading-5 text-ink/52">matches your return rule</p>
        </div>
        <div>
          <p className="section-label">Research edge</p>
          <p className="mt-2 font-serif text-3xl text-pine">{isLoading ? "—" : researchEdgeCount}</p>
          <p className="mt-1 text-xs leading-5 text-ink/52">price edge verified</p>
        </div>
        <div>
          <p className="section-label">Research checked</p>
          <p className="mt-2 font-serif text-3xl text-ink">{isLoading ? "—" : checkedCount}</p>
          <p className="mt-1 text-xs leading-5 text-ink/52">fresh or recently rejected</p>
        </div>
        <div>
          <p className="section-label">Needs research</p>
          <p className="mt-2 font-serif text-3xl text-ember">{isLoading ? "—" : needsAnalysisCount}</p>
          <p className="mt-1 text-xs leading-5 text-ink/52">not counted as unfavorable</p>
        </div>
      </Panel>

      <Panel className="space-y-4 p-4">
        <div>
          <p className="section-label">Higher-chance return settings</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Define what a useful win looks like.</h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="section-label">Stake</span>
            <div className="relative mt-2">
              <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-sm text-ink/45">$</span>
              <input
                aria-label="Stake"
                type="number"
                min="1"
                step="1"
                value={stake}
                onChange={(event) => setStake(Number(event.target.value))}
                className="field-control pl-8"
              />
            </div>
          </label>
          <label className="block">
            <span className="section-label">Minimum implied chance</span>
            <div className="relative mt-2">
              <input
                aria-label="Minimum implied chance"
                type="number"
                min="50"
                max="99.9"
                step="1"
                value={minimumChancePercent}
                onChange={(event) => setMinimumChancePercent(Number(event.target.value))}
                className="field-control pr-8"
              />
              <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-sm text-ink/45">%</span>
            </div>
          </label>
          <label className="block">
            <span className="section-label">Minimum estimated profit</span>
            <div className="relative mt-2">
              <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-sm text-ink/45">$</span>
              <input
                aria-label="Minimum estimated profit"
                type="number"
                min="0"
                step="1"
                value={minimumProfit}
                onChange={(event) => setMinimumProfit(Number(event.target.value))}
                className="field-control pl-8"
              />
            </div>
          </label>
        </div>
        <p className="text-xs leading-5 text-ink/54">
          Profit estimates use the current ask and subtract a 1% execution allowance. Market-implied
          probability is crowd pricing, not a guarantee or a research forecast.
        </p>
      </Panel>

      <Panel className="space-y-4 p-4">
        <form className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleSubmit}>
          <label className="block">
            <span className="section-label">Search</span>
            <input
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className="field-control mt-2"
              placeholder="Fed rates, Bitcoin, Champions League..."
            />
          </label>
          <div className="flex items-end gap-2">
            <button type="submit" className="primary-action h-12">
              Search
            </button>
            {activeQuery ? (
              <button
                type="button"
                onClick={() => {
                  setQueryInput("");
                  setActiveQuery("");
                }}
                className="secondary-action h-12"
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0">
          {viewOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={!activeQuery && view === option.value}
              onClick={() => {
                setQueryInput("");
                setActiveQuery("");
                setView(option.value);
              }}
              className={`filter-chip shrink-0 whitespace-nowrap ${
                !activeQuery && view === option.value ? "filter-chip-active" : "filter-chip-idle"
              }`}
            >
              {option.label}
            </button>
          ))}
          <span className="mx-1 hidden h-9 w-px bg-black/10 sm:block" aria-hidden="true" />
          {([
            ["all", "All markets"],
            ["higher_chance", "Higher-chance only"],
            ["research_edge", "Research edge only"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={signalFilter === value}
              onClick={() => setSignalFilter(value)}
              className={`rounded-md border px-3 py-2 text-sm font-semibold transition ${
                signalFilter === value
                  ? value === "research_edge"
                    ? "border-pine bg-pine text-white"
                    : value === "higher_chance"
                      ? "border-[#8a6314] bg-[#8a6314] text-white"
                      : "border-ink bg-ink text-white"
                  : "border-black/10 bg-white/65 text-ink/64 hover:bg-white hover:text-ink"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </Panel>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-black/8 bg-white/60 p-4">
          <p className="section-label">1 · Higher chance</p>
          <p className="mt-2 text-sm leading-6 text-ink/62">The market midpoint must clear your chance threshold.</p>
        </div>
        <div className="rounded-lg border border-black/8 bg-white/60 p-4">
          <p className="section-label">2 · Useful return</p>
          <p className="mt-2 text-sm leading-6 text-ink/62">Profit at the ask must clear your target after a 1% allowance.</p>
        </div>
        <div className="rounded-lg border border-black/8 bg-white/60 p-4">
          <p className="section-label">3 · Full downside</p>
          <p className="mt-2 text-sm leading-6 text-ink/62">Every card shows that an incorrect outcome can lose the full stake.</p>
        </div>
        <div className="rounded-lg border border-black/8 bg-white/60 p-4">
          <p className="section-label">4 · Research edge</p>
          <p className="mt-2 text-sm leading-6 text-ink/62">A separate green signal asks whether evidence beats the market price.</p>
        </div>
      </div>

      {actionError ? (
        <DataState variant="error" title="Could not start the analysis" note={actionError} />
      ) : null}

      <Panel className="p-5">
        <div className="border-b border-black/10 pb-3">
          <p className="section-label">{activeQuery ? "Search results" : pageTitle}</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Live markets</h3>
        </div>
        {isLoading ? (
          <div className="space-y-3 py-5 animate-pulse">
            <div className="h-16 rounded-lg bg-black/5" />
            <div className="h-16 rounded-lg bg-black/5" />
            <div className="h-16 rounded-lg bg-black/5" />
          </div>
        ) : loadError && markets.length === 0 ? (
          <DataState
            variant="error"
            title="Markets cannot be loaded"
            note={loadError}
            onRetry={() => setReloadKey((key) => key + 1)}
            className="mt-4"
          />
        ) : displayedMarkets.length ? (
          <div>
            {loadError ? (
              <DataState
                variant="error"
                title="Loading more markets failed"
                note={loadError}
                onRetry={() => void handleLoadMore()}
                className="mt-4"
              />
            ) : null}
            {displayedMarkets.map((market) => (
              <MarketRow
                key={market.polymarket_id}
                market={market}
                onAnalyze={handleAnalyze}
                isAnalyzing={analyzingId === market.polymarket_id}
                isAnalyzeDisabled={Boolean(analyzingId) || market.status === "closed"}
                returnResult={returnResults.get(market.polymarket_id) ?? calculateHighChanceReturn(market, returnSettings)}
                returnSettings={returnSettings}
              />
            ))}
            {hasMore ? (
              <div className="border-t border-black/10 pt-4">
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={isLoadingMore}
                  className="secondary-action"
                >
                  {isLoadingMore ? "Loading more..." : `Load more (${markets.length} loaded)`}
                </button>
              </div>
            ) : null}
          </div>
        ) : (
          <DataState
            variant="empty"
            note={
              signalFilter === "higher_chance" && markets.length
                ? "No loaded market currently clears your chance and profit settings."
                : signalFilter === "research_edge" && markets.length
                  ? "No loaded market currently has verified research edge. Run or refresh analysis to check one."
                  : "No markets matched this view."
            }
          />
        )}
      </Panel>
    </div>
  );
}
