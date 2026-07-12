"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createManualAnalysis, fetchPublicMarket, PublicMarket } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
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
  ReturnSettings,
} from "@/components/markets/high-chance-return";
import { HighChanceReturnCard } from "@/components/markets/high-chance-return-card";
import { ResearchEdgeSignalCard } from "@/components/markets/research-edge-signal";

type MarketDetailClientProps = {
  polymarketId: string;
  initialReturnSettings?: ReturnSettings;
};

function statusVariant(status: string | null | undefined) {
  if (status === "active") {
    return "yes" as const;
  }
  if (status === "closed") {
    return "no" as const;
  }
  return "muted" as const;
}

export function MarketDetailClient({
  polymarketId,
  initialReturnSettings = DEFAULT_RETURN_SETTINGS,
}: MarketDetailClientProps) {
  const router = useRouter();
  const [market, setMarket] = useState<PublicMarket | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchPublicMarket(polymarketId)
      .then((payload) => {
        if (!cancelled) {
          setMarket(payload);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Could not load market.");
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
  }, [polymarketId]);

  async function handleAnalyze() {
    if (!market) {
      return;
    }
    setIsAnalyzing(true);
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
      setIsAnalyzing(false);
    }
  }

  if (isLoading) {
    return (
      <Panel className="space-y-4 p-5 animate-pulse">
        <div className="h-4 w-32 rounded-full bg-black/8" />
        <div className="h-10 max-w-3xl rounded-lg bg-black/8" />
        <div className="grid gap-3 md:grid-cols-4">
          <div className="h-24 rounded-lg bg-black/8" />
          <div className="h-24 rounded-lg bg-black/8" />
          <div className="h-24 rounded-lg bg-black/8" />
          <div className="h-24 rounded-lg bg-black/8" />
        </div>
      </Panel>
    );
  }

  if (!market) {
    return (
      <div className="space-y-4">
        <Link href="/markets" className="secondary-action">
          Back to markets
        </Link>
        <div className="rounded-lg border border-ember/20 bg-ember/10 px-5 py-4 text-sm leading-7 text-ember">
          {error ?? "Market not found."}
        </div>
      </div>
    );
  }

  const yesMidpoint = marketYesMidpoint(market);
  const noMidpoint = marketNoMidpoint(market);
  const isClosed = market.status === "closed";
  const resolutionText =
    market.rules_text || market.description || "No resolution text was returned for this market.";
  const contextText =
    market.description && market.description !== resolutionText
      ? market.description
      : "Resolution details are shown in the rules panel.";
  const highChanceReturn = calculateHighChanceReturn(market, initialReturnSettings);

  return (
    <div className="space-y-6">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Link href="/markets" className="secondary-action">
            Back to markets
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(market.status)}>{market.status ?? "market"}</Badge>
            {market.category ? <Badge variant="muted">{market.category}</Badge> : null}
            {market.featured ? <Badge variant="warning">featured</Badge> : null}
          </div>
          <h2 className="page-title">{market.title}</h2>
          {market.event_title ? (
            <p className="page-intro">{market.event_title}</p>
          ) : null}
        </div>

        <Panel className="space-y-4 p-5">
          <p className="section-label">Action</p>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isAnalyzing || isClosed}
            className="primary-action w-full"
          >
            {isClosed ? "Market closed" : isAnalyzing ? "Starting analysis..." : "Analyze this market"}
          </button>
          {market.url ? (
            <Link href={market.url} target="_blank" className="secondary-action w-full">
              Open on Polymarket
            </Link>
          ) : null}
        </Panel>
      </section>

      {error ? (
        <div className="rounded-lg border border-ember/20 bg-ember/10 px-5 py-4 text-sm leading-7 text-ember">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <HighChanceReturnCard result={highChanceReturn} settings={initialReturnSettings} />
        <ResearchEdgeSignalCard signal={market.research_edge_signal} />
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Panel className="p-4">
          <p className="section-label">YES price</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{formatPercent(yesMidpoint)}</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">NO price</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{formatPercent(noMidpoint)}</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Liquidity</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{formatCurrency(market.liquidity)}</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">24h volume</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{formatCurrency(market.volume_24h)}</p>
        </Panel>
        <Panel className="p-4">
          <p className="section-label">Ends</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{formatDate(market.expiry_at)}</p>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-3">
            <p className="section-label">Resolution</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Rules</h3>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-7 text-ink/68">
            {resolutionText}
          </p>
        </Panel>

        <Panel className="space-y-4 p-5">
          <div className="border-b border-black/8 pb-3">
            <p className="section-label">Market</p>
            <h3 className="mt-1.5 font-serif text-2xl text-ink">Context</h3>
          </div>
          <div className="space-y-3 text-sm leading-7 text-ink/64">
            <p>{contextText}</p>
            <p>
              <span className="font-semibold text-ink">Spread:</span>{" "}
              {formatPercent(market.spread)}
            </p>
            <p>
              <span className="font-semibold text-ink">Polymarket ID:</span>{" "}
              {market.polymarket_id}
            </p>
          </div>
        </Panel>
      </section>
    </div>
  );
}
