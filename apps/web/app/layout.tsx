import type { Metadata } from "next";
import { Fraunces, Inter } from "next/font/google";

import { AppShell } from "@/components/shell/app-shell";

import "./globals.css";


const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  axes: ["opsz", "SOFT"],
});


export const metadata: Metadata = {
  title: "Healthcare Policy Copilot",
  description: "Grounded answers over healthcare policy documents.",
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body className="antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
