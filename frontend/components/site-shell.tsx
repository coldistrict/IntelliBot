"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Overview" },
  { href: "/manual", label: "Manual Analysis" },
  { href: "/history", label: "History" },
  { href: "/settings", label: "Settings" },
];

type SiteShellProps = {
  children: React.ReactNode;
};

export function SiteShell({ children }: SiteShellProps) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-[94rem] flex-col px-5 pb-10 sm:px-7 lg:px-10">
        <header className="sticky top-0 z-40 -mx-5 border-b border-black/8 bg-[rgba(246,240,230,0.9)] px-5 py-4 backdrop-blur-sm sm:-mx-7 sm:px-7 lg:-mx-10 lg:px-10">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-[0.28em] text-ember/76">
                Shadow-Mode Research Desk
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <Link href="/" className="font-serif text-2xl leading-none text-ink sm:text-3xl">
                  Polymarket Copilot
                </Link>
                <span className="text-[10px] uppercase tracking-[0.18em] text-ink/44">
                  Manual mode first
                </span>
              </div>
            </div>
            <nav className="flex flex-wrap gap-2 lg:justify-end">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition",
                    pathname === link.href
                      ? "border-ink bg-ink text-white"
                      : "border-black/10 bg-white/60 text-ink hover:border-black/18 hover:bg-white/90",
                  )}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1 pt-8">{children}</main>
      </div>
    </div>
  );
}
