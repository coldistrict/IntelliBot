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

type MarketView = "popular" | "trending" | "liquidity" | "closing_soon" | "newest";

const PAGE_SIZE = 25;

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
}: {
  market: PublicMarket;
  onAnalyze: (market: PublicMarket) => void;
  isAnalyzing: boolean;
  isAnalyzeDisabled: boolean;
}) {
  const yesMidpoint = marketYesMidpoint(market);
  const noMidpoint = marketNoMidpoint(market);
  const isClosed = market.status === "closed";

  return (
    <article className="surface-row grid gap-4 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-start">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={marketStatusVariant(market.status)}>{market.status ?? "market"}</Badge>
          {market.category ? <Badge variant="muted">{market.category}</Badge> : null}
          {market.featured ? <Badge variant="warning">featured</Badge> : null}
          {market.is_new ? <Badge variant="muted">new</Badge> : null}
        </div>
        <Link
          href={`/markets/${encodeURIComponent(market.polymarket_id)}`}
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

      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] lg:grid-cols-3">
        <div className="rounded-lg border border-pine/20 bg-pine/5 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-pine/80">Yes</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-pine">
            {formatPercent(yesMidpoint)}
          </p>
        </div>
        <div className="rounded-lg border border-ember/20 bg-ember/5 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ember/80">No</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-ember">
            {formatPercent(noMidpoint)}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onAnalyze(market)}
          disabled={isAnalyzeDisabled}
          className="primary-action h-full w-full"
        >
          {isClosed ? "Closed" : isAnalyzing ? "Starting..." : "Analyze"}
        </button>
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
          <h1 className="page-title">Find live Polymarket questions worth reading deeply.</h1>
          <p className="page-intro">
            Browse public markets, inspect live pricing context, and send one into the research desk.
          </p>
        </div>
        <Panel className="space-y-3 p-4">
          <p className="section-label">Current view</p>
          <p className="font-serif text-2xl text-ink">{pageTitle}</p>
          <p className="text-sm leading-6 text-ink/60">
            {isLoading
              ? "Loading markets"
              : loadError && markets.length === 0
                ? "Market list unavailable"
                : `${markets.length}${hasMore ? "+" : ""} markets loaded`}
          </p>
        </Panel>
      </section>

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
        </div>
      </Panel>

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
        ) : markets.length ? (
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
            {markets.map((market) => (
              <MarketRow
                key={market.polymarket_id}
                market={market}
                onAnalyze={handleAnalyze}
                isAnalyzing={analyzingId === market.polymarket_id}
                isAnalyzeDisabled={Boolean(analyzingId) || market.status === "closed"}
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
          <DataState variant="empty" note="No markets matched this view." />
        )}
      </Panel>
    </div>
  );
}
