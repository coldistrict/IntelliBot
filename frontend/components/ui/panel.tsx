import { cn } from "@/lib/utils";

type PanelProps = {
  children: React.ReactNode;
  className?: string;
};

export function Panel({ children, className }: PanelProps) {
  return (
    <section
      className={cn(
        "rounded-[18px] border border-black/[0.08] bg-[rgba(251,248,241,0.88)] p-6 shadow-[0_8px_24px_rgba(22,17,12,0.05)]",
        className,
      )}
    >
      {children}
    </section>
  );
}
