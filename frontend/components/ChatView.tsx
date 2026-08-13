"use client";

import { useEffect, useState } from "react";

import { ApprovalPanel } from "@/components/ApprovalPanel";
import { ChartRenderer } from "@/components/ChartRenderer";
import { ResultsTable } from "@/components/ResultsTable";
import { useChat } from "@/hooks/useChat";
import { fetchDatasets, reportCsvUrl, reportMarkdownUrl } from "@/lib/api";
import { EXAMPLES, SCOPE_LINE } from "@/lib/examples";
import type { Dataset } from "@/lib/types";

export function ChatView() {
  const { state, ask, respond } = useChat();
  const [question, setQuestion] = useState("");
  const [approveSql, setApproveSql] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);

  useEffect(() => {
    fetchDatasets()
      .then(setDatasets)
      .catch(() => setDatasets([]));
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    void ask(question, approveSql);
  };

  // Populate the box *and* submit: a chip that only fills the input makes the
  // visitor do the work twice, and the point is a one-click first answer.
  const runExample = (q: string) => {
    setQuestion(q);
    void ask(q, approveSql);
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">DataChat</h1>
        <p className="text-sm opacity-60">
          Ask open data in plain English — safe, grounded, verified SQL.
        </p>
      </header>

      {datasets.length > 0 && (
        <section className="flex flex-wrap gap-2 text-xs opacity-70">
          {datasets.map((d) => (
            <span key={d.name} className="rounded-full border border-white/10 px-2 py-1">
              {d.name}: {d.tables.join(", ")}
            </span>
          ))}
        </section>
      )}

      {!state.question && (
        <section aria-label="Example questions" className="flex flex-col gap-2">
          <p className="text-sm opacity-70">Try one of these:</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.question}
                type="button"
                onClick={() => runExample(ex.question)}
                disabled={state.active}
                className={`rounded-lg border p-3 text-left transition hover:bg-white/5 disabled:opacity-50 ${
                  ex.refusal ? "border-amber-400/30" : "border-white/10"
                }`}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{ex.label}</span>
                  <span className="shrink-0 text-[11px] opacity-50">{ex.hint}</span>
                </span>
                <span className="mt-1 block text-xs opacity-70">{ex.question}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-xs opacity-55">{SCOPE_LINE}</p>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Which 10 countries had the highest CO₂ per capita in 2022?"
          className="h-24 w-full rounded-lg border border-white/10 bg-black/30 p-3 text-sm"
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm opacity-80">
            <input
              type="checkbox"
              checked={approveSql}
              onChange={(e) => setApproveSql(e.target.checked)}
            />
            Review SQL before it runs
          </label>
          <button
            type="submit"
            disabled={state.active}
            className="rounded-lg bg-emerald-500/80 px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {state.active ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      <TurnView state={state} onDecision={(d) => state.awaiting && void respond(state.awaiting.run_id, d)} />
    </main>
  );
}

function TurnView({
  state,
  onDecision,
}: {
  state: ReturnType<typeof useChat>["state"];
  onDecision: Parameters<typeof ApprovalPanel>[0]["onDecision"];
}) {
  if (!state.question) {
    return <p className="text-sm opacity-50">Ask a question to get started.</p>;
  }

  return (
    <section className="flex flex-col gap-4">
      {state.waking && (
        <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm">
          Waking the server (free tier)… this can take up to a minute on the first request.
        </div>
      )}

      {state.active && !state.waking && (
        <p className="text-sm opacity-60">{stageLabel(state.stage)}</p>
      )}

      {state.sql && (
        <details className="rounded-lg border border-white/10 bg-white/5 p-3">
          <summary className="cursor-pointer text-sm">Executed SQL</summary>
          <pre className="mt-2 overflow-x-auto font-mono text-xs">{state.sql}</pre>
        </details>
      )}

      {state.awaiting && <ApprovalPanel awaiting={state.awaiting} onDecision={onDecision} />}

      {state.rows && <ResultsTable rows={state.rows} />}
      {state.chart && <ChartRenderer spec={state.chart} />}

      {state.webSources && (
        <div className="rounded-lg border border-amber-400/30 bg-amber-400/5 p-3 text-xs">
          <p className="font-medium text-amber-300/90">
            Answered from the web — not your governed datasets.
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {state.webSources.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noreferrer" className="underline opacity-80">
                  {s.title || s.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {state.explanation && <p className="text-sm leading-relaxed">{state.explanation}</p>}

      {state.done && state.rows && state.runId && (
        <div className="flex flex-wrap gap-2 text-sm">
          <a
            href={reportMarkdownUrl(state.runId)}
            download
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10"
          >
            ⬇ Download report
          </a>
          <a
            href={reportCsvUrl(state.runId)}
            download
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 hover:bg-white/10"
          >
            ⬇ Download data (CSV)
          </a>
        </div>
      )}

      {state.error && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/5 p-3 text-sm">
          {state.error.message}
        </div>
      )}
    </section>
  );
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    understanding: "Understanding your question…",
    retrieving: "Retrieving the relevant schema…",
    planning: "Planning the analysis…",
    generating: "Generating SQL…",
    validating: "Checking the query is safe…",
    executing: "Running the query…",
    verifying: "Verifying the result…",
    repairing: "Fixing the query…",
    explaining: "Explaining the answer…",
    visualizing: "Building a chart…",
  };
  return labels[stage] ?? "Working…";
}
