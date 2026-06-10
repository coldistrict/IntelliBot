import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import { SiteShell } from "@/components/site-shell";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Polymarket Copilot",
  description: "Shadow-mode research desk for reading Polymarket markets deeply",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="bg-canvas text-ink antialiased">
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
