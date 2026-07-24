import { describe, expect, test } from "vitest";

import type { InsuranceAnalysis } from "../../analysis/store";
import {
  initialUploadWorkflowState,
  isUploadInFlight,
  uploadWorkflowReducer,
} from "./state";

const analysis = {
  generatedAt: "2030-01-01T00:00:00.000Z",
  portfolioSessionToken: "portfolio-token",
  portfolioSessionExpiresAt: "2030-01-02T00:00:00.000Z",
  counselTurnsRemaining: 10,
  insuranceDocuments: [],
} satisfies InsuranceAnalysis;

describe("uploadWorkflowReducer", () => {
  test("tracks upload progress only while the upload is active", () => {
    const preparing = uploadWorkflowReducer(initialUploadWorkflowState, {
      type: "start",
      total: 2,
    });
    const uploading = uploadWorkflowReducer(preparing, {
      type: "server-ready",
    });
    const progressed = uploadWorkflowReducer(uploading, { type: "uploaded" });

    expect(preparing).toMatchObject({
      phase: "preparing-server",
      analysisProgress: { completed: 0, total: 2 },
    });
    expect(progressed).toMatchObject({
      phase: "uploading",
      analysisProgress: { completed: 1, total: 2 },
    });
    expect(isUploadInFlight(preparing)).toBe(true);
    expect(isUploadInFlight(progressed)).toBe(true);
    expect(
      uploadWorkflowReducer(initialUploadWorkflowState, { type: "uploaded" }),
    ).toBe(initialUploadWorkflowState);
  });

  test("restores name selection when its document cleanup fails", () => {
    const selectingName = uploadWorkflowReducer(
      uploadWorkflowReducer(
        uploadWorkflowReducer(initialUploadWorkflowState, {
          type: "start",
          total: 2,
        }),
        { type: "server-ready" },
      ),
      {
        type: "require-name-selection",
        analysis,
        selectedName: "테스트고객",
      },
    );
    const completing = uploadWorkflowReducer(selectingName, {
      type: "begin-completion",
    });
    const restored = uploadWorkflowReducer(completing, {
      type: "return-to-name-selection",
    });

    expect(restored).toMatchObject({
      phase: "name-selection",
      pendingAnalysis: analysis,
      selectedName: "테스트고객",
    });
    expect(isUploadInFlight(completing)).toBe(true);
    expect(isUploadInFlight(restored)).toBe(false);
  });

  test("clears pending name selection when the user replaces selected files", () => {
    const selectingName = uploadWorkflowReducer(
      uploadWorkflowReducer(
        uploadWorkflowReducer(initialUploadWorkflowState, {
          type: "start",
          total: 2,
        }),
        { type: "server-ready" },
      ),
      {
        type: "require-name-selection",
        analysis,
        selectedName: "테스트고객",
      },
    );

    expect(uploadWorkflowReducer(selectingName, { type: "reset" })).toBe(
      initialUploadWorkflowState,
    );
  });
});
