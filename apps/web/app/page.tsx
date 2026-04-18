import { PhaseOneConsole } from "../components/phase-one-console";

const capabilityPills = [
  "Grounded answers with citations",
  "Healthcare document ingestion",
  "Inspectable evidence review",
  "Corpus operations dashboard",
];

const statusCards = [
  { value: "Answer-First", label: "Primary Workflow" },
  { value: "Dense Retrieval", label: "Search Layer" },
  { value: "Corpus Control", label: "Admin Surface" },
];

export default function Home() {
  return (
    <main className="mx-auto min-h-screen max-w-[1580px] px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
      <section className="overflow-hidden rounded-[32px] border border-white/80 bg-paper/90 shadow-card backdrop-blur">
        <div className="border-b border-slate/10 px-5 py-4 md:px-7">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <span className="rounded-full bg-slate px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">
                Healthcare Policy Copilot
              </span>
              <span className="rounded-full border border-slate/10 bg-white/80 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate/65">
                Healthcare RAG Workspace
              </span>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate/45">
              Built by Jasper Valk · 2026
            </p>
          </div>
        </div>

        <div className="px-5 py-7 md:px-7 md:py-8">
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr] xl:items-end">
            <div className="max-w-4xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-clay">Grounded Answers, Operational Corpus Control</p>
              <h1 className="mt-4 [font-family:var(--font-display)] text-[clamp(2.5rem,5vw,4.5rem)] font-bold leading-[0.98] text-slate">
                A calm workspace for asking policy questions and managing the source corpus behind them.
              </h1>
              <p className="mt-4 max-w-3xl text-base leading-8 text-slate/75">
                Ask evidence-backed questions against the indexed document set, review the exact supporting excerpts, and
                keep the healthcare policy corpus current without leaving the same interface.
              </p>

              <div className="mt-6 flex flex-wrap gap-2">
                {capabilityPills.map((pill) => (
                  <span
                    key={pill}
                    className="rounded-full border border-slate/10 bg-white/85 px-4 py-2 text-sm font-semibold text-slate/75"
                  >
                    {pill}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              {statusCards.map((card) => (
                <article key={card.label} className="rounded-[24px] border border-slate/10 bg-white/92 px-5 py-4">
                  <p className="[font-family:var(--font-display)] text-[1.65rem] font-bold leading-none text-slate">
                    {card.value}
                  </p>
                  <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate/55">{card.label}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 bg-grid bg-[size:26px_26px]">
        <PhaseOneConsole />
      </section>
    </main>
  );
}
