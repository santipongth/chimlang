import createClient from "openapi-fetch";
import type { paths } from "./openapi.generated";
import type { SimRunDetail, ValidationReport } from "./api";

export const apiClient = createClient<paths>({ baseUrl: "" });

function message(error: unknown, status: number): string {
  if (error && typeof error === "object" && "detail" in error) {
    return String((error as { detail: unknown }).detail);
  }
  return `HTTP ${status}`;
}

export async function getRunDetailTyped(runId: string): Promise<SimRunDetail> {
  const { data, error, response } = await apiClient.GET("/runs/{run_id}.json", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw new Error(message(error, response.status));
  return data as unknown as SimRunDetail;
}

export async function getValidationTyped(runId: string): Promise<ValidationReport> {
  const { data, error, response } = await apiClient.GET("/runs/{run_id}/validation", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw new Error(message(error, response.status));
  return data as unknown as ValidationReport;
}
