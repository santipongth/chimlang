import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunEvents } from "./useRunEvents";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
}

describe("useRunEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reconnects with the last valid event id", () => {
    const onEvent = vi.fn();
    const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource;

    const { result, unmount } = renderHook(() => useRunEvents("run 1", true, onEvent, factory));

    expect(FakeEventSource.instances[0].url).toBe("/runs/run%201/events/stream");

    act(() => {
      FakeEventSource.instances[0].onopen?.(new Event("open"));
    });
    expect(result.current.state).toBe("live");

    act(() => {
      FakeEventSource.instances[0].onmessage?.({ data: JSON.stringify({ id: 7, stage: "running", progress: 0.4, event_type: "tick", message: "ok" }), lastEventId: "7" } as MessageEvent);
    });
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(result.current.lastEventId).toBe(7);

    act(() => {
      FakeEventSource.instances[0].onerror?.(new Event("error"));
    });
    expect(result.current.state).toBe("reconnecting");

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(FakeEventSource.instances[1].url).toBe("/runs/run%201/events/stream?after_id=7");

    unmount();
    expect(FakeEventSource.instances[1].close).toHaveBeenCalled();
  });

  it("ignores malformed events without moving the replay cursor", () => {
    const onEvent = vi.fn();
    const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource;

    const { result } = renderHook(() => useRunEvents("run-2", true, onEvent, factory));

    act(() => {
      FakeEventSource.instances[0].onmessage?.({ data: "{not-json", lastEventId: "5" } as MessageEvent);
    });

    expect(onEvent).not.toHaveBeenCalled();
    expect(result.current.lastEventId).toBe(0);
  });
});
