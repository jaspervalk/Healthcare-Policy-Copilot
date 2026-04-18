import { PhaseOneConsole } from "../components/phase-one-console";


const foundationChecklist = [
  "FastAPI service with upload, index, list, and query endpoints",
  "Text-based PDF parsing with page preservation and metadata inference",
  "Hierarchical chunking with section-aware payloads",
  "OpenAI embeddings with local fallback for development",
  "Qdrant-backed dense retrieval ready for citation generation in Phase 2",
];

const nextMilestones = [
  "Answer generation with citations and abstention",
  "Confidence scoring from evidence quality",
  "Hybrid retrieval and version-aware ranking",
  "Evaluation harness and benchmark dataset",
];


export default function Home() {
  return (
    <main className="mx-auto min-h-screen max-w-7xl px-5 py-8 md:px-8 lg:px-10">
      <section className="overflow-hidden rounded-[36px] border border-white/70 bg-paper/75 p-8 shadow-card backdrop-blur">
        <div className="grid gap-10 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="relative">
            <div className="absolute -left-6 top-0 h-40 w-40 rounded-full bg-clay/15 blur-3xl" />
            <p className="relative text-sm font-medium uppercase tracking-[0.28em] text-clay">Healthcare Policy Copilot</p>
            <h1 className="relative mt-4 max-w-xl font-[var(--font-display)] text-5xl font-bold leading-[1.02] text-slate md:text-6xl">
              Trust-first retrieval for policy teams.
            </h1>
            <p className="relative mt-5 max-w-xl text-lg leading-8 text-slate/80">
              Phase 1 focuses on the infrastructure that matters: ingestion, parsing, chunking, embeddings, indexing,
              and inspectable retrieval results.
            </p>

            <div className="relative mt-8 grid gap-3">
              {foundationChecklist.map((item) => (
                <div
                  key={item}
                  className="flex items-start gap-3 rounded-2xl border border-slate/10 bg-white/90 px-4 py-3"
                >
                  <span className="mt-1 h-2.5 w-2.5 rounded-full bg-moss" />
                  <span className="text-sm leading-6 text-slate/85">{item}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[30px] border border-slate/10 bg-white/80 p-6">
            <div className="grid gap-4 md:grid-cols-2">
              <StatCard value="Phase 1" label="Current Build Stage" />
              <StatCard value="Dense RAG" label="Active Retrieval Mode" />
              <StatCard value="PDF -> Chunks" label="Ingest Pipeline" />
              <StatCard value="Next: Citations" label="Phase 2 Focus" />
            </div>

            <div className="mt-6 rounded-[26px] bg-slate px-5 py-5 text-white">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-white/65">Coming Next</p>
              <div className="mt-4 grid gap-3">
                {nextMilestones.map((item) => (
                  <div key={item} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-8 bg-grid bg-[size:26px_26px]">
        <PhaseOneConsole />
      </section>
    </main>
  );
}


function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <article className="rounded-[24px] border border-slate/10 bg-sand/70 p-5">
      <p className="font-[var(--font-display)] text-2xl font-bold text-slate">{value}</p>
      <p className="mt-2 text-sm uppercase tracking-[0.18em] text-slate/60">{label}</p>
    </article>
  );
}
