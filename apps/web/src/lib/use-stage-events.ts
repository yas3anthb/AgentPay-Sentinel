"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { RELAY_WS_URL } from "@/lib/config";
import type { StageEvent } from "@/lib/pipeline";

export type SocketState = "connecting" | "open" | "closed" | "error";

/**
 * Subscribes to the relay's stage stream.
 *
 * `requestId` watches one request; `null` watches the firehose. The firehose is
 * what agent-driven runs use: the agent-simulator does not forward an
 * X-Request-Id to the gateway, so there is no id to filter on. That is a real
 * limitation of a single-tenant demo, not something to hide.
 */
export function useStageEvents(requestId: string | null, enabled = true) {
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [socketState, setSocketState] = useState<SocketState>("closed");
  const [dropped, setDropped] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    setEvents([]);
    setDropped(0);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const path = requestId ? `/ws/transactions/${encodeURIComponent(requestId)}` : "/ws/live";
    let socket: WebSocket;
    try {
      socket = new WebSocket(`${RELAY_WS_URL}${path}`);
    } catch {
      setSocketState("error");
      return;
    }
    socketRef.current = socket;
    setSocketState("connecting");

    socket.onopen = () => setSocketState("open");
    socket.onerror = () => setSocketState("error");
    socket.onclose = () => setSocketState("closed");
    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data as string) as Record<string, unknown>;
        if (payload.type === "stage") {
          setEvents((prev) => [...prev, payload as unknown as StageEvent]);
        } else if (payload.type === "dropped") {
          setDropped((prev) => prev + Number(payload.count ?? 0));
        }
      } catch {
        /* a malformed frame is not worth tearing the UI down for */
      }
    };

    return () => {
      socket.onclose = null;
      socket.close();
      socketRef.current = null;
    };
  }, [requestId, enabled]);

  return { events, socketState, dropped, reset };
}

/** True when this browser can actually render the 3D scene. */
export function useWebGLAvailable(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    try {
      const canvas = document.createElement("canvas");
      const gl =
        canvas.getContext("webgl2") ??
        canvas.getContext("webgl") ??
        canvas.getContext("experimental-webgl");
      setAvailable(Boolean(gl));
    } catch {
      setAvailable(false);
    }
  }, []);
  return available;
}

/** Honours prefers-reduced-motion, and keeps honouring it if the user changes it. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}
