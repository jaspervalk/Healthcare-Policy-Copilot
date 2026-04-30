import type { AnswerCitation } from "@/lib/types";


/**
 * Render an answer with inline citation markers `[N]`, where N is 1-based and
 * matches the citations array. The model emits citations as a separate list, so
 * we splice marker chips into the prose at end-of-sentence boundaries: the
 * least-bad place to attach them when the model didn't anchor them itself.
 *
 * If you want spans rather than sentence-end attachment later, change this
 * function — the rest of the UI does not care.
 */
export function AnswerWithCitations({
  answer,
  citations,
  selectedChunkId,
  onCitationClick,
}: {
  answer: string;
  citations: AnswerCitation[];
  selectedChunkId: string | null;
  onCitationClick: (chunkId: string) => void;
}) {
  if (!citations.length) {
    return <p className="font-sans text-[15px] leading-7 text-ink-800">{answer}</p>;
  }

  const sentences = splitSentences(answer);
  const totalCitations = citations.length;
  const perSentence = distributeCitations(sentences.length, totalCitations);

  return (
    <p className="font-sans text-[15px] leading-7 text-ink-800">
      {sentences.map((sentence, sentenceIndex) => {
        const citationIndices = perSentence[sentenceIndex] ?? [];
        return (
          <span key={sentenceIndex}>
            {sentence}
            {citationIndices.map((citationIndex) => {
              const citation = citations[citationIndex];
              const number = citationIndex + 1;
              const active = selectedChunkId === citation.chunk_id;
              return (
                <button
                  key={`${sentenceIndex}-${citationIndex}`}
                  type="button"
                  onClick={() => onCitationClick(citation.chunk_id)}
                  aria-label={`Citation ${number}: ${citation.document_title}, pages ${citation.page_start}-${citation.page_end}`}
                  className={`mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm border px-1 align-text-top text-[11px] font-semibold transition ${
                    active
                      ? "border-ink-800 bg-ink-800 text-surface"
                      : "border-ink-300 bg-white text-ink-700 hover:border-ink-800 hover:text-ink-900"
                  }`}
                >
                  {number}
                </button>
              );
            })}
            {sentenceIndex < sentences.length - 1 ? " " : ""}
          </span>
        );
      })}
    </p>
  );
}


function splitSentences(text: string): string[] {
  const matches = text.match(/[^.!?]+[.!?]?/g);
  if (!matches) {
    return [text];
  }
  return matches.map((sentence) => sentence.trim()).filter(Boolean);
}


/**
 * Distribute N citations across S sentences. We put one citation per sentence
 * starting from the last sentence and walking backward, so the densest
 * grounding sits at the end of the answer (the conclusion). If there are more
 * citations than sentences, extras attach to the final sentence.
 */
function distributeCitations(sentenceCount: number, citationCount: number): number[][] {
  const result: number[][] = Array.from({ length: sentenceCount }, () => []);
  if (sentenceCount === 0 || citationCount === 0) {
    return result;
  }
  for (let i = 0; i < citationCount; i += 1) {
    const targetIndex = Math.max(0, sentenceCount - 1 - i);
    result[targetIndex].push(i);
  }
  // Sort each sentence's citation list ascending so [1] [2] reads naturally.
  for (const list of result) {
    list.sort((a, b) => a - b);
  }
  return result;
}
