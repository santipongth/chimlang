import { useEffect, useRef, useState } from "react";

export interface RunEvent {
  id: number;
  stage: string;
  progress: number | null;
  event_type: string;
  message: string;
  call_status?: string;
  cost_usd?: number;
}

export type StreamState = "idle" | "connecting" | "live" | "reconnecting" | "closed";

const nativeEventSource = (url: string) => new EventSource(url);

export function useRunEvents(
  runId: string,
  enabled: boolean,
  onEvent: (event: RunEvent) => void,
  eventSourceFactory: (url: string) => EventSource = nativeEventSource,
) {
  const [state, setState] = useState<StreamState>(enabled ? "connecting" : "idle");
  const [visibleLastId, setVisibleLastId] = useState(0);
  const lastId = useRef(0);
  const retry = useRef(0);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    let source: EventSource | null = null;
    let timer = 0;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      setState(retry.current ? "reconnecting" : "connecting");
      const query = lastId.current ? `?after_id=${lastId.current}` : "";
      source = eventSourceFactory(`/runs/${encodeURIComponent(runId)}/events/stream${query}`);
      source.onopen = () => {
        retry.current = 0;
        setState("live");
      };
      source.onmessage = (messageEvent) => {
        try {
          const event = JSON.parse(messageEvent.data) as RunEvent;
          const id = Number(messageEvent.lastEventId || event.id || 0);
          if (id > lastId.current) {
            lastId.current = id;
            setVisibleLastId(id);
          }
          onEventRef.current(event);
        } catch {
          // Malformed operational events are ignored; durable replay resumes from last valid id.
        }
      };
      source.onerror = () => {
        source?.close();
        if (stopped) return;
        retry.current += 1;
        setState("reconnecting");
        const delay = Math.min(10_000, 500 * 2 ** Math.min(retry.current - 1, 4));
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      source?.close();
    };
  }, [enabled, eventSourceFactory, runId]);

  return { state, lastEventId: visibleLastId };
}
