import { HighChanceReturn, ReturnSettings } from "@/components/markets/high-chance-return";
import { formatCurrency, formatPercent } from "@/components/markets/market-format";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function HighChanceReturnCard({
  result,
  settings,
  compact = false,
}: {
  result: HighChanceReturn;
  settings: ReturnSettings;
  compact?: boolean;
}) {
  if (!result.qualifies) {
    return (
      <section
        aria-label="Higher-chance return check"
        className="rounded-lg border border-black/8 bg-black/[0.02] p-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Badge variant="muted">Below return rule</Badge>
          {result.side && result.impliedProbability !== null ? (
            <span className="text-xs font-semibold text-ink/52">
              Closest: {result.side.toUpperCase()} {formatPercent(result.impliedProbability)}
            </span>
          ) : null}
        </div>
        {!compact ? <p className="mt-2 text-xs leading-5 text-ink/58">{result.reason}</p> : null}
      </section>
    );
  }

  return (
    <section
      aria-label="Higher-chance return check"
      className="rounded-lg border border-[#b9892e]/30 bg-[#f0d18a]/15 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant="warning">Higher-chance return</Badge>
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#6a4c0a]">
          Market-implied · not verified
        </span>
      </div>
      <p className={cn("mt-3 font-serif text-ink", compact ? "text-xl" : "text-3xl")}>
        {result.side?.toUpperCase()} · {formatPercent(result.impliedProbability)} implied
      </p>
      <div className={cn("mt-3 grid gap-3", compact ? "grid-cols-2" : "sm:grid-cols-4")}>
        <div>
          <p className="section-label">Est. profit if correct</p>
          <p className="mt-1 font-semibold text-pine">
            {formatCurrency(result.bufferedProfitIfCorrect)}
          </p>
        </div>
        <div>
          <p className="section-label">Maximum loss</p>
          <p className="mt-1 font-semibold text-ember">{formatCurrency(result.maximumLoss)}</p>
        </div>
        {!compact ? (
          <>
            <div>
              <p className="section-label">Buy price</p>
              <p className="mt-1 font-semibold text-ink">{formatPercent(result.executionPrice)}</p>
            </div>
            <div>
              <p className="section-label">Settings</p>
              <p className="mt-1 font-semibold text-ink">
                {formatCurrency(settings.stake)} · {(settings.minimumProbability * 100).toFixed(0)}%+
              </p>
            </div>
          </>
        ) : null}
      </div>
      <p className="mt-3 text-xs leading-5 text-ink/58">
        Includes a 1% execution allowance. Fees, slippage, and price movement can reduce the return;
        an incorrect outcome can lose the full stake.
      </p>
    </section>
  );
}
