import { PhaseOneConsole } from "../components/phase-one-console";


const capabilityPills = [
  "Healthcare document ingestion",
  "Auto indexing into vector search",
  "Grounded answer generation",
  "Inspectable citation evidence",
  "Corpus operations dashboard",
];

const statusCards = [
  { value: "Answer-First", label: "Workspace Priority" },
  { value: "Dense Retrieval", label: "Retrieval Mode" },
  { value: "Corpus Ops", label: "Library Surface" },
];


export default function Home() {
  return (
    <main className="mx-auto min-h-screen max-w-[1560px] px-5 py-6 md:px-7 lg:px-8">
      <section className="overflow-hidden rounded-[34px] border border-white/70 bg-paper/80 p-6 shadow-card backdrop-blur md:p-7">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-4xl">
            <p className="text-sm font-medium uppercase tracking-[0.28em] text-clay">Healthcare Policy Copilot</p>
            <h1 className="mt-4 font-[var(--font-display)] text-4xl font-bold leading-[1.04] text-slate md:text-5xl">
              A grounded document workspace for healthcare policy teams.
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-8 text-slate/78">
              Ask evidence-backed questions against the indexed corpus, then manage the source set with the same level of
              operational clarity you would expect from a real internal product.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {statusCards.map((card) => (
              <article key={card.label} className="rounded-[24px] border border-slate/10 bg-white/90 px-5 py-4">
                <p className="font-[var(--font-display)] text-2xl font-bold text-slate">{card.value}</p>
                <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate/58">{card.label}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {capabilityPills.map((pill) => (
            <span
              key={pill}
              className="rounded-full border border-slate/10 bg-white/80 px-4 py-2 text-sm font-semibold text-slate/78"
            >
              {pill}
            </span>
          ))}
        </div>
      </section>

      <section className="mt-6 bg-grid bg-[size:26px_26px]">
        <PhaseOneConsole />
      </section>
    </main>
  );
}
