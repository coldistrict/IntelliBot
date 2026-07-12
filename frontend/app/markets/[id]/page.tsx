import { MarketDetailClient } from "@/components/markets/market-detail-client";

type MarketDetailPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ stake?: string; chance?: string; profit?: string }>;
};

function finiteOrDefault(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default async function MarketDetailPage({ params, searchParams }: MarketDetailPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const stake = Math.max(finiteOrDefault(query.stake, 100), 1);
  const chance = Math.min(Math.max(finiteOrDefault(query.chance, 60), 50), 99.9);
  const profit = Math.max(finiteOrDefault(query.profit, 1), 0);
  return (
    <MarketDetailClient
      polymarketId={id}
      initialReturnSettings={{
        stake,
        minimumProbability: chance / 100,
        minimumProfit: profit,
      }}
    />
  );
}
