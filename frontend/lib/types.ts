// Event and API types mirroring the backend SSE contract (TechSpec §4).

export interface StatusEvent {
  type: "status";
  stage: string;
}
export interface PlanEvent {
  type: "plan";
  steps: string[];
  target_tables: string[];
}
export interface SqlEvent {
  type: "sql";
  sql: string;
}
export interface AwaitingApprovalEvent {
  type: "awaiting_approval";
  run_id: string;
  kind: "approve" | "clarify";
  sql: string | null;
  options: string[];
}
export interface RowsEvent {
  type: "rows";
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}
export interface ExplanationDeltaEvent {
  type: "explanation_delta";
  text: string;
}
export interface ChartSpecEvent {
  type: "chart_spec";
  spec: Record<string, unknown>;
}
export interface WebSourcesEvent {
  type: "web_sources";
  sources: { title: string; url: string }[];
}
export interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
}
export interface DoneEvent {
  type: "done";
  run_id: string;
  trace_id: string | null;
}

export type AgentEvent =
  | StatusEvent
  | PlanEvent
  | SqlEvent
  | AwaitingApprovalEvent
  | RowsEvent
  | ExplanationDeltaEvent
  | ChartSpecEvent
  | WebSourcesEvent
  | ErrorEvent
  | DoneEvent;

export interface Dataset {
  name: string;
  source: string;
  version: string;
  description: string;
  tables: string[];
}

export type Decision = "approve" | "edit" | "reject";
