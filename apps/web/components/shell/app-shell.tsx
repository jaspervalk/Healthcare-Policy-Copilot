import type { ReactNode } from "react";

import { Nav } from "./nav";


export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-100 bg-surface/80 backdrop-blur sticky top-0 z-30">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <span className="font-display text-base font-semibold tracking-tight text-ink-900">
              Healthcare Policy Copilot
            </span>
            <Nav />
          </div>
          <a
            href="https://github.com/jaspervalk"
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-ink-400 hover:text-ink-700"
          >
            Jasper Valk · 2026
          </a>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
