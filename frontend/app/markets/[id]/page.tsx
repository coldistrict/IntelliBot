import { MarketDetailClient } from "@/components/markets/market-detail-client";

type MarketDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default async function MarketDetailPage({ params }: MarketDetailPageProps) {
  const { id } = await params;
  return <MarketDetailClient polymarketId={id} />;
}
