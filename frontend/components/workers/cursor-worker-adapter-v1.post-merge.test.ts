import { describe, expect, it } from "node:test";

import { buildCursorTaskPacket } from "./cursor-worker-adapter-v1";

describe("Cursor worker adapter post-merge contracts", () => {
  it("builds deterministic packets with explicit target paths", () => {
    const input = {
      runId: "run-001",
      taskId: "task-001",
      title: "Harden worker validation",
      instructions: "Improve validation without changing execution policy.",
      targetPaths: ["frontend/components/workers"],
      validationCommand: "npm test",
    };
    const first = buildCursorTaskPacket(input);
    const second = buildCursorTaskPacket(input);

    expect(first.jobId).toBe(second.jobId);
    expect(first.targetPaths).toEqual(["frontend/components/workers"]);
    expect(first.metadata).toBeUndefined();
  });

  it("keeps mutation authority explicitly disabled when metadata is supplied", () => {
    const packet = buildCursorTaskPacket({
      runId: "run-002",
      taskId: "task-002",
      title: "Research-only worker task",
      instructions: "Return a bounded patch for review.",
      targetPaths: ["frontend"],
      metadata: {
        mutationAuthorized: false,
        automaticPr: false,
        automaticMerge: false,
      },
    });

    expect(packet.metadata).toEqual({
      mutationAuthorized: false,
      automaticPr: false,
      automaticMerge: false,
    });
  });
});
