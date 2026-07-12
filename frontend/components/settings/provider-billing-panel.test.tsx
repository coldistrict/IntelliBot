import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProviderBillingPanel } from "@/components/settings/provider-billing-panel";
import { fetchProviderBilling } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchProviderBilling: vi.fn(),
}));

const billingPayload = {
  refreshed_at: "2026-07-12T16:00:00Z",
  openai: {
    provider: "openai" as const,
    status: "available" as const,
    balance_type: "estimated" as const,
    currency: "USD" as const,
    credit_balance_usd: null,
    spent_month_usd: 13,
    budget_usd: 100,
    remaining_usd: 87,
    message: "Estimated from your monthly budget minus OpenAI costs this month.",
    setup_fields: [],
    dashboard_url: "https://platform.openai.com/usage",
    as_of: "2026-07-12T16:00:00Z",
  },
  grok: {
    provider: "grok" as const,
    status: "available" as const,
    balance_type: "exact" as const,
    currency: "USD" as const,
    credit_balance_usd: 42.5,
    spent_month_usd: null,
    budget_usd: null,
    remaining_usd: null,
    message: "Exact prepaid credit balance reported by xAI.",
    setup_fields: [],
    dashboard_url: "https://console.x.ai/team/default/billing",
    as_of: "2026-07-12T16:00:00Z",
  },
};

describe("ProviderBillingPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchProviderBilling).mockReset();
    vi.mocked(fetchProviderBilling).mockResolvedValue(billingPayload);
  });

  it("distinguishes OpenAI's estimate from Grok's exact balance", async () => {
    render(<ProviderBillingPanel />);

    expect(await screen.findByText("$87.00")).toBeInTheDocument();
    expect(screen.getByText("$42.50")).toBeInTheDocument();
    expect(screen.getByText("estimate")).toBeInTheDocument();
    expect(screen.getByText("exact balance")).toBeInTheDocument();
    expect(screen.getByText("$13.00")).toBeInTheDocument();
    expect(screen.getByText("$100.00")).toBeInTheDocument();
  });

  it("forces a provider refresh from the refresh control", async () => {
    render(<ProviderBillingPanel />);
    await screen.findByText("$87.00");

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(fetchProviderBilling).toHaveBeenLastCalledWith(true));
  });
});
