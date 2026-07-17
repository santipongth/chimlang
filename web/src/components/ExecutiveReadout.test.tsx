// Executive Readout is a reusable result component, not a route-level page.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { SimRunDetail } from "../api";
import { ExecutiveReadout, hasUsableExecutiveSynthesis } from "../pages/RunDetail";

const data = {
  engine: "debate",
  status: "complete",
  subject: "Policy test",
  manifest: { complete: true },
} as unknown as SimRunDetail;

const validSynthesis = {
  summary: "Validated analyst summary",
  confidence: 0.8,
  distribution: [{ bucket: "support", pct: 100 }],
  key_drivers: ["driver"],
  risks: ["risk"],
};

describe("ExecutiveReadout", () => {
  it("rejects a valid JSON object that is not an Executive synthesis", async () => {
    const rerun = vi.fn();
    const malformed = { bucket: "support", pct: 65 };

    expect(hasUsableExecutiveSynthesis(malformed as never)).toBe(false);
    render(
      <ExecutiveReadout
        data={data}
        p={{ synthesis: malformed as never }}
        isDebate
        t={(key) => key}
        onRerunFrozen={rerun}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("rd_synthesis_unavailable");
    expect(screen.queryByText("rd_prediction_note")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "rd_rerun_frozen_for_readout" }));
    expect(rerun).toHaveBeenCalledOnce();
  });

  it("rejects a partially populated synthesis instead of rendering misleading output", () => {
    const partial = {
      ...validSynthesis,
      confidence: Number.NaN,
      risks: [""],
    };

    expect(hasUsableExecutiveSynthesis(partial)).toBe(false);
  });

  it("renders a validated synthesis and its calibration note", () => {
    expect(hasUsableExecutiveSynthesis(validSynthesis)).toBe(true);
    render(
      <ExecutiveReadout
        data={data}
        p={{ synthesis: validSynthesis }}
        isDebate
        t={(key) => key}
      />,
    );

    expect(screen.getByRole("heading", { name: "Validated analyst summary" })).toBeVisible();
    expect(screen.getByText("rd_prediction_note")).toBeVisible();
  });
});
