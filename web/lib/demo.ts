const DEMO_FILES = {
  before: "/demo/substation-before.xer",
  after: "/demo/substation-after.xer",
} as const;

export async function loadDemoFiles(fetcher: typeof fetch = fetch): Promise<{ before: File; after: File }> {
  const entries = await Promise.all(
    Object.entries(DEMO_FILES).map(async ([side, path]) => {
      const response = await fetcher(path);
      if (!response.ok) throw new Error(`The synthetic demo file could not be loaded (${response.status}).`);
      const blob = await response.blob();
      return [side, new File([blob], `synthetic-${side}.xer`, { type: "application/octet-stream" })] as const;
    }),
  );
  return Object.fromEntries(entries) as { before: File; after: File };
}

export const DEMO_LABEL = "Synthetic demo schedule";
