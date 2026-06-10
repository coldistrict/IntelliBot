import { cn } from "@/lib/utils";

const variantStyles = {
  neutral: "border border-black/10 bg-black/5 text-ink/80",
  yes: "border border-pine/20 bg-pine/10 text-pine",
  no: "border border-ember/20 bg-ember/10 text-ember",
  warning: "border border-[#b9892e]/25 bg-[#f0d18a]/25 text-[#6a4c0a]",
  muted: "border border-black/10 bg-white/70 text-ink/60",
};

const dotStyles: Partial<Record<keyof typeof variantStyles, string>> = {
  yes: "bg-pine",
  no: "bg-ember",
  warning: "bg-[#b9892e]",
};

type BadgeProps = {
  children: React.ReactNode;
  variant?: keyof typeof variantStyles;
  className?: string;
};

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  const dot = dotStyles[variant];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]",
        variantStyles[variant],
        className,
      )}
    >
      {dot ? <span aria-hidden="true" className={cn("h-1.5 w-1.5 rounded-full", dot)} /> : null}
      {children}
    </span>
  );
}
