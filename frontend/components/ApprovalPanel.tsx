"use client";

import { useState } from "react";

import type { AwaitingApprovalEvent, Decision } from "@/lib/types";

interface Props {
  awaiting: AwaitingApprovalEvent;
  onDecision: (decision: { decision?: Decision; edited_sql?: string; clarification?: string }) => void;
}

export function ApprovalPanel({ awaiting, onDecision }: Props) {
  if (awaiting.kind === "clarify") {
    return <ClarifyPanel awaiting={awaiting} onDecision={onDecision} />;
  }
  return <ApproveSqlPanel awaiting={awaiting} onDecision={onDecision} />;
}

function ApproveSqlPanel({ awaiting, onDecision }: Props) {
  const [editing, setEditing] = useState(false);
  const [sql, setSql] = useState(awaiting.sql ?? "");

  return (
    <div className="rounded-lg border border-amber-400/30 bg-amber-400/5 p-4">
      <p className="mb-2 text-sm font-medium">Approve this query before it runs</p>
      {editing ? (
        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          className="mb-3 h-28 w-full rounded border border-white/10 bg-black/30 p-2 font-mono text-xs"
        />
      ) : (
        <pre className="mb-3 overflow-x-auto rounded bg-black/30 p-2 font-mono text-xs">
          {awaiting.sql}
        </pre>
      )}
      <div className="flex flex-wrap gap-2">
        {editing ? (
          <button
            className="rounded bg-emerald-500/80 px-3 py-1.5 text-sm"
            onClick={() => onDecision({ decision: "edit", edited_sql: sql })}
          >
            Run edited SQL
          </button>
        ) : (
          <>
            <button
              className="rounded bg-emerald-500/80 px-3 py-1.5 text-sm"
              onClick={() => onDecision({ decision: "approve" })}
            >
              Approve &amp; run
            </button>
            <button
              className="rounded bg-white/10 px-3 py-1.5 text-sm"
              onClick={() => setEditing(true)}
            >
              Edit
            </button>
          </>
        )}
        <button
          className="rounded bg-white/10 px-3 py-1.5 text-sm"
          onClick={() => onDecision({ decision: "reject" })}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

function ClarifyPanel({ awaiting, onDecision }: Props) {
  return (
    <div className="rounded-lg border border-sky-400/30 bg-sky-400/5 p-4">
      <p className="mb-2 text-sm font-medium">Which did you mean?</p>
      <div className="flex flex-wrap gap-2">
        {awaiting.options.map((option) => (
          <button
            key={option}
            className="rounded bg-white/10 px-3 py-1.5 text-sm"
            onClick={() => onDecision({ clarification: option })}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
