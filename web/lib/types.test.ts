import { describe, expect, it } from "vitest";
import { activityLabel, isComparisonReport } from "./types";

describe("schema contract helpers", () => {
  it("accepts a minimally shaped ComparisonReport", () => {
    expect(isComparisonReport({
      schema_version: "1.0",
      comparison: { before: {}, after: {} },
      projects: [],
      warnings: [],
      evidence: {},
    })).toBe(true);
  });

  it("accepts the enriched 1.1 report version", () => {
    expect(isComparisonReport({ schema_version: "1.1", projects: [], evidence: {} })).toBe(true);
  });

  it("rejects unknown or missing report versions", () => {
    expect(isComparisonReport({ schema_version: "2.0", projects: [], evidence: {} })).toBe(false);
    expect(isComparisonReport(null)).toBe(false);
  });

  it("uses returned change values for the activity label", () => {
    expect(activityLabel({
      before_activity_id: "A100",
      after_activity_id: "A100",
      status: "MODIFIED",
      confidence: 1,
      changes: { task_name: { before: "Excavate", after: "Excavate footings" } },
      evidence_refs: [],
    })).toBe("Excavate footings");
  });

  it("does not mistake date changes for an activity name", () => {
    expect(activityLabel({
      before_activity_id: "A101",
      after_activity_id: "A101",
      status: "MODIFIED",
      confidence: 1,
      changes: { start_date: { before: "2026-01-01", after: "2026-01-02" } },
      evidence_refs: [],
    })).toBe("A101");
  });
});
