import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      function send(eventType: string, data: unknown) {
        const payload = `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;
        controller.enqueue(encoder.encode(payload));
      }

      // Send initial connection event
      send("MARKET_STATUS", {
        status: "connected",
        timestamp: new Date().toISOString(),
      });

      // Send periodic market update events (every 30 seconds)
      const interval = setInterval(() => {
        send("MARKET_UPDATE", {
          timestamp: new Date().toISOString(),
          source: "market-events-stream",
        });
      }, 30_000);

      // Cleanup on abort
      request.signal.addEventListener("abort", () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "Access-Control-Allow-Origin": "*",
      "X-Accel-Buffering": "no",
    },
  });
}