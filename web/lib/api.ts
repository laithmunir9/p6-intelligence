import { ComparisonReport, isComparisonReport } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function compareSchedules(before: File, after: File, signal?: AbortSignal): Promise<ComparisonReport> {
  const body = new FormData();
  body.append("before", before);
  body.append("after", after);
  const response = await fetch(`${API_BASE_URL}/v1/compare`, { method: "POST", body, signal });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload as { error?: { code?: string; message?: string } } | null;
    throw new ApiError(error?.error?.code ?? "INTERNAL_ERROR", error?.error?.message ?? "The comparison could not be completed.", response.status);
  }
  if (!isComparisonReport(payload)) throw new ApiError("INTERNAL_ERROR", "The API returned an invalid comparison report.", response.status);
  return payload;
}
