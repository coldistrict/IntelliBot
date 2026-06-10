"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Overview" },
  { href: "/markets", label: "Markets" },
  { href: "/manual", label: "Manual" },
  { href: "/history", label: "History" },
  { href: "/scoreboard", label: "Scoreboard" },
  { href: "/settings", label: "Settings" },
];

type SiteShellProps = {
  children: React.ReactNode;
};

export function SiteShell({ children }: SiteShellProps) {
  const pathname = usePathname();
  const activeHref = pathname.startsWith("/analyses")
    ? "/history"
    : pathname.startsWith("/markets")
      ? "/markets"
      : pathname;

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="z-40 border-b border-black/10 bg-canvas/85 px-4 py-3 backdrop-blur-md sm:px-6 lg:sticky lg:top-0 lg:px-8">
        <div className="mx-auto flex max-w-[94rem] flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/"
              aria-hidden="true"
              tabIndex={-1}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-pine font-serif text-lg font-medium italic leading-none text-white shadow-sm"
            >
              P
            </Link>
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <Link href="/" className="font-serif text-2xl font-medium leading-none text-ink">
                  Polymarket Copilot
                </Link>
                <span className="rounded-full border border-pine/30 bg-pine/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-pine">
                  Shadow mode
                </span>
              </div>
              <p className="mt-1 hidden text-xs font-medium text-ink/50 sm:block">
                Research desk · reads markets, never trades them
              </p>
            </div>
          </div>
          <nav className="flex flex-wrap gap-1 lg:justify-end" aria-label="Primary">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={activeHref === link.href ? "page" : undefined}
                className={cn(
                  "rounded-full px-3.5 py-2 text-sm font-semibold transition",
                  activeHref === link.href
                    ? "bg-ink text-white shadow-sm"
                    : "text-ink/60 hover:bg-white hover:text-ink hover:shadow-sm",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[94rem] flex-1 px-4 pb-16 pt-8 sm:px-6 lg:px-8">
        {children}
      </main>
      <footer className="border-t border-black/10 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[94rem] flex-wrap items-center justify-between gap-3 text-xs text-ink/50">
          <p>
            <span className="font-serif text-sm italic text-ink/60">Polymarket Copilot</span>
            {" · "}shadow-mode research desk — analysis only, no orders are ever placed.
          </p>
          <p>Manual runs · live memos · calibration scoreboard</p>
        </div>
      </footer>
    </div>
  );
}
