import { describe, expect, it, vi } from "vitest";
import { DEMO_LABEL, loadDemoFiles } from "./demo";

describe("synthetic demo loader", () => {
  it("loads both XER sides as files without using a fake report", async () => {
    const fetcher = vi.fn(async (path: string) => new Response(`demo-${path}`, { status: 200 }));
    const result = await loadDemoFiles(fetcher as typeof fetch);
    expect(DEMO_LABEL).toBe("Synthetic demo schedule");
    expect(result.before.name).toBe("synthetic-before.xer");
    expect(result.after.name).toBe("synthetic-after.xer");
    expect(fetcher).toHaveBeenCalledWith("/demo/substation-before.xer");
    expect(fetcher).toHaveBeenCalledWith("/demo/substation-after.xer");
  });

  it("surfaces a clean loading error", async () => {
    await expect(loadDemoFiles(async () => new Response(null, { status: 503 }))).rejects.toThrow("could not be loaded");
  });
});
