type StatusCardProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function StatusCard({ eyebrow, title, description }: StatusCardProps) {
  return (
    <article className="rounded-[26px] border border-black/8 bg-white/[0.7] p-6 shadow-panel backdrop-blur">
      <p className="text-[11px] uppercase tracking-[0.22em] text-ember/78">{eyebrow}</p>
      <div className="mt-4 border-t border-black/8 pt-4">
        <h2 className="text-2xl font-semibold text-ink">{title}</h2>
        <p className="mt-3 text-sm leading-7 text-ink/66">{description}</p>
      </div>
    </article>
  );
}
