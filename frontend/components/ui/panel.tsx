import { cn } from "@/lib/utils";

type PanelProps = {
  children: React.ReactNode;
  className?: string;
} & React.ComponentPropsWithoutRef<"section">;

export function Panel({ children, className, ...sectionProps }: PanelProps) {
  return (
    <section
      {...sectionProps}
      className={cn(
        "min-w-0 rounded-xl border border-black/[0.08] bg-white p-6 shadow-panel",
        className,
      )}
    >
      {children}
    </section>
  );
}
