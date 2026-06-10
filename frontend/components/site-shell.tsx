"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Overview" },
  { href: "/markets", label: "Markets" },
  { href: "/manual", label: "Manual" },
  { href: "/history", label: "History" },
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
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-40 border-b border-black/10 bg-canvas px-4 py-3 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-[94rem] flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="eyebrow">
              Shadow-Mode Research Desk
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-3">
              <Link href="/" className="font-serif text-2xl leading-none text-ink">
                Polymarket Copilot
              </Link>
              <span className="rounded-md border border-black/8 bg-white/70 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink/52">
                Manual mode first
              </span>
            </div>
          </div>
          <nav className="flex flex-wrap gap-1.5 lg:justify-end" aria-label="Primary">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-md border px-3 py-2 text-sm font-semibold transition",
                  activeHref === link.href
                    ? "border-ink bg-ink text-white"
                    : "border-transparent text-ink/64 hover:border-black/10 hover:bg-white/80 hover:text-ink",
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[94rem] px-4 pb-10 pt-6 sm:px-6 lg:px-8">{children}</main>
    </div>
  );
}
