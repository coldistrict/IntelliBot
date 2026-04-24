import { cn } from "@/lib/utils";

type PanelProps = {
  children: React.ReactNode;
  className?: string;
};

export function Panel({ children, className }: PanelProps) {
  return (
    <section
      className={cn(
        "rounded-lg border border-black/[0.08] bg-white/90 p-6 shadow-panel backdrop-blur-sm",
        className,
      )}
    >
      {children}
    </section>
  );
}
