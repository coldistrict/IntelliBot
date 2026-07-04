import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ManualAnalysisForm } from "@/components/analysis/manual-analysis-form";
import { createManualAnalysis } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    createManualAnalysis: vi.fn(),
  };
});

describe("ManualAnalysisForm", () => {
  it("shows the live X intelligence toggle and compact manual setup guidance", () => {
    render(<ManualAnalysisForm />);

    expect(screen.getByRole("heading", { name: /compose the research run, then let the memo build itself/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/include live x intelligence/i)).toBeChecked();
    expect(screen.getAllByText(/what happens next/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tips for stronger inputs/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/let grok handle live x discovery instead of hand-curating posts/i),
    ).toBeInTheDocument();
  });

  it("keeps the explanatory copy behind a disclosure and preserves defaults", () => {
    render(<ManualAnalysisForm />);

    const disclosure = screen
      .getByText(/what happens next & tips for stronger inputs/i)
      .closest("details");
    expect(disclosure).not.toBeNull();
    expect(disclosure).not.toHaveAttribute("open");

    expect(screen.getByLabelText(/include live x intelligence/i)).toBeChecked();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[1]).not.toBeChecked();

    expect(screen.getByRole("button", { name: /run manual analysis/i })).toBeInTheDocument();
  });

  it("can fill a political manual-analysis example", () => {
    render(<ManualAnalysisForm />);

    fireEvent.click(screen.getByRole("button", { name: /democrats win control of the senate/i }));

    expect(screen.getByLabelText(/primary input/i)).toHaveValue(
      "Will Democrats win control of the Senate in the 2026 midterms?",
    );
  });

  it("surfaces submission errors as an alert next to the submit action", async () => {
    vi.mocked(createManualAnalysis).mockRejectedValue(new Error("Backend rejected the claim."));

    render(<ManualAnalysisForm />);

    fireEvent.change(screen.getByLabelText(/primary input/i), {
      target: { value: "Will the Fed cut rates by June?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run manual analysis/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Backend rejected the claim.");
  });
});
