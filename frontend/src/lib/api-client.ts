/**
 * Fetch wrapper for the FastAPI backend.
 *
 * - The browser always calls the same origin (`/api/v1/...`); Nginx or the Next.js dev
 *   rewrite forwards it to FastAPI, so the refresh cookie stays first-party.
 * - The access token lives only in memory (never localStorage). On a 401 the client
 *   refreshes once (single flight: parallel requests share one refresh) and retries.
 */

export const API_BASE = "/api/v1";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | undefined;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }
}

const NETWORK_ERROR: ApiErrorBody = {
  code: "network_error",
  message: "Server bilan bog‘lanib bo‘lmadi. Internet aloqasini tekshiring.",
};

// --- Token store ------------------------------------------------------------------------

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Called when the session is definitely gone (refresh failed). */
export function onSessionExpired(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export interface TokenResponse {
  access_token: string;
  expires_at: string;
  admin: unknown;
}

/** Exchange the HttpOnly refresh cookie for a new access token. */
export async function refreshSession(): Promise<TokenResponse | null> {
  try {
    const response = await fetch(`${API_BASE}/admin/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      accessToken = null;
      return null;
    }
    const data = (await response.json()) as TokenResponse;
    accessToken = data.access_token;
    return data;
  } catch {
    return null;
  }
}

function refreshOnce(): Promise<boolean> {
  refreshInFlight ??= refreshSession()
    .then((r) => r !== null)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

// --- Requests ---------------------------------------------------------------------------

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as ApiErrorBody).code === "string" &&
    typeof (err as ApiErrorBody).message === "string"
  );
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Resolve these HTTP statuses with their JSON body instead of throwing. */
  acceptStatuses?: number[];
  /** Query string parameters; undefined/null/"" values are skipped. */
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Don't attach the token or refresh (login, refresh itself). */
  anonymous?: boolean;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  // acceptStatuses is handled by the caller; keep it out of the fetch() options.
  const { body, acceptStatuses, query, anonymous, headers, ...init } = options;
  void acceptStatuses;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  try {
    return await fetch(buildUrl(path, query), {
      ...init,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
        ...(!anonymous && accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR);
  }
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);
  if (response.status === 401 && !options.anonymous && (await refreshOnce())) {
    response = await send(path, options);
  }
  if (response.status === 401 && !options.anonymous) {
    listeners.forEach((l) => l());
  }
  const data = await parse(response);
  if (response.ok || options.acceptStatuses?.includes(response.status)) {
    return data as T;
  }
  if (isErrorEnvelope(data)) throw new ApiError(response.status, data.error);
  throw new ApiError(response.status, {
    code: "http_error",
    message: `Kutilmagan javob (HTTP ${response.status}).`,
  });
}

/** Download a file (CSV export) with the current token and save it in the browser. */
export async function downloadFile(path: string, query: RequestOptions["query"]): Promise<void> {
  let response = await send(path, { query });
  if (response.status === 401 && (await refreshOnce())) response = await send(path, { query });
  if (!response.ok) {
    const data = await parse(response);
    if (isErrorEnvelope(data)) throw new ApiError(response.status, data.error);
    throw new ApiError(response.status, { code: "http_error", message: "Faylni yuklab bo‘lmadi." });
  }
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "export.csv";
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
