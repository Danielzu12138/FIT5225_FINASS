import type { ManagementClient, ManagementResult } from "../manage/ManagementPanel";
import type { QueryClient, QueryMode, QueryResponse } from "../query/QueryPanel";
import type { SubscriptionClient, SubscriptionView } from "../subscriptions/SubscriptionPanel";
import type { MediaResult } from "../library/MediaGallery";
import type {
  UploadReservationRequest,
  UploadReservationResponse,
} from "../upload/UploadPanel";

type ErrorPayload = {
  error?: { message?: unknown };
  message?: unknown;
};

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === "object") {
    const response = payload as ErrorPayload;
    if (typeof response.error?.message === "string") return response.error.message;
    if (typeof response.message === "string") return response.message;
  }
  return `Request failed with status ${status}.`;
}

export class PlatformClient implements QueryClient, ManagementClient, SubscriptionClient {
  constructor(private readonly baseUrl = import.meta.env.VITE_API_BASE_URL ?? "") {}

  search(mode: QueryMode, payload: Record<string, unknown>, accessToken: string): Promise<QueryResponse> {
    return this.json(`/queries/${mode}`, accessToken, "POST", payload);
  }

  async queryByFile(file: File, accessToken: string): Promise<ManagementResult[]> {
    const body = new FormData();
    body.append("file", file);
    const response = await this.request<QueryResponse>("/queries/by-file", accessToken, {
      method: "POST",
      body,
    });
    return response.results;
  }

  reserve(
    payload: UploadReservationRequest,
    accessToken: string,
  ): Promise<UploadReservationResponse> {
    return this.json("/uploads/reservations", accessToken, "POST", payload);
  }

  listMedia(accessToken: string): Promise<{ results: MediaResult[] }> {
    return this.request("/media", accessToken, { method: "GET" });
  }

  updateTags(urls: string[], tags: string[], operation: 0 | 1, accessToken: string): Promise<void> {
    return this.json("/media/tags", accessToken, "POST", { urls, tags, operation });
  }

  deleteMedia(urls: string[], accessToken: string): Promise<void> {
    return this.json("/media", accessToken, "DELETE", { urls });
  }

  async list(accessToken: string): Promise<SubscriptionView[]> {
    const response = await this.request<{ results: SubscriptionView[] }>(
      "/subscriptions",
      accessToken,
      { method: "GET" },
    );
    return response.results;
  }

  create(email: string, tags: string[], accessToken: string): Promise<SubscriptionView> {
    return this.json("/subscriptions", accessToken, "POST", { email, tags });
  }

  update(
    subscriptionId: string,
    email: string,
    tags: string[],
    expectedVersion: number,
    accessToken: string,
  ): Promise<SubscriptionView> {
    return this.json(`/subscriptions/${subscriptionId}`, accessToken, "PUT", {
      email,
      tags,
      expected_version: expectedVersion,
    });
  }

  delete(subscriptionId: string, accessToken: string): Promise<void> {
    return this.request(`/subscriptions/${subscriptionId}`, accessToken, { method: "DELETE" });
  }

  private json<T>(path: string, accessToken: string, method: string, body: unknown): Promise<T> {
    return this.request(path, accessToken, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  private async request<T>(path: string, accessToken: string, init: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...init.headers,
      },
    });
    if (!response.ok) {
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        // A non-JSON error still receives a useful HTTP status message.
      }
      throw new Error(errorMessage(payload, response.status));
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
}
