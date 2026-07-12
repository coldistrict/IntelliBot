import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScoreboardClient } from "@/components/calibration/scoreboard-client";
import {
  CalibrationScoreboard,
  fetchCalibrationScoreboard,
  refreshCalibrationOutcomes,
} from "@/lib/api";

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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchCalibrationScoreboard: vi.fn(),
    refreshCalibrationOutcomes: vi.fn(),
  };
});

const emptyScoreboard: CalibrationScoreboard = {
  summary: {
    resolved_runs: 0,
    pending_runs: 0,
    unlinked_runs: 0,
    scored_runs: 0,
    avg_model_brier: null,
    avg_market_brier: null,
    head_to_head_runs: 0,
    head_to_head_model_brier: null,
    head_to_head_market_brier: null,
    model_beats_market_rate: null,
    direction_calls: 0,
    direction_hit_rate: null,
    trade_count: 0,
    trade_wins: 0,
    total_pnl: 0,
    roi_per_trade: null,
  },
  buckets: [],
  template_slices: [],
  confidence_slices: [],
  resolved: [],
  pending: [],
};

const populatedScoreboard: CalibrationScoreboard = {
  ...emptyScoreboard,
  summary: {
    ...emptyScoreboard.summary,
    resolved_runs: 2,
    scored_runs: 2,
    avg_model_brier: 0.2,
    avg_market_brier: 0.2263,
    head_to_head_runs: 2,
    head_to_head_model_brier: 0.2,
    head_to_head_market_brier: 0.2263,
    model_beats_market_rate: 0.5,
    direction_calls: 2,
    direction_hit_rate: 0.5,
    trade_count: 2,
    trade_wins: 1,
    total_pnl: 0,
    roi_per_trade: 0,
  },
  buckets: [
    {
      label: "60-80%",
      lower: 0.6,
      upper: 0.8,
      count: 1,
      avg_p_hat: 0.6,
      actual_yes_rate: 0,
    },
  ],
  template_slices: [
    {
      key: "official_event",
      resolved_runs: 1,
      avg_model_brier: 0.04,
      direction_hit_rate: 1,
      trades: 1,
      total_pnl: 100,
    },
  ],
  confidence_slices: [
    {
      key: "medium",
      resolved_runs: 2,
      avg_model_brier: 0.2,
      direction_hit_rate: 0.5,
      trades: 2,
      total_pnl: 0,
    },
  ],
  resolved: [
    {
      analysis_request_id: 11,
      analysis_run_id: 21,
      title: "Won market",
      template: "official_event",
      recommendation_label: "lean_yes",
      confidence_label: "medium",
      p_hat: 0.8,
      market_mid_prob: 0.5,
      outcome: "yes",
      resolved_at: "2026-06-01T00:00:00Z",
      model_brier: 0.04,
      market_brier: 0.25,
      direction_hit: true,
      trade_side: "yes",
      trade_entry_price: 0.5,
      trade_pnl: 100,
    },
  ],
  pending: [
    {
      analysis_request_id: 12,
      analysis_run_id: 22,
      title: "Pending market",
      p_hat: 0.55,
      recommendation_label: "no_edge",
      market_expiry_at: "2026-08-01T00:00:00Z",
    },
  ],
};

describe("ScoreboardClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when nothing has resolved", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue(emptyScoreboard);

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("No resolved markets yet")).toBeInTheDocument();
    });
  });

  it("renders summary stats, tables, and pending runs", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue(populatedScoreboard);

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("Won market")).toBeInTheDocument();
    });

    expect(screen.getByText("Every scored call")).toBeInTheDocument();
    expect(
      screen.getByText("Too few runs to judge — 2 of 5 head-to-head runs needed"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Model is beating the market price/)).not.toBeInTheDocument();
    expect(screen.getByText("YES @ 50%")).toBeInTheDocument();
    expect(screen.getByText("Pending market")).toBeInTheDocument();
    expect(screen.getByText("Won market").closest("a")).toHaveAttribute("href", "/analyses/11");
  });

  it("declares a verdict only with enough head-to-head runs and a real delta", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue({
      ...populatedScoreboard,
      summary: {
        ...populatedScoreboard.summary,
        head_to_head_runs: 6,
        head_to_head_model_brier: 0.18,
        head_to_head_market_brier: 0.24,
      },
    });

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(
        screen.getByText("Model is beating the market price across 6 runs"),
      ).toBeInTheDocument();
    });
  });

  it("uses dead-even copy inside the Brier delta dead band", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue({
      ...populatedScoreboard,
      summary: {
        ...populatedScoreboard.summary,
        head_to_head_runs: 6,
        head_to_head_model_brier: 0.2,
        head_to_head_market_brier: 0.205,
      },
    });

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("Dead even with the market across 6 runs")).toBeInTheDocument();
    });
  });

  it("explains unscoreable runs and routes toward linked markets", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue({
      ...populatedScoreboard,
      summary: { ...populatedScoreboard.summary, unlinked_runs: 37 },
    });

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("37 runs can never be scored")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Browse markets" })).toHaveAttribute(
      "href",
      "/markets",
    );
  });

  it("shows a retryable error state instead of a dead end", async () => {
    vi.mocked(fetchCalibrationScoreboard)
      .mockRejectedValueOnce(new Error("Failed to fetch"))
      .mockResolvedValueOnce(populatedScoreboard);

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("The scoreboard cannot be loaded")).toBeInTheDocument();
    });
    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => {
      expect(screen.getByText("Won market")).toBeInTheDocument();
    });
  });

  it("refreshes outcomes and reloads the scoreboard", async () => {
    vi.mocked(fetchCalibrationScoreboard).mockResolvedValue(emptyScoreboard);
    vi.mocked(refreshCalibrationOutcomes).mockResolvedValue({
      markets_checked: 3,
      newly_resolved: 1,
      still_open: 2,
      lookup_failures: 0,
    });

    render(<ScoreboardClient />);

    await waitFor(() => {
      expect(screen.getByText("No resolved markets yet")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Check for resolutions" }));

    await waitFor(() => {
      expect(
        screen.getByText("3 market(s) checked · 1 newly resolved · 2 still open"),
      ).toBeInTheDocument();
    });
    expect(refreshCalibrationOutcomes).toHaveBeenCalledTimes(1);
    expect(fetchCalibrationScoreboard).toHaveBeenCalledTimes(2);
  });
});
