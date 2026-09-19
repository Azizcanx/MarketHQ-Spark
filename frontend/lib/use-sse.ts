"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface SSEEvent {
  event: string;
  data: any;
  event_id: string;
  timestamp: string;
}

interface SSEOptions {
  url?: string;
  reconnect?: boolean;
  maxReconnectDelay?: number;
  heartbeatTimeout?: number;
  onEvent?: (event: SSEEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export function useSSE(options: SSEOptions = {}) {
  const {
    url = "/api/workforce/sse",
    reconnect = true,
    maxReconnectDelay = 30,
    heartbeatTimeout = 60,
    onEvent,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [reconnectDelay, setReconnectDelay] = useState(1);
  const [isStale, setIsStale] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastEventTimeRef = useRef<number>(0);
  const receivedEventsRef = useRef<Set<string>>(new Set());

  const connect = useCallback(() => {
    // Cleanup existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const eventSource = new EventSource(url);

      eventSource.onopen = () => {
        setConnected(true);
        setReconnectDelay(1);
        lastEventTimeRef.current = Date.now();
        setIsStale(false);
        onConnect?.();
      };

      eventSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const eventKey = `${data.event}:${data.timestamp}`;

          // Duplicate protection
          if (receivedEventsRef.current.has(eventKey)) {
            return;
          }
          receivedEventsRef.current.add(eventKey);

          const event: SSEEvent = {
            event: data.event,
            data: data.data,
            event_id: data.event_id,
            timestamp: data.timestamp,
          };

          setLastEvent(event);
          setEvents((prev) => [...prev.slice(-99), event]); // Keep last 100
          onEvent?.(event);
          lastEventTimeRef.current = Date.now();
        } catch {
          // Invalid JSON, ignore
        }
      };

      eventSource.onerror = () => {
        setConnected(false);
        onDisconnect?.();

        if (reconnect) {
          const delay = Math.min(reconnectDelay * 2, maxReconnectDelay);
          setReconnectDelay(delay);
          reconnectTimerRef.current = setTimeout(connect, delay * 1000);
        }
      };

      eventSourceRef.current = eventSource;
    } catch {
      // EventSource not supported
    }
  }, [url, reconnect, maxReconnectDelay, reconnectDelay, onEvent, onConnect, onDisconnect]);

  // Heartbeat monitoring
  useEffect(() => {
    const interval = setInterval(() => {
      if (connected && lastEventTimeRef.current) {
        const elapsed = (Date.now() - lastEventTimeRef.current) / 1000;
        setIsStale(elapsed > heartbeatTimeout * 2);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [connected, heartbeatTimeout]);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [connect]);

  return {
    connected,
    lastEvent,
    events,
    reconnectDelay,
    isStale,
    reconnect: connect,
  };
}

// ─── Specific hooks ───────────────────────────────────────────────

export function useTaskEvents(taskId: string) {
  return useSSE({
    url: `/api/workforce/sse?task_id=${taskId}`,
    onEvent: (event) => {
      if (event.event.startsWith("task.")) {
        // Handle task events
      }
    },
  });
}

export function useWorkerEvents(workerId: string) {
  return useSSE({
    url: `/api/workforce/sse?worker_id=${workerId}`,
    onEvent: (event) => {
      if (event.event.startsWith("worker.")) {
        // Handle worker events
      }
    },
  });
}

export function useActivityFeed() {
  return useSSE({
    url: "/api/workforce/sse",
    onEvent: (event) => {
      // Handle all events for activity feed
    },
  });
}