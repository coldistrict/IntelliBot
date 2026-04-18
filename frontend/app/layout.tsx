import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import { SiteShell } from "@/components/site-shell";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
});

export const metadata: Metadata = {
  title: "Polymarket Copilot v1",
  description: "Shadow-mode research copilot scaffold",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${serif.variable} bg-canvas text-ink antialiased`}>
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
