import type { AnswerResult } from "@/lib/types";


/**
 * Replaces the answer card's normal prose render when the model abstained.
 * Surfaces the model's stated reason (when present) so the user understands
 * *why* the system refused — empty answer text + a small badge looks like a bug.
 */
export function AbstainNotice({ result }: { result: AnswerResult }) {
  const reason = result.answer?.trim();
  const fallbackReason =
    result.confidence_reasons[0] ||
    "No retrieved evidence was strong enough to ground a confident answer.";

  return (
    <div
      role="status"
      className="rounded-md border border-amber-200 bg-amber-50 p-4"
    >
      <div className="flex items-start gap-3">
        <svg
          aria-hidden
          viewBox="0 0 20 20"
          className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            clipRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.346 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 0 1 .75.75v3.5a.75.75 0 1 1-1.5 0v-3.5A.75.75 0 0 1 10 6zm0 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"
          />
        </svg>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-amber-900">
            Abstained — evidence was not sufficient to answer
          </p>
          <p className="mt-1 text-sm leading-6 text-amber-900/85">
            {reason || fallbackReason}
          </p>
          <p className="mt-2 text-xs text-amber-800/70">
            Try rephrasing, broadening filters, or check the Library to confirm the relevant policy is indexed.
          </p>
        </div>
      </div>
    </div>
  );
}
