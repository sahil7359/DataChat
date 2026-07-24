"use client";

import { useEffect, useRef } from "react";
import embed from "vega-embed";

type Spec = Parameters<typeof embed>[1];

// Thin renderer: the backend emits a validated Vega-Lite spec, we just draw it.
// No intelligence in the frontend — that's the design.
export function ChartRenderer({ spec }: { spec: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let disposed = false;
    void embed(el, spec as unknown as Spec, { actions: false }).catch(() => {
      /* rendering is best-effort; the table already carries the answer */
    });
    return () => {
      if (!disposed) {
        disposed = true;
        el.replaceChildren();
      }
    };
  }, [spec]);

  return <div ref={ref} className="w-full overflow-x-auto" aria-label="chart" />;
}
