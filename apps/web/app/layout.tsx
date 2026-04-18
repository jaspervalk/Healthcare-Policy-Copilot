import type { Metadata } from "next";

import "./globals.css";


export const metadata: Metadata = {
  title: "Healthcare Policy Copilot",
  description: "Phase 1 operator console for document ingestion and retrieval.",
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-[var(--font-body)] antialiased">{children}</body>
    </html>
  );
}
