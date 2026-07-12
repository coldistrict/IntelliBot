import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeskLaunchpad } from "@/components/home/desk-launchpad";
import { AnalysisSummary, fetchAnalyses, fetchProviderStatus } from "@/lib/api";

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
    fetchProviderStatus: vi.fn(),
  };
});

const providerStatus = {
  openai_configured: true,
  grok_configured: true,
  search_configured: true,
  fred_configured: false,
  premium_session_available: false,
};

function summary(id: number, status: string, marketTitle: string | null): AnalysisSummary {
  return {
    id,
    mode: "manual",
    input_type: marketTitle ? "market_id" : "custom_claim",
    input_text: marketTitle ? String(900000 + id) : `Claim ${id}`,
    market_id: marketTitle ? id : null,
    market_title: marketTitle,
    template_requested: null,
    template_selected: "macro_policy",
    status,
    current_stage: status,
    error_message: null,
    started_at: "2026-06-10T04:59:04Z",
    completed_at: status === "complete" ? "2026-06-10T05:00:42Z" : null,
    created_at: "2026-06-10T04:59:04Z",
    updated_at: "2026-06-10T05:00:42Z",
    latest_recommendation_label: null,
    latest_confidence_label: null,
    review_count: 0,
    progress_percent: status === "complete" ? 100 : 40,
    current_stage_label: status,
    current_stage_note: "Note.",
    display_summary: "Summary.",
    qualitative_label: null,
  } as AnalysisSummary;
}

describe("DeskLaunchpad", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows true counts and readable market titles, not capped slices or raw IDs", async () => {
    const finished = Array.from({ length: 7 }, (_, index) =>
      summary(index + 1, "complete", index === 0 ? "Fed rate cut by June 2026 meeting?" : null),
    );
    vi.mocked(fetchAnalyses).mockResolvedValue({ items: finished, total: finished.length });
    vi.mocked(fetchProviderStatus).mockResolvedValue(providerStatus);

    render(<DeskLaunchpad />);

    expect(await screen.findByText("Fed rate cut by June 2026 meeting?")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("900001")).not.toBeInTheDocument();
    expect(screen.getByText("Completed or failed runs")).toBeInTheDocument();
  });

  it("shows a retryable error state instead of healthy zeros when the backend is down", async () => {
    vi.mocked(fetchAnalyses)
      .mockRejectedValueOnce(new Error("Failed to fetch"))
      .mockResolvedValueOnce({ items: [], total: 0 });
    vi.mocked(fetchProviderStatus)
      .mockRejectedValueOnce(new Error("Failed to fetch"))
      .mockResolvedValueOnce(providerStatus);

    render(<DeskLaunchpad />);

    expect(await screen.findByText("The desk cannot reach the backend")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("No active analyses right now. Start one from Manual Analysis.")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Try again" })[0]);

    await waitFor(() => {
      expect(screen.queryByText("The desk cannot reach the backend")).not.toBeInTheDocument();
    });
    expect(
      screen.getByText("No active analyses right now. Start one from Manual Analysis."),
    ).toBeInTheDocument();
  });
});
