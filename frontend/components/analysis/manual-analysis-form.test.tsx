import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ManualAnalysisForm } from "@/components/analysis/manual-analysis-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("ManualAnalysisForm", () => {
  it("shows the live X intelligence toggle and compact manual setup guidance", () => {
    render(<ManualAnalysisForm />);

    expect(screen.getByRole("heading", { name: /compose the research run, then let the memo build itself/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/include live x intelligence/i)).toBeChecked();
    expect(screen.getByText(/what happens next/i)).toBeInTheDocument();
    expect(screen.getByText(/tips for stronger inputs/i)).toBeInTheDocument();
    expect(
      screen.getByText(/let grok handle live x discovery instead of hand-curating posts/i),
    ).toBeInTheDocument();
  });

  it("can fill a political manual-analysis example", () => {
    render(<ManualAnalysisForm />);

    fireEvent.click(screen.getByRole("button", { name: /democrats win control of the senate/i }));

    expect(screen.getByLabelText(/primary input/i)).toHaveValue(
      "Will Democrats win control of the Senate in the 2026 midterms?",
    );
  });
});
