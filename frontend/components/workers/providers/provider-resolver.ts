import type { WorkerProvider, WorkerProviderId } from "../worker-types";
import { CursorProvider } from "./cursor-provider";
import { HermesProvider } from "./hermes-provider";

export function resolveWorkerProvider(id: WorkerProviderId, repoRoot: string): WorkerProvider {
  if (id === "cursor") return new CursorProvider(repoRoot);
  if (id === "hermes") return new HermesProvider();
  throw new Error(`Worker provider not registered: ${id}`);
}
