import { parseEventStream } from "./sse";
import type { AgentEvent, Dataset, Decision } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

/** Download links for a finished run's report and result data. */
export const reportMarkdownUrl = (runId: string) => `${BASE}/runs/${runId}/report.md`;
export const reportCsvUrl = (runId: string) => `${BASE}/runs/${runId}/data.csv`;

export interface AskRequest {
  question: string;
  conversationId?: string;
  approveSql: boolean;
}

export async function* streamChat(req: AskRequest): AsyncGenerator<AgentEvent> {
  const resp = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      question: req.question,
      conversation_id: req.conversationId,
      options: { approve_sql: req.approveSql },
    }),
  });
  yield* readStream(resp);
}

export async function* resumeChat(
  runId: string,
  decision: { decision?: Decision; edited_sql?: string; clarification?: string },
): AsyncGenerator<AgentEvent> {
  const resp = await fetch(`${BASE}/chat/${runId}/resume`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(decision),
  });
  yield* readStream(resp);
}

export async function fetchDatasets(): Promise<Dataset[]> {
  const resp = await fetch(`${BASE}/datasets`);
  if (!resp.ok) throw new Error(`datasets request failed: ${resp.status}`);
  return (await resp.json()) as Dataset[];
}

export interface MetricsSnapshot {
  counters: Record<string, number>;
  gauges: Record<string, number>;
  cache_hit_rate: number;
  breakers: Record<string, string>;
}

export async function fetchMetrics(): Promise<MetricsSnapshot> {
  const resp = await fetch(`${BASE}/metrics`);
  if (!resp.ok) throw new Error(`metrics request failed: ${resp.status}`);
  return (await resp.json()) as MetricsSnapshot;
}

async function* readStream(resp: Response): AsyncGenerator<AgentEvent> {
  if (!resp.ok || !resp.body) {
    throw new Error(`chat request failed: ${resp.status}`);
  }
  yield* parseEventStream(resp.body);
}
