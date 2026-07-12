import { PublicMarket } from "@/lib/api";
import { marketNoMidpoint, marketYesMidpoint } from "@/components/markets/market-format";

export type ReturnSettings = {
  stake: number;
  minimumProbability: number;
  minimumProfit: number;
};

export type HighChanceReturn = {
  qualifies: boolean;
  side: "yes" | "no" | null;
  impliedProbability: number | null;
  executionPrice: number | null;
  grossProfitIfCorrect: number | null;
  bufferedProfitIfCorrect: number | null;
  maximumLoss: number;
  spread: number | null;
  reason: string;
};

export const DEFAULT_RETURN_SETTINGS: ReturnSettings = {
  stake: 100,
  minimumProbability: 0.6,
  minimumProfit: 1,
};

export const EXECUTION_ALLOWANCE_RATE = 0.01;
export const MAX_ACCEPTABLE_SPREAD = 0.05;

type SideCandidate = {
  side: "yes" | "no";
  impliedProbability: number;
  executionPrice: number;
  grossProfitIfCorrect: number;
  bufferedProfitIfCorrect: number;
  spread: number;
};

function candidateForSide(
  market: PublicMarket,
  side: "yes" | "no",
  stake: number,
): SideCandidate | null {
  const bid = side === "yes" ? market.yes_bid : market.no_bid;
  const ask = side === "yes" ? market.yes_ask : market.no_ask;
  const impliedProbability = side === "yes" ? marketYesMidpoint(market) : marketNoMidpoint(market);
  if (
    bid === null ||
    bid === undefined ||
    ask === null ||
    ask === undefined ||
    impliedProbability === null ||
    ask <= 0 ||
    ask >= 1
  ) {
    return null;
  }

  const grossProfitIfCorrect = stake * (1 / ask - 1);
  const bufferedProfitIfCorrect = grossProfitIfCorrect - stake * EXECUTION_ALLOWANCE_RATE;
  return {
    side,
    impliedProbability,
    executionPrice: ask,
    grossProfitIfCorrect,
    bufferedProfitIfCorrect,
    spread: Math.max(ask - bid, 0),
  };
}

export function calculateHighChanceReturn(
  market: PublicMarket,
  settings: ReturnSettings,
): HighChanceReturn {
  const stake = Math.max(settings.stake, 0);
  const candidates = (["yes", "no"] as const)
    .map((side) => candidateForSide(market, side, stake))
    .filter((candidate): candidate is SideCandidate => candidate !== null)
    .sort((left, right) => right.impliedProbability - left.impliedProbability);
  const best = candidates[0] ?? null;

  if (!best) {
    return {
      qualifies: false,
      side: null,
      impliedProbability: null,
      executionPrice: null,
      grossProfitIfCorrect: null,
      bufferedProfitIfCorrect: null,
      maximumLoss: stake,
      spread: null,
      reason: "Executable bid and ask prices are unavailable.",
    };
  }

  const qualifies =
    market.status === "active" &&
    best.impliedProbability >= settings.minimumProbability &&
    best.bufferedProfitIfCorrect >= settings.minimumProfit &&
    best.spread !== null &&
    best.spread <= MAX_ACCEPTABLE_SPREAD;

  let reason: string;
  if (market.status !== "active") {
    reason = "The market is not active.";
  } else if (best.impliedProbability < settings.minimumProbability) {
    reason = `No side reaches ${(settings.minimumProbability * 100).toFixed(0)}% market-implied probability.`;
  } else if (best.bufferedProfitIfCorrect < settings.minimumProfit) {
    reason = `The estimated profit does not reach $${settings.minimumProfit.toFixed(2)} after the 1% execution allowance.`;
  } else if (best.spread > MAX_ACCEPTABLE_SPREAD) {
    reason = "The bid-ask spread is wider than the 5% execution guardrail.";
  } else {
    reason = `${best.side.toUpperCase()} clears your chance and buffered-profit settings.`;
  }

  return {
    qualifies,
    ...best,
    maximumLoss: stake,
    reason,
  };
}
