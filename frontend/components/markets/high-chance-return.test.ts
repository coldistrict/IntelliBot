import { describe, expect, it } from "vitest";

import { PublicMarket } from "@/lib/api";
import {
  calculateHighChanceReturn,
  DEFAULT_RETURN_SETTINGS,
} from "@/components/markets/high-chance-return";

function marketWithPrices(overrides: Partial<PublicMarket> = {}): PublicMarket {
  return {
    polymarket_id: "example",
    title: "Example market",
    url: null,
    rules_text: null,
    description: null,
    yes_bid: 0.14,
    yes_ask: 0.145,
    no_bid: 0.855,
    no_ask: 0.86,
    liquidity: 100000,
    volume_24h: 10000,
    spread: 0.005,
    expiry_at: null,
    status: "active",
    category: null,
    event_title: null,
    event_slug: null,
    image: null,
    featured: false,
    is_new: false,
    research_edge_signal: {
      status: "analysis_needed",
      reason: "Research not run.",
    },
    ...overrides,
  };
}

describe("calculateHighChanceReturn", () => {
  it("finds the higher-probability side and estimates buffered profit", () => {
    const result = calculateHighChanceReturn(marketWithPrices(), DEFAULT_RETURN_SETTINGS);

    expect(result.qualifies).toBe(true);
    expect(result.side).toBe("no");
    expect(result.impliedProbability).toBeCloseTo(0.8575);
    expect(result.executionPrice).toBe(0.86);
    expect(result.grossProfitIfCorrect).toBeCloseTo(16.279, 3);
    expect(result.bufferedProfitIfCorrect).toBeCloseTo(15.279, 3);
    expect(result.maximumLoss).toBe(100);
  });

  it("does not treat a large payout at coin-flip odds as higher chance", () => {
    const result = calculateHighChanceReturn(
      marketWithPrices({
        yes_bid: 0.5,
        yes_ask: 0.5025,
        no_bid: 0.4975,
        no_ask: 0.5,
      }),
      DEFAULT_RETURN_SETTINGS,
    );

    expect(result.qualifies).toBe(false);
    expect(result.reason).toBe("No side reaches 60% market-implied probability.");
  });

  it("rejects a high probability when the buffered return is too small", () => {
    const result = calculateHighChanceReturn(
      marketWithPrices({
        yes_bid: 0.004,
        yes_ask: 0.005,
        no_bid: 0.995,
        no_ask: 0.996,
      }),
      DEFAULT_RETURN_SETTINGS,
    );

    expect(result.qualifies).toBe(false);
    expect(result.reason).toContain("estimated profit does not reach $1.00");
  });

  it("rejects wide spreads even when midpoint probability clears the threshold", () => {
    const result = calculateHighChanceReturn(
      marketWithPrices({
        yes_bid: 0.1,
        yes_ask: 0.2,
        no_bid: 0.8,
        no_ask: 0.9,
      }),
      DEFAULT_RETURN_SETTINGS,
    );

    expect(result.qualifies).toBe(false);
    expect(result.reason).toContain("spread is wider than the 5% execution guardrail");
  });
});
