/**
 * Curated entry points for a first-time visitor.
 *
 * The corpus is deliberately narrow (15 countries, three World Bank indicators,
 * CO2 for 2021-22). An empty text box over a narrow corpus invites a question we
 * cannot answer, so the visitor's first impression becomes a refusal. These six
 * are the fix: every one is verified against the deployed backend, and together
 * they show the range — lookup, comparison, trend, aggregation, a chart, and a
 * deliberate refusal so the guardrail is visible rather than merely claimed.
 *
 * The refusal is included on purpose. Watching the system decline a question it
 * genuinely cannot answer, and say exactly why, is a better signal than a sixth
 * question that works.
 */
export interface Example {
  /** Short label for the chip. */
  label: string;
  /** What this one demonstrates, shown under the label. */
  hint: string;
  question: string;
  /** Rendered differently: this one is expected to be declined. */
  refusal?: boolean;
}

export const EXAMPLES: Example[] = [
  {
    label: "Look up one value",
    hint: "single row",
    question: "What was Japan's total population in 2022?",
  },
  {
    label: "Compare two countries",
    hint: "filter + join",
    question: "Compare CO2 per capita between the United States and China in 2022.",
  },
  {
    label: "Trend over time",
    hint: "group by year",
    question: "What was the total CO2 emitted across all countries in each year?",
  },
  {
    label: "Aggregate everything",
    hint: "average across rows",
    question: "What is the average life expectancy across all countries in 2022?",
  },
  {
    label: "Rank and chart it",
    hint: "order by + chart",
    question: "Which 5 countries had the highest CO2 per capita in 2022?",
  },
  {
    label: "Watch it refuse",
    hint: "outside the data",
    question: "What was Kenya's CO2 per capita in 2022?",
    refusal: true,
  },
];

/** One line, directly above the input, so nobody has to guess the boundary. */
export const SCOPE_LINE =
  "15 countries · GDP per capita, population, life expectancy (World Bank, 2022) · CO₂ emissions (Our World in Data, 2021–2022)";
