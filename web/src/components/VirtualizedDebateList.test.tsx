import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DebatePostItem } from "../api";
import { VirtualizedDebateList } from "./VirtualizedDebateList";

function posts(count: number): DebatePostItem[] {
  return Array.from({ length: count }, (_, index) => ({
    round_no: 0,
    agent_idx: index,
    segment: `กลุ่มทดสอบ ${index}`,
    content: `โพสต์ภาษาไทยลำดับ ${index}`,
    stance: (index % 20) / 10 - 1,
    sentiment: 0,
    failed: false,
    move_id: `m-${index}`,
    move_type: "claim",
  }));
}

describe("VirtualizedDebateList", () => {
  it("keeps a 1,000-post payload bounded and renders later rows after scroll", () => {
    render(<VirtualizedDebateList posts={posts(1000)} />);
    const list = screen.getByTestId("virtual-debate-list");
    expect(screen.getAllByTestId("debate-post-row").length).toBeLessThan(20);
    expect(screen.getByText("โพสต์ภาษาไทยลำดับ 0")).toBeInTheDocument();
    Object.defineProperty(list, "scrollTop", { value: 132 * 500, configurable: true });
    fireEvent.scroll(list);
    expect(screen.getAllByText(/โพสต์ภาษาไทยลำดับ 49[6-9]|โพสต์ภาษาไทยลำดับ 500/).length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("debate-post-row").length).toBeLessThan(20);
  });
});
