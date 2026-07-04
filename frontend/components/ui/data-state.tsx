import { cn } from "@/lib/utils";

type DataStateProps = {
  variant: "loading" | "error" | "empty";
  title?: string;
  note: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: React.ReactNode;
  className?: string;
};

export function DataState({
  variant,
  title,
  note,
  onRetry,
  retryLabel = "Try again",
  action,
  className,
}: DataStateProps) {
  if (variant === "loading") {
    return (
      <div className={cn("py-5", className)} role="status" aria-live="polite">
        {title ? <p className="text-sm font-semibold text-ink">{title}</p> : null}
        <p className={cn("text-sm leading-6 text-ink/60", title && "mt-1")}>{note}</p>
        <div className="mt-4 space-y-2 animate-pulse" aria-hidden="true">
          <div className="h-2.5 w-3/4 rounded-full bg-black/5" />
          <div className="h-2.5 w-5/6 rounded-full bg-black/5" />
          <div className="h-2.5 w-2/3 rounded-full bg-black/5" />
        </div>
      </div>
    );
  }

  if (variant === "error") {
    return (
      <div
        className={cn(
          "rounded-lg border border-ember/20 bg-ember/10 px-5 py-4",
          className,
        )}
        role="alert"
      >
        <p className="text-sm font-semibold text-ember">
          {title ?? "Something went wrong"}
        </p>
        <p className="mt-1 text-sm leading-6 text-ember/90">{note}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry} className="secondary-action mt-3">
            {retryLabel}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className={cn("py-5", className)}>
      {title ? <p className="text-sm font-semibold text-ink">{title}</p> : null}
      <p className={cn("text-sm leading-7 text-ink/60", title && "mt-1")}>{note}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
