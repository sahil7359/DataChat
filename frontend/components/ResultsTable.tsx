import type { RowsEvent } from "@/lib/types";

export function ResultsTable({ rows }: { rows: RowsEvent }) {
  if (rows.row_count === 0) {
    return <p className="text-sm opacity-60">No rows matched that question.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-white/10">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/5">
          <tr>
            {rows.columns.map((col) => (
              <th key={col} className="px-3 py-2 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.rows.map((row, i) => (
            <tr key={i} className="border-t border-white/5">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 tabular-nums">
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.truncated && (
        <p className="px-3 py-2 text-xs opacity-50">Showing the first {rows.row_count} rows.</p>
      )}
    </div>
  );
}

function formatCell(cell: unknown): string {
  if (cell === null || cell === undefined) return "—";
  if (typeof cell === "number") return cell.toLocaleString();
  if (typeof cell === "string" || typeof cell === "boolean") return String(cell);
  return JSON.stringify(cell);
}
