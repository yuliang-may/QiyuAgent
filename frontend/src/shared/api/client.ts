export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T>(url: string, init: RequestInit = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(url, {
      credentials: "include",
      ...init,
    });
  } catch {
    throw new ApiError("无法连接到本地服务，请确认后端仍在运行。", 0);
  }

  const raw = await response.text();
  const payload = raw ? safeJsonParse(raw) : null;

  if (!response.ok) {
    const message = extractErrorMessage(payload, raw);
    throw new ApiError(message, response.status);
  }

  return (payload ?? {}) as T;
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function extractErrorMessage(payload: unknown, raw: string): string {
  if (typeof payload === "object" && payload && "detail" in payload) {
    return stringifyDetail((payload as { detail?: unknown }).detail);
  }
  return raw || "请求失败";
}

function stringifyDetail(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const msg = String((item as { msg?: unknown }).msg || "").trim();
          if (!msg) return "";
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc?: unknown[] }).loc?.slice(1).join(".")
            : "";
          return loc ? `${loc}: ${msg}` : msg;
        }
        return "";
      })
      .filter(Boolean);

    if (messages.length) {
      return messages.join("；");
    }
  }

  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail, null, 2);
    } catch {
      return "请求失败";
    }
  }

  return "请求失败";
}
