import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HistoryList } from "@/components/analysis/history-list";
import { AnalysisSummary, fetchAnalyses } from "@/lib/api";

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
    fetchAnalyses: vi.fn(),
  };
});

const linkedRun = {
  id: 42,
  mode: "manual",
  input_type: "market_id",
  input_text: "949495",
  market_id: 4,
  market_title: "Fed rate cut by June 2026 meeting?",
  template_requested: null,
  template_selected: "macro_policy",
  status: "complete",
  current_stage: "complete",
  error_message: null,
  started_at: "2026-06-10T04:59:04Z",
  completed_at: "2026-06-10T05:00:42Z",
  created_at: "2026-06-10T04:59:04Z",
  updated_at: "2026-06-10T05:00:42Z",
  latest_recommendation_label: "no_edge",
  latest_confidence_label: "low",
  review_count: 0,
  progress_percent: 100,
  current_stage_label: "Complete",
  current_stage_note: "Done.",
  display_summary: "Done.",
  qualitative_label: "leans_no",
} as AnalysisSummary;

describe("HistoryList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("prefers the linked market title over the raw market id", async () => {
    vi.mocked(fetchAnalyses).mockResolvedValue({ items: [linkedRun], total: 1 });

    render(<HistoryList />);

    expect(
      await screen.findByText("Fed rate cut by June 2026 meeting?"),
    ).toBeInTheDocument();
    expect(screen.queryByText("949495")).not.toBeInTheDocument();
  });

  it("shows a retryable error state, and empty copy only when truly empty", async () => {
    vi.mocked(fetchAnalyses)
      .mockRejectedValueOnce(new Error("Failed to fetch"))
      .mockResolvedValueOnce({ items: [], total: 0 });

    render(<HistoryList />);

    expect(await screen.findByText("The research log cannot be loaded")).toBeInTheDocument();
    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
    expect(screen.queryByText(/no finished runs/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => {
      expect(screen.queryByText("The research log cannot be loaded")).not.toBeInTheDocument();
    });
    expect(
      screen.getByText("Completed analyses will appear here once the desk has some history."),
    ).toBeInTheDocument();
  });
});
