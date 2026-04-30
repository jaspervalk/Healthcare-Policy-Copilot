"use client";

import { FormEvent, KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import type { QueryFilters, RetrievalMode } from "@/lib/types";


type FilterKey = keyof QueryFilters;


export function Composer({
  question,
  onQuestionChange,
  filters,
  onFiltersChange,
  retrievalMode,
  onRetrievalModeChange,
  onSubmit,
  isSubmitting,
  disabled,
  filterOptions,
}: {
  question: string;
  onQuestionChange: (value: string) => void;
  filters: QueryFilters;
  onFiltersChange: (filters: QueryFilters) => void;
  retrievalMode: RetrievalMode;
  onRetrievalModeChange: (mode: RetrievalMode) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
  disabled: boolean;
  filterOptions: Record<FilterKey, string[]>;
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      onSubmit();
    }
  }

  function setFilter(key: FilterKey, value: string) {
    const next = { ...filters };
    if (value === "") {
      delete next[key];
    } else {
      next[key] = value;
    }
    onFiltersChange(next);
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-ink-100 bg-white shadow-soft">
      <textarea
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a grounded question — e.g. What is the urgent prior authorization escalation process?"
        rows={3}
        className="block w-full resize-none border-0 bg-transparent px-4 pt-4 pb-2 text-[15px] leading-6 text-ink-800 placeholder:text-ink-400 focus:outline-none focus:ring-0"
      />
      <div className="flex flex-wrap items-center gap-2 border-t border-ink-100 px-3 py-2">
        <FilterChip
          label="Department"
          value={filters.department ?? ""}
          options={filterOptions.department ?? []}
          onChange={(value) => setFilter("department", value)}
        />
        <FilterChip
          label="Type"
          value={filters.document_type ?? ""}
          options={filterOptions.document_type ?? []}
          onChange={(value) => setFilter("document_type", value)}
        />
        <FilterChip
          label="Status"
          value={filters.policy_status ?? ""}
          options={filterOptions.policy_status ?? []}
          onChange={(value) => setFilter("policy_status", value)}
        />
        <ModeToggle value={retrievalMode} onChange={onRetrievalModeChange} />
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-xs text-ink-400 md:inline">⌘ + Enter</span>
          <Button type="submit" disabled={disabled || isSubmitting} size="md">
            {isSubmitting ? "Generating…" : "Ask"}
          </Button>
        </div>
      </div>
    </form>
  );
}


function FilterChip({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const active = value !== "";
  return (
    <label
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${
        active ? "border-ink-800 bg-ink-50 text-ink-900" : "border-ink-200 bg-white text-ink-600 hover:border-ink-300"
      }`}
    >
      <span className="font-medium">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="border-0 bg-transparent pr-1 text-xs focus:outline-none focus:ring-0"
      >
        <option value="">any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}


function ModeToggle({
  value,
  onChange,
}: {
  value: RetrievalMode;
  onChange: (mode: RetrievalMode) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-ink-200 p-0.5">
      {(["hybrid", "dense"] as RetrievalMode[]).map((mode) => (
        <button
          key={mode}
          type="button"
          onClick={() => onChange(mode)}
          aria-pressed={value === mode}
          className={`rounded-sm px-2 py-0.5 text-xs font-medium transition ${
            value === mode ? "bg-ink-800 text-surface" : "text-ink-500 hover:text-ink-800"
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  );
}
