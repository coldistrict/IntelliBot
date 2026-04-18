import { cn } from "@/lib/utils";

const variantStyles = {
  neutral: "border border-black/8 bg-black/4 text-ink/78",
  yes: "border border-pine/20 bg-pine/10 text-pine",
  no: "border border-ember/18 bg-ember/10 text-ember",
  warning: "border border-[#d7ad55]/28 bg-[#d7ad55]/14 text-[#6a4c0a]",
  muted: "border border-black/8 bg-white/56 text-ink/62",
};

type BadgeProps = {
  children: React.ReactNode;
  variant?: keyof typeof variantStyles;
  className?: string;
};

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em]",
        variantStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
