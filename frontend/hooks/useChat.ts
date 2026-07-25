"use client";

import { useCallback, useRef, useState } from "react";

import { resumeChat, streamChat } from "@/lib/api";
import type { AgentEvent, AwaitingApprovalEvent, Decision, RowsEvent } from "@/lib/types";

export interface TurnState {
  active: boolean;
  waking: boolean;
  done: boolean;
  question: string;
  stage: string;
  plan: { steps: string[]; targetTables: string[] } | null;
  sql: string | null;
  rows: RowsEvent | null;
  explanation: string;
  chart: Record<string, unknown> | null;
  webSources: { title: string; url: string }[] | null;
  awaiting: AwaitingApprovalEvent | null;
  error: { code: string; message: string } | null;
  runId: string | null;
}

const INITIAL: TurnState = {
  active: false,
  waking: false,
  done: false,
  question: "",
  stage: "",
  plan: null,
  sql: null,
  rows: null,
  explanation: "",
  chart: null,
  webSources: null,
  awaiting: null,
  error: null,
  runId: null,
};

function reduce(state: TurnState, event: AgentEvent): TurnState {
  const base = { ...state, waking: false };
  switch (event.type) {
    case "status":
      return { ...base, stage: event.stage, waking: event.stage === "waking" };
    case "plan":
      return { ...base, plan: { steps: event.steps, targetTables: event.target_tables } };
    case "sql":
      return { ...base, sql: event.sql };
    case "rows":
      return { ...base, rows: event };
    case "explanation_delta":
      return { ...base, explanation: state.explanation + event.text };
    case "chart_spec":
      return { ...base, chart: event.spec };
    case "web_sources":
      return { ...base, webSources: event.sources };
    case "awaiting_approval":
      return { ...base, awaiting: event, runId: event.run_id };
    case "error":
      return { ...base, error: { code: event.code, message: event.message } };
    case "done":
      return { ...base, done: true, active: false, runId: event.run_id || state.runId };
    default:
      return base;
  }
}

export function useChat() {
  const [state, setState] = useState<TurnState>(INITIAL);
  const running = useRef(false);

  const consume = useCallback(async (gen: AsyncGenerator<AgentEvent>) => {
    try {
      for await (const event of gen) {
        setState((prev) => reduce(prev, event));
      }
    } catch {
      setState((prev) => ({
        ...prev,
        active: false,
        done: true,
        error: { code: "network", message: "Couldn't reach the server. Please try again." },
      }));
    } finally {
      running.current = false;
    }
  }, []);

  const ask = useCallback(
    async (question: string, approveSql: boolean) => {
      if (running.current || !question.trim()) return;
      running.current = true;
      setState({ ...INITIAL, active: true, waking: true, question });
      await consume(streamChat({ question, approveSql }));
    },
    [consume],
  );

  const respond = useCallback(
    async (runId: string, decision: { decision?: Decision; edited_sql?: string; clarification?: string }) => {
      if (running.current) return;
      running.current = true;
      setState((prev) => ({ ...prev, awaiting: null, active: true }));
      await consume(resumeChat(runId, decision));
    },
    [consume],
  );

  const reset = useCallback(() => setState(INITIAL), []);

  return { state, ask, respond, reset };
}
