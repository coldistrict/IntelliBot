"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
import {
  fetchProviderBilling,
  ProviderBilling,
  ProviderBillingItem,
} from "@/lib/api";

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatMoney(value: number | null | undefined) {
  return value == null ? "—" : money.format(value);
}

function formatUpdated(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function badgeFor(item: ProviderBillingItem) {
  if (item.status === "error") {
    return { label: "needs attention", variant: "no" as const };
  }
  if (item.status === "setup_required") {
    return { label: "setup needed", variant: "warning" as const };
  }
  if (item.balance_type === "exact") {
    return { label: "exact balance", variant: "yes" as const };
  }
  if (item.balance_type === "estimated") {
    return { label: "estimate", variant: "neutral" as const };
  }
  return { label: "live usage", variant: "neutral" as const };
}

function BillingCard({ item }: { item: ProviderBillingItem }) {
  const badge = badgeFor(item);
  const isOpenAI = item.provider === "openai";
  const mainLabel = isOpenAI
    ? item.balance_type === "estimated"
      ? "Estimated remaining"
      : item.status === "available"
        ? "Spent this month"
        : "Billing connection"
    : item.status === "available"
      ? "Prepaid credits left"
      : "Billing connection";
  const mainValue = isOpenAI
    ? item.balance_type === "estimated"
      ? formatMoney(item.remaining_usd)
      : item.status === "available"
        ? formatMoney(item.spent_month_usd)
        : "Not connected"
    : item.status === "available"
      ? formatMoney(item.credit_balance_usd)
      : "Not connected";

  return (
    <article className="rounded-lg border border-black/8 bg-paper/70 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="section-label">{isOpenAI ? "OpenAI" : "Grok · xAI"}</p>
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">
            {mainLabel}
          </p>
          <p className="mt-1 font-serif text-4xl leading-none text-ink">{mainValue}</p>
        </div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>

      {item.status === "available" && isOpenAI ? (
        <div className="mt-5 grid grid-cols-2 gap-3 border-y border-black/8 py-4">
          <div>
            <p className="text-xs text-ink/48">Spent this month</p>
            <p className="mt-1 text-sm font-semibold text-ink">
              {formatMoney(item.spent_month_usd)}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink/48">Monthly budget</p>
            <p className="mt-1 text-sm font-semibold text-ink">
              {formatMoney(item.budget_usd)}
            </p>
          </div>
        </div>
      ) : null}

      <p className="mt-4 text-sm leading-6 text-ink/62">{item.message}</p>

      {item.setup_fields?.length ? (
        <div className="mt-4">
          <p className="text-xs font-semibold text-ink/55">Add to the root .env file</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {item.setup_fields.map((field) => (
              <code
                key={field}
                className="rounded-md border border-black/8 bg-white px-2 py-1 text-[11px] text-ink/70"
              >
                {field}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      <a
        className="mt-5 inline-flex text-xs font-semibold uppercase tracking-[0.14em] text-pine hover:underline"
        href={item.dashboard_url}
        target="_blank"
        rel="noreferrer"
      >
        Open provider billing ↗
      </a>
    </article>
  );
}

export function ProviderBillingPanel() {
  const [billing, setBilling] = useState<ProviderBilling | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force = false) => {
    if (force) {
      setRefreshing(true);
    }
    try {
      const payload = await fetchProviderBilling(force);
      setBilling(payload);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load billing details.");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [load]);

  return (
    <Panel className="p-5" aria-labelledby="billing-heading">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-black/8 pb-4">
        <div>
          <p className="section-label">API budget</p>
          <h3 id="billing-heading" className="mt-1.5 font-serif text-2xl text-ink">
            Credits and monthly spend
          </h3>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-ink/58">
            Grok reports an exact prepaid balance. OpenAI remaining funds are an estimate based on
            the monthly budget you set.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {billing ? (
            <p className="text-xs text-ink/45">Updated {formatUpdated(billing.refreshed_at)}</p>
          ) : null}
          <button
            type="button"
            className="quiet-action"
            onClick={() => void load(true)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-lg border border-ember/15 bg-ember/5 px-4 py-3 text-sm text-ember">
          {error}
        </div>
      ) : null}

      {billing ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <BillingCard item={billing.openai} />
          <BillingCard item={billing.grok} />
        </div>
      ) : !error ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {["OpenAI", "Grok · xAI"].map((label) => (
            <div key={label} className="min-h-52 animate-pulse rounded-lg bg-black/[0.035] p-5">
              <p className="section-label">{label}</p>
              <div className="mt-5 h-10 w-40 rounded bg-black/5" />
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
