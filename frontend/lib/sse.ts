import type {
  AgentEvent,
  AwaitingApprovalEvent,
  ChartSpecEvent,
  ErrorEvent,
  ExplanationDeltaEvent,
  PlanEvent,
  RowsEvent,
  SqlEvent,
  StatusEvent,
} from "./types";

// Parse a fetch SSE body into typed AgentEvents. The backend is our own contract,
// so we narrow each `event:` frame into its typed shape here (once) rather than
// scattering casts through the UI.
export async function* parseEventStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseFrame(frame);
      if (event) yield event;
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function parseFrame(frame: string): AgentEvent | null {
  let name = "";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!name) return null;
  const payload = dataLines.length ? (JSON.parse(dataLines.join("\n")) as Record<string, unknown>) : {};
  return toEvent(name, payload);
}

function toEvent(name: string, d: Record<string, unknown>): AgentEvent | null {
  switch (name) {
    case "status":
      return { type: "status", stage: asString(d.stage) } satisfies StatusEvent;
    case "plan":
      return {
        type: "plan",
        steps: asStringArray(d.steps),
        target_tables: asStringArray(d.target_tables),
      } satisfies PlanEvent;
    case "sql":
      return { type: "sql", sql: asString(d.sql) } satisfies SqlEvent;
    case "awaiting_approval":
      return {
        type: "awaiting_approval",
        run_id: asString(d.run_id),
        kind: d.kind === "clarify" ? "clarify" : "approve",
        sql: d.sql == null ? null : asString(d.sql),
        options: asStringArray(d.options),
      } satisfies AwaitingApprovalEvent;
    case "rows":
      return {
        type: "rows",
        columns: asStringArray(d.columns),
        rows: Array.isArray(d.rows) ? (d.rows as unknown[][]) : [],
        row_count: Number(d.row_count),
        truncated: Boolean(d.truncated),
      } satisfies RowsEvent;
    case "explanation_delta":
      return { type: "explanation_delta", text: asString(d.text) } satisfies ExplanationDeltaEvent;
    case "chart_spec":
      return { type: "chart_spec", spec: (d.spec ?? {}) as Record<string, unknown> } satisfies ChartSpecEvent;
    case "error":
      return { type: "error", code: asString(d.code), message: asString(d.message) } satisfies ErrorEvent;
    case "done":
      return {
        type: "done",
        run_id: asString(d.run_id),
        trace_id: d.trace_id == null ? null : asString(d.trace_id),
      };
    default:
      return null;
  }
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(asString) : [];
}
