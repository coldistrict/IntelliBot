import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarketBrowserClient } from "@/components/markets/market-browser-client";
import { MarketDetailClient } from "@/components/markets/market-detail-client";
import { createManualAnalysis, fetchPublicMarket, fetchPublicMarkets } from "@/lib/api";

const push = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children: React.ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push,
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    createManualAnalysis: vi.fn(),
    fetchPublicMarket: vi.fn(),
    fetchPublicMarkets: vi.fn(),
  };
});

const market = {
  polymarket_id: "fed-cut-june-2026",
  title: "Will the Fed cut rates by June 2026?",
  url: "https://polymarket.com/event/fed-cut-june-2026",
  rules_text: "Resolves YES if the Federal Reserve cuts rates by June 2026.",
  description: "Federal Reserve interest-rate market.",
  yes_bid: 0.41,
  yes_ask: 0.43,
  no_bid: 0.57,
  no_ask: 0.59,
  liquidity: 25000,
  volume_24h: 5000,
  spread: 0.02,
  expiry_at: "2026-06-30T00:00:00Z",
  status: "active",
  category: "Economics",
  event_title: "Fed decision in June",
  event_slug: "fed-cut-june-2026",
  image: null,
  featured: true,
  is_new: false,
} as const;

describe("MarketBrowserClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPublicMarkets).mockResolvedValue({ items: [market], total: 1 });
    vi.mocked(fetchPublicMarket).mockResolvedValue(market);
    vi.mocked(createManualAnalysis).mockResolvedValue({
      request: {
        id: 99,
        mode: "manual",
        input_type: "market_id",
        input_text: market.polymarket_id,
        market_id: null,
        template_requested: null,
        template_selected: null,
        status: "queued",
        current_stage: "queued",
        error_message: null,
        started_at: null,
        completed_at: null,
        created_at: "2026-05-30T14:00:00Z",
        updated_at: "2026-05-30T14:00:00Z",
        latest_recommendation_label: null,
        latest_confidence_label: null,
        review_count: 0,
        progress_percent: 0,
        current_stage_label: "Queued",
        current_stage_note: "Queued.",
        display_summary: "Queued.",
        qualitative_label: null,
      },
    });
  });

  it("loads public markets and starts analysis from a market row", async () => {
    render(<MarketBrowserClient />);

    expect(await screen.findByText("Will the Fed cut rates by June 2026?")).toBeInTheDocument();
    expect(screen.getByText("Economics")).toBeInTheDocument();
    expect(screen.getByText("$25,000")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));

    await waitFor(() => {
      expect(createManualAnalysis).toHaveBeenCalledWith({
        include_premium: false,
        polymarket_market_id: "fed-cut-june-2026",
      });
      expect(push).toHaveBeenCalledWith("/analyses/99");
    });
  });

  it("submits search terms to market discovery", async () => {
    render(<MarketBrowserClient />);

    await screen.findByText("Will the Fed cut rates by June 2026?");
    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: "bitcoin" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(fetchPublicMarkets).toHaveBeenLastCalledWith({
        q: "bitcoin",
        view: "popular",
        limit: 25,
      });
    });
  });

  it("clears stale search input when switching back to a market view", async () => {
    render(<MarketBrowserClient />);

    await screen.findByText("Will the Fed cut rates by June 2026?");
    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: "bitcoin" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("Clear");
    fireEvent.click(screen.getByRole("button", { name: "Trending" }));

    expect(screen.getByLabelText(/search/i)).toHaveValue("");
    await waitFor(() => {
      expect(fetchPublicMarkets).toHaveBeenLastCalledWith({
        q: undefined,
        view: "trending",
        limit: 25,
      });
    });
  });
});

describe("MarketDetailClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPublicMarket).mockResolvedValue(market);
    vi.mocked(createManualAnalysis).mockResolvedValue({
      request: {
        id: 101,
        mode: "manual",
        input_type: "market_id",
        input_text: market.polymarket_id,
        market_id: null,
        template_requested: null,
        template_selected: null,
        status: "queued",
        current_stage: "queued",
        error_message: null,
        started_at: null,
        completed_at: null,
        created_at: "2026-05-30T14:00:00Z",
        updated_at: "2026-05-30T14:00:00Z",
        latest_recommendation_label: null,
        latest_confidence_label: null,
        review_count: 0,
        progress_percent: 0,
        current_stage_label: "Queued",
        current_stage_note: "Queued.",
        display_summary: "Queued.",
        qualitative_label: null,
      },
    });
  });

  it("renders market detail and starts analysis from the detail action", async () => {
    render(<MarketDetailClient polymarketId="fed-cut-june-2026" />);

    expect(await screen.findByRole("heading", { name: market.title })).toBeInTheDocument();
    expect(screen.getByText(market.rules_text)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /analyze this market/i }));

    await waitFor(() => {
      expect(createManualAnalysis).toHaveBeenCalledWith({
        include_premium: false,
        polymarket_market_id: "fed-cut-june-2026",
      });
      expect(push).toHaveBeenCalledWith("/analyses/101");
    });
  });

  it("does not repeat description-only resolution text in the context panel", async () => {
    vi.mocked(fetchPublicMarket).mockResolvedValue({
      ...market,
      rules_text: null,
      description: "Description-only resolution text.",
    });

    render(<MarketDetailClient polymarketId="fed-cut-june-2026" />);

    expect(await screen.findByText("Description-only resolution text.")).toBeInTheDocument();
    expect(screen.getAllByText("Description-only resolution text.")).toHaveLength(1);
    expect(screen.getByText("Resolution details are shown in the rules panel.")).toBeInTheDocument();
  });
});
