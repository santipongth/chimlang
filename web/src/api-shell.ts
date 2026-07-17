import { apiClient } from "./openapi-client";

function apiError(error: unknown, status: number): Error {
  if (error && typeof error === "object" && "detail" in error) {
    return new Error(String((error as { detail: unknown }).detail));
  }
  return new Error(`HTTP ${status}`);
}

/** Shell-only call kept separate so feature APIs stay in lazy route chunks. */
export async function fetchShellUnread(): Promise<number> {
  const { data, error, response } = await apiClient.GET("/watchlists.json");
  if (!response.ok || !data) throw apiError(error, response.status);
  return Number(data.unread ?? 0);
}
