"use client";

import { useEffect, useState } from "react";

import { fetchMetrics, type MetricsSnapshot } from "@/lib/api";

// A deliberately small operational dashboard. MLflow holds the deep traces; this
// shows the live counters the free-tier host exposes at /metrics.
export default function Dashboard() {
  const [metrics, setMetrics] = useState<MetricsSnapshot | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const load = () => {
      fetchMetrics()
        .then((m) => {
          setMetrics(m);
          setError(false);
        })
        .catch(() => setError(true));
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const requests = metrics
    ? Object.entries(metrics.counters).filter(([k]) => k.startsWith("http_requests_total"))
    : [];

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">Observability</h1>
      {error && <p className="text-sm text-red-400">Metrics endpoint unreachable.</p>}
      {!metrics && !error && <p className="text-sm opacity-60">Loading…</p>}

      {metrics && (
        <>
          <Card title="Cache hit rate">
            <span className="text-3xl tabular-nums">
              {(metrics.cache_hit_rate * 100).toFixed(1)}%
            </span>
          </Card>

          <Card title="Provider circuit breakers">
            <div className="flex flex-wrap gap-2">
              {Object.entries(metrics.breakers).map(([provider, state]) => (
                <span
                  key={provider}
                  className={`rounded-full px-3 py-1 text-sm ${
                    state === "closed" ? "bg-emerald-500/20" : "bg-amber-500/20"
                  }`}
                >
                  {provider}: {state}
                </span>
              ))}
            </div>
          </Card>

          <Card title="Requests">
            {requests.length === 0 ? (
              <p className="text-sm opacity-60">No requests recorded yet.</p>
            ) : (
              <ul className="text-sm tabular-nums">
                {requests.map(([label, count]) => (
                  <li key={label} className="flex justify-between border-b border-white/5 py-1">
                    <span className="font-mono text-xs opacity-70">{label}</span>
                    <span>{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </main>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/5 p-4">
      <h2 className="mb-2 text-sm font-medium opacity-70">{title}</h2>
      {children}
    </section>
  );
}
