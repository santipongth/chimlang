import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart, CustomChart, HeatmapChart, LineChart, SankeyChart, ScatterChart } from "echarts/charts";
import { AriaComponent, GridComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import cytoscape from "cytoscape";
import type { EChartsOption } from "echarts";
import type { DebatePostItem, ValidationReport } from "../api";

echarts.use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  CustomChart,
  GridComponent,
  HeatmapChart,
  LineChart,
  MarkLineComponent,
  SankeyChart,
  ScatterChart,
  TooltipComponent,
  VisualMapComponent,
]);

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function AccessibleChart({
  option,
  label,
  height = 320,
  testId,
}: {
  option: EChartsOption;
  label: string;
  height?: number;
  testId?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.setOption({ ...option, animation: !reducedMotion() });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [option]);
  return (
    <div
      ref={ref}
      role="img"
      aria-label={label}
      tabIndex={0}
      data-testid={testId}
      className="w-full rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-primary"
      style={{ height }}
    />
  );
}

function FallbackTable({
  label,
  headers,
  rows,
}: {
  label: string;
  headers: string[];
  rows: (string | number)[][];
}) {
  return (
    <details className="mt-3 rounded-xl border border-border bg-background p-3 text-xs">
      <summary className="cursor-pointer font-medium">ตารางข้อมูล: {label}</summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-left">
          <thead>
            <tr>{headers.map((h) => <th key={h} className="border-b border-border px-2 py-1.5">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>{row.map((value, j) => <td key={j} className="border-b border-border/60 px-2 py-1.5 tabular-nums">{value}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export interface UniverseDatum {
  universe_id: number;
  estimate: number;
  ci95: [number, number];
  conclusion: string;
}

export function UniverseRangeChart({ universes, fallbackRange }: { universes: UniverseDatum[]; fallbackRange?: [number, number] }) {
  const data = universes.length
    ? universes
    : fallbackRange
      ? [{ universe_id: 0, estimate: (fallbackRange[0] + fallbackRange[1]) / 2, ci95: fallbackRange, conclusion: "ช่วงรวม" }]
      : [];
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 72, right: 24, top: 20, bottom: 42 },
    tooltip: { trigger: "item" },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    yAxis: { type: "category", data: data.map((u) => `U${u.universe_id + 1}`) },
    series: [
      {
        name: "ช่วง 95%",
        type: "custom",
        renderItem: (_params, api) => {
          const low = api.coord([api.value(1), api.value(0)]);
          const high = api.coord([api.value(2), api.value(0)]);
          return { type: "line", shape: { x1: low[0], y1: low[1], x2: high[0], y2: high[1] }, style: { stroke: "#94a3b8", lineWidth: 5 } };
        },
        encode: { x: [1, 2], y: 0 },
        data: data.map((u, i) => [i, u.ci95[0], u.ci95[1]]),
        tooltip: { formatter: (p: any) => `${data[p.dataIndex].conclusion}<br/>95%: ${(p.value[1] * 100).toFixed(1)}–${(p.value[2] * 100).toFixed(1)}%` },
      },
      {
        name: "ค่ากลาง",
        type: "scatter",
        symbolSize: 12,
        itemStyle: { color: "#059669" },
        data: data.map((u, i) => [u.estimate, i]),
        tooltip: { formatter: (p: any) => `U${p.dataIndex + 1}: ${(p.value[0] * 100).toFixed(1)}%` },
      },
    ],
  }), [data]);
  if (!data.length) return <p className="text-sm text-muted-foreground">ไม่มีข้อมูล multiverse</p>;
  return (
    <>
      <AccessibleChart option={option} label="ช่วงความไม่แน่นอนของแต่ละ universe" testId="universe-range-chart" />
      <FallbackTable label="Multiverse ranges" headers={["Universe", "Estimate", "95% low", "95% high", "Conclusion"]} rows={data.map((u) => [`U${u.universe_id + 1}`, u.estimate.toFixed(4), u.ci95[0].toFixed(4), u.ci95[1].toFixed(4), u.conclusion])} />
    </>
  );
}

export interface ScenarioDatum { name: string; belief_by_segment: Record<string, number> }

export function ScenarioComparisonChart({ scenarios, population }: { scenarios: ScenarioDatum[]; population: { segment: string; population_share: number }[] }) {
  const segments = [...new Set(scenarios.flatMap((s) => Object.keys(s.belief_by_segment)))];
  const baseline = scenarios[0];
  const variant = scenarios[scenarios.length - 1];
  const rows = segments.map((segment) => {
    const before = baseline?.belief_by_segment[segment] ?? 0;
    const after = variant?.belief_by_segment[segment] ?? 0;
    const share = population.find((x) => x.segment === segment)?.population_share ?? 0;
    return { segment, before, after, delta: after - before, share };
  });
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 135, right: 35, top: 24, bottom: 42 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%` } },
    yAxis: { type: "category", data: rows.map((r) => r.segment), axisLabel: { width: 120, overflow: "truncate" } },
    series: [{ type: "bar", data: rows.map((r) => ({ value: r.delta, itemStyle: { color: r.delta >= 0 ? "#059669" : "#ef4444" } })), markLine: { silent: true, symbol: "none", data: [{ xAxis: 0 }] } }],
  }), [rows]);
  if (!rows.length) return <p className="text-sm text-muted-foreground">ไม่มีข้อมูลเปรียบเทียบ scenario</p>;
  return (
    <>
      <AccessibleChart option={option} label="การเปลี่ยนแปลงระหว่าง baseline และ variant แยกตามกลุ่ม" height={Math.max(280, rows.length * 44)} testId="scenario-comparison-chart" />
      <FallbackTable label="Scenario comparison" headers={["Segment", "Baseline", "Variant", "Delta", "Population share"]} rows={rows.map((r) => [r.segment, r.before.toFixed(3), r.after.toFixed(3), r.delta.toFixed(3), r.share.toFixed(3)])} />
    </>
  );
}

export function StanceTimelineChart({ posts }: { posts: DebatePostItem[] }) {
  const ok = posts.filter((p) => !p.failed);
  const rounds = [...new Set(ok.map((p) => p.round_no))].sort((a, b) => a - b);
  const averages = rounds.map((round) => {
    const values = ok.filter((p) => p.round_no === round).map((p) => p.stance);
    return values.reduce((a, b) => a + b, 0) / Math.max(1, values.length);
  });
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 48, right: 24, top: 22, bottom: 48 },
    tooltip: { trigger: "item" },
    xAxis: { type: "value", min: 1, max: Math.max(1, rounds.length), interval: 1, name: "รอบ" },
    yAxis: { type: "value", min: -1, max: 1, name: "stance" },
    series: [
      { name: "Agent", type: "scatter", symbolSize: 7, itemStyle: { color: "rgba(5,150,105,.42)" }, data: ok.map((p, i) => [p.round_no + 1 + ((i % 7) - 3) * 0.018, p.stance, p.segment, p.content]), tooltip: { formatter: (p: any) => `${p.value[2]} · r${Math.round(p.value[0])}<br/>${Number(p.value[1]).toFixed(2)}<br/>${String(p.value[3]).slice(0, 120)}` } },
      { name: "Average", type: "line", symbolSize: 9, lineStyle: { width: 3, color: "#047857" }, itemStyle: { color: "#047857" }, data: averages.map((value, i) => [rounds[i] + 1, value]) },
    ],
  }), [averages, ok, rounds]);
  if (!ok.length) return <p className="text-sm text-muted-foreground">ไม่มี stance ที่ใช้งานได้</p>;
  return (
    <>
      <AccessibleChart option={option} label="การกระจาย stance ของ agent และค่าเฉลี่ยในแต่ละรอบ" testId="stance-timeline-chart" />
      <FallbackTable label="Stance timeline" headers={["Round", "Average", "Posts", "Failed"]} rows={rounds.map((round, i) => [`r${round + 1}`, averages[i].toFixed(3), ok.filter((p) => p.round_no === round).length, posts.filter((p) => p.round_no === round && p.failed).length])} />
    </>
  );
}

export function StabilityMatrix({ report }: { report: ValidationReport }) {
  const children = report.children ?? [];
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 72, right: 20, top: 24, bottom: 42 },
    tooltip: { formatter: (p: any) => `seed ${children[p.dataIndex]?.seed}<br/>${children[p.dataIndex]?.status}<br/>value ${children[p.dataIndex]?.value == null ? "—" : Number(children[p.dataIndex]?.value).toFixed(3)}` },
    xAxis: { type: "category", data: children.map((c) => String(c.seed)), name: "seed" },
    yAxis: { type: "category", data: ["ผลรัน"] },
    visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, inRange: { color: ["#ef4444", "#f8fafc", "#059669"] } },
    series: [{ type: "heatmap", data: children.map((c, i) => [i, 0, c.value ?? 0]), label: { show: true, formatter: (p: any) => children[p.dataIndex]?.value == null ? children[p.dataIndex]?.status : Number(children[p.dataIndex]?.value).toFixed(2) } }],
  }), [children]);
  if (!children.length) return null;
  return (
    <>
      <AccessibleChart option={option} label="เมทริกซ์ความเสถียรของผลจากสาม seed" height={220} testId="stability-matrix" />
      <FallbackTable label="3-seed stability" headers={["Seed", "Status", "Value", "Error"]} rows={children.map((c) => [c.seed, c.status, c.value == null ? "—" : c.value.toFixed(4), c.error ?? ""])} />
    </>
  );
}

const CONTENTION_NODE_LIMIT = 24;

function graphForRound(posts: DebatePostItem[], round: number) {
  const usable = posts.filter((p) => !p.failed && p.round_no === round);
  const grouped = new Map<string, DebatePostItem[]>();
  usable.forEach((p) => grouped.set(p.segment, [...(grouped.get(p.segment) ?? []), p]));
  const allNodes = [...grouped.entries()].map(([segment, items]) => ({ segment, avg: items.reduce((sum, p) => sum + p.stance, 0) / items.length, posts: items.length }));
  // COSE is quadratic in the number of segment pairs. Keep the interactive graph
  // bounded for 1,000-agent runs; the full post set remains available in Debate feed.
  const nodes = allNodes
    .sort((left, right) => right.posts - left.posts || Math.abs(right.avg) - Math.abs(left.avg) || left.segment.localeCompare(right.segment))
    .slice(0, CONTENTION_NODE_LIMIT);
  const edges = nodes.flatMap((left, i) => nodes.slice(i + 1).map((right) => ({ from: left.segment, to: right.segment, tension: Math.abs(left.avg - right.avg) })).filter((e) => e.tension >= 0.35));
  return { nodes, edges, hiddenSegments: Math.max(0, allNodes.length - nodes.length) };
}

export function ContentionGraph({ posts }: { posts: DebatePostItem[] }) {
  const rounds = [...new Set(posts.map((p) => p.round_no))].sort((a, b) => a - b);
  const [round, setRound] = useState(rounds.at(-1) ?? 0);
  const [selected, setSelected] = useState("");
  const container = useRef<HTMLDivElement>(null);
  const graph = useMemo(() => graphForRound(posts, round), [posts, round]);
  useEffect(() => {
    if (!container.current || !graph.nodes.length) return;
    const cy = cytoscape({
      container: container.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.segment, label: `${n.segment}\n${n.avg.toFixed(2)}` } })),
        ...graph.edges.map((e, i) => ({ data: { id: `e${i}`, source: e.from, target: e.to, tension: e.tension } })),
      ],
      style: [
        { selector: "node", style: { label: "data(label)", "text-wrap": "wrap", "text-valign": "center", "font-size": 10, color: "#0f172a", "background-color": "#a7f3d0", width: 72, height: 72 } },
        { selector: "edge", style: { width: "mapData(tension, .35, 2, 2, 8)", "line-color": "#f59e0b", opacity: .65, "curve-style": "bezier" } },
        { selector: ":selected", style: { "border-width": 4, "border-color": "#047857" } },
      ],
      layout: { name: "cose", animate: !reducedMotion(), randomize: false, fit: true, padding: 24 },
    });
    cy.on("tap", "node", (event) => setSelected(String(event.target.id())));
    return () => cy.destroy();
  }, [graph]);
  const related = selected ? posts.filter((p) => p.round_no === round && p.segment === selected) : [];
  if (!rounds.length) return <p className="text-sm text-muted-foreground">ไม่มีข้อมูล contention</p>;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2" aria-label="กรองกราฟตามรอบ">
        {rounds.map((r) => <button key={r} onClick={() => { setRound(r); setSelected(""); }} aria-pressed={round === r} className={`rounded-lg border px-3 py-1 text-xs ${round === r ? "border-primary bg-primary/10 text-primary-strong" : "border-border"}`}>r{r + 1}</button>)}
      </div>
      <div ref={container} role="img" aria-label={`Contention graph รอบ ${round + 1}`} tabIndex={0} data-testid="contention-graph" className="h-[360px] w-full rounded-xl border border-border outline-none focus-visible:ring-2 focus-visible:ring-primary" />
      <div className="mt-3 flex flex-wrap gap-2" aria-label="เลือก segment ในกราฟ">
        {graph.nodes.map((node) => <button key={node.segment} onClick={() => setSelected(node.segment)} aria-pressed={selected === node.segment} className="rounded-full border border-border px-3 py-1 text-xs hover:bg-muted">{node.segment} {node.avg.toFixed(2)}</button>)}
      </div>
      {graph.hiddenSegments > 0 && <p className="mt-2 text-xs text-muted-foreground">แสดง {graph.nodes.length} segments ที่มีข้อมูลเด่นจากทั้งหมด {graph.nodes.length + graph.hiddenSegments}; posts ทั้งหมดยังอยู่ใน Debate feed</p>}
      {selected && <div className="mt-3 rounded-xl border border-border bg-background p-3 text-xs"><div className="font-semibold">Posts: {selected}</div>{related.map((p) => <p key={p.agent_idx} className="mt-2 text-muted-foreground">#{p.agent_idx}: {p.content}</p>)}</div>}
      <FallbackTable label="Contention edges" headers={["Round", "From", "To", "Tension"]} rows={graph.edges.map((e) => [`r${round + 1}`, e.from, e.to, e.tension.toFixed(3)])} />
    </div>
  );
}

export function EvidenceLineage({ sources, subject, posts, synthesis }: { sources: any[]; subject: string; posts: DebatePostItem[]; synthesis: string }) {
  const sourceNodes = sources.slice(0, 8).map((s, i) => ({ name: `แหล่ง ${i + 1}: ${String(s.label ?? s.title ?? s.provider ?? "evidence").slice(0, 28)}` }));
  const segments = [...new Set(posts.filter((p) => !p.failed).map((p) => p.segment))].slice(0, 10);
  const claim = `Claim: ${subject.slice(0, 42)}`;
  const result = `Synthesis: ${synthesis.slice(0, 42) || "ผลสังเคราะห์"}`;
  const nodes = [...sourceNodes, { name: claim }, ...segments.map((name) => ({ name })), { name: result }];
  const links = [
    ...sourceNodes.map((node) => ({ source: node.name, target: claim, value: 1 })),
    ...segments.map((segment) => ({ source: claim, target: segment, value: Math.max(1, posts.filter((p) => p.segment === segment && !p.failed).length) })),
    ...segments.map((segment) => ({ source: segment, target: result, value: Math.max(1, posts.filter((p) => p.segment === segment && !p.failed).length) })),
  ];
  const option = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: "item" },
    series: [{ type: "sankey", data: nodes, links, emphasis: { focus: "adjacency" }, lineStyle: { color: "gradient", curveness: .5 }, label: { width: 130, overflow: "truncate" } }],
  }), [links, nodes]);
  if (!sourceNodes.length || !segments.length) return <p className="text-sm text-muted-foreground">ยังไม่มี lineage ที่เชื่อมแหล่งข้อมูลกับ agent</p>;
  return (
    <>
      <AccessibleChart option={option} label="เส้นทางหลักฐานจากแหล่งข้อมูลผ่าน claim และ segment ไปยัง synthesis" height={420} testId="evidence-lineage-chart" />
      <FallbackTable label="Evidence lineage" headers={["Source", "Target", "Weight"]} rows={links.map((link) => [link.source, link.target, link.value])} />
    </>
  );
}
