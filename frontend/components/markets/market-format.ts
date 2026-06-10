import { PublicMarket } from "@/lib/api";

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  const percentage = value * 100;
  const rounded = Math.round(percentage);
  return Math.abs(percentage - rounded) >= 0.05 ? `${percentage.toFixed(1)}%` : `${rounded}%`;
}

export function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
    notation: value >= 1_000_000 ? "compact" : "standard",
    style: "currency",
  }).format(value);
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function marketYesMidpoint(market: PublicMarket) {
  if (market.yes_bid !== null && market.yes_bid !== undefined && market.yes_ask !== null && market.yes_ask !== undefined) {
    return (market.yes_bid + market.yes_ask) / 2;
  }
  return market.yes_ask ?? market.yes_bid ?? null;
}

export function marketNoMidpoint(market: PublicMarket) {
  if (market.no_bid !== null && market.no_bid !== undefined && market.no_ask !== null && market.no_ask !== undefined) {
    return (market.no_bid + market.no_ask) / 2;
  }
  return market.no_ask ?? market.no_bid ?? null;
}
