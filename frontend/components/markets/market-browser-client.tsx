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
import { Panel } from "@/components/ui/panel";
import {
  formatCurrency,
  formatDate,
  formatPercent,
  marketNoMidpoint,
  marketYesMidpoint,
} from "@/components/markets/market-format";

type MarketView = "popular" | "trending" | "liquidity" | "closing_soon" | "newest";

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
          <p className="mt-1 text-sm leading-6 text-ink/58">{market.event_title}</p>
        ) : null}
        <div className="mt-3 grid gap-2 text-sm text-ink/58 sm:grid-cols-3">
          <p>
            <span className="font-semibold text-ink">Liquidity:</span>{" "}
            {formatCurrency(market.liquidity)}
          </p>
          <p>
            <span className="font-semibold text-ink">24h:</span>{" "}
            {formatCurrency(market.volume_24h)}
          </p>
          <p>
            <span className="font-semibold text-ink">Ends:</span> {formatDate(market.expiry_at)}
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] lg:grid-cols-3">
        <div className="rounded-lg border border-black/10 bg-white/70 p-3">
          <p className="section-label">YES</p>
          <p className="mt-1 text-lg font-semibold text-ink">{formatPercent(yesMidpoint)}</p>
        </div>
        <div className="rounded-lg border border-black/10 bg-white/70 p-3">
          <p className="section-label">NO</p>
          <p className="mt-1 text-lg font-semibold text-ink">{formatPercent(noMidpoint)}</p>
        </div>
        <button
          type="button"
          onClick={() => onAnalyze(market)}
          disabled={isAnalyzeDisabled}
          className="primary-action min-h-[4.25rem] w-full"
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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchPublicMarkets({
      q: activeQuery || undefined,
      view,
      limit: 25,
    })
      .then((payload) => {
        if (!cancelled) {
          setMarkets(payload.items);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Could not load markets.");
          setMarkets([]);
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
  }, [activeQuery, view]);

  const pageTitle = useMemo(
    () => (activeQuery ? `Search: ${activeQuery}` : viewOptions.find((item) => item.value === view)?.label ?? "Markets"),
    [activeQuery, view],
  );

  async function handleAnalyze(market: PublicMarket) {
    setAnalyzingId(market.polymarket_id);
    setError(null);
    try {
      const result = await createManualAnalysis({
        include_premium: false,
        polymarket_market_id: market.polymarket_id,
      });
      router.push(`/analyses/${result.request.id}`);
    } catch (analysisError) {
      setError(
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
          <h2 className="page-title">Find live Polymarket questions worth reading deeply.</h2>
          <p className="page-intro">
            Browse public markets, inspect live pricing context, and send one into the research desk.
          </p>
        </div>
        <Panel className="space-y-3 p-4">
          <p className="section-label">Current view</p>
          <p className="font-serif text-2xl text-ink">{pageTitle}</p>
          <p className="text-sm leading-6 text-ink/58">
            {isLoading ? "Loading markets" : `${markets.length} markets loaded`}
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
            <button type="submit" className="primary-action h-[3.05rem]">
              Search
            </button>
            {activeQuery ? (
              <button
                type="button"
                onClick={() => {
                  setQueryInput("");
                  setActiveQuery("");
                }}
                className="secondary-action h-[3.05rem]"
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>
        <div className="flex flex-wrap gap-2">
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
              className={`rounded-md border px-3 py-2 text-sm font-semibold transition ${
                !activeQuery && view === option.value
                  ? "border-ink bg-ink text-white"
                  : "border-black/10 bg-white/65 text-ink/64 hover:bg-white hover:text-ink"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </Panel>

      {error ? (
        <div className="rounded-lg border border-ember/20 bg-ember/10 px-5 py-4 text-sm leading-7 text-ember">
          {error}
        </div>
      ) : null}

      <Panel className="p-5">
        <div className="border-b border-black/8 pb-3">
          <p className="section-label">{activeQuery ? "Search results" : pageTitle}</p>
          <h3 className="mt-1.5 font-serif text-2xl text-ink">Live markets</h3>
        </div>
        {isLoading ? (
          <div className="space-y-3 py-5 animate-pulse">
            <div className="h-16 rounded-lg bg-black/5" />
            <div className="h-16 rounded-lg bg-black/5" />
            <div className="h-16 rounded-lg bg-black/5" />
          </div>
        ) : markets.length ? (
          <div>
            {markets.map((market) => (
              <MarketRow
                key={market.polymarket_id}
                market={market}
                onAnalyze={handleAnalyze}
                isAnalyzing={analyzingId === market.polymarket_id}
                isAnalyzeDisabled={Boolean(analyzingId) || market.status === "closed"}
              />
            ))}
          </div>
        ) : (
          <div className="py-6 text-sm leading-7 text-ink/58">
            No markets matched this view.
          </div>
        )}
      </Panel>
    </div>
  );
}
