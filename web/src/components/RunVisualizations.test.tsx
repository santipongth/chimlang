import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DebatePostItem, ValidationReport } from "../api";
import {
  ContentionGraph,
  EvidenceLineage,
  ScenarioComparisonChart,
  StabilityMatrix,
  StanceTimelineChart,
  UniverseRangeChart,
} from "./RunVisualizations";

const chartApi = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
};

vi.mock("echarts/core", () => ({
  init: vi.fn(() => chartApi),
  use: vi.fn(),
}));

vi.mock("echarts/charts", () => ({
  BarChart: {},
  CustomChart: {},
  HeatmapChart: {},
  LineChart: {},
  SankeyChart: {},
  ScatterChart: {},
}));

vi.mock("echarts/components", () => ({
  AriaComponent: {},
  GridComponent: {},
  MarkLineComponent: {},
  TooltipComponent: {},
  VisualMapComponent: {},
}));

vi.mock("echarts/renderers", () => ({
  CanvasRenderer: {},
}));

vi.mock("cytoscape", () => ({
  default: vi.fn(() => ({
    on: vi.fn(),
    destroy: vi.fn(),
  })),
}));

const posts: DebatePostItem[] = [
  { round_no: 0, agent_idx: 1, segment: "urban", content: "supports rollout", stance: 0.7, sentiment: 0.4, failed: false },
  { round_no: 0, agent_idx: 2, segment: "rural", content: "opposes rollout", stance: -0.1, sentiment: -0.2, failed: false },
  { round_no: 1, agent_idx: 3, segment: "urban", content: "strong support", stance: 0.9, sentiment: 0.5, failed: false },
  { round_no: 1, agent_idx: 4, segment: "rural", content: "strong concern", stance: -0.6, sentiment: -0.4, failed: false },
  { round_no: 1, agent_idx: 5, segment: "student", content: "", stance: 0, sentiment: 0, failed: true },
];

describe("Run visualizations", () => {
  it("renders ECharts visualizations with accessible labels and table fallbacks", () => {
    const report: ValidationReport = {
      parent_run_id: "parent",
      status: "running",
      completed: 2,
      failure_rate: 0.1,
      sign_agreement: 0.8,
      stance_range: [-0.2, 0.6],
      between_run_dispersion: 0.12,
      claim_overlap: 0.5,
      agent_failure_rate: 0.05,
      total_cost_usd: 0.02,
      children: [
        { run_id: "a", seed: 11, status: "complete", error: null, value: 0.4 },
        { run_id: "b", seed: 12, status: "running", error: null, value: null },
      ],
      note: "",
    };

    render(
      <div>
        <UniverseRangeChart universes={[{ universe_id: 0, estimate: 0.52, ci95: [0.41, 0.63], conclusion: "range" }]} />
        <ScenarioComparisonChart
          scenarios={[
            { name: "baseline", belief_by_segment: { urban: 0.4, rural: 0.3 } },
            { name: "variant", belief_by_segment: { urban: 0.55, rural: 0.2 } },
          ]}
          population={[{ segment: "urban", population_share: 0.6 }, { segment: "rural", population_share: 0.4 }]}
        />
        <StanceTimelineChart posts={posts} />
        <StabilityMatrix report={report} />
        <EvidenceLineage sources={[{ label: "source one" }]} subject="Policy outcome" posts={posts} synthesis="summary" />
      </div>,
    );

    expect(screen.getByTestId("universe-range-chart")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("scenario-comparison-chart")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("stance-timeline-chart")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("stability-matrix")).toHaveAttribute("role", "img");
    expect(screen.getByTestId("evidence-lineage-chart")).toHaveAttribute("role", "img");
    expect(screen.getByText(/Multiverse ranges/)).toBeInTheDocument();
    expect(screen.getByText(/Evidence lineage/)).toBeInTheDocument();
  });

  it("lets keyboard users select a debate segment outside the canvas graph", async () => {
    render(<ContentionGraph posts={posts} />);

    await userEvent.click(screen.getByRole("button", { name: /urban/ }));

    expect(screen.getByText("Posts: urban")).toBeInTheDocument();
    expect(screen.getByText(/strong support/)).toBeInTheDocument();
    expect(screen.getByText(/Contention edges/)).toBeInTheDocument();
  });
});
