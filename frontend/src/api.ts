const API_ORIGIN = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")).replace(/\/$/, "");
const API_ROOT = `${API_ORIGIN}/api/v1`;

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.json().catch(() => null) as { detail?: string | Array<{ msg?: string }> } | null;
  if (response.status === 422) {
    return new ApiError("Revisa los datos: nombre, correo válido, teléfono de 7 a 15 dígitos y contraseña de al menos 10 caracteres.", response.status);
  }
  const detail = typeof body?.detail === "string"
    ? body.detail
    : body?.detail?.map((item) => item.msg).filter(Boolean).join(". ");
  return new ApiError(detail || fallback, response.status);
}

// El servidor gratuito de Render se apaga tras unos minutos sin uso y tarda
// cerca de un minuto en volver a arrancar; también se reinicia si se queda sin
// memoria. Las consultas (GET) se reintentan solas antes de mostrar el error.
// Las peticiones que crean o borran datos no se reintentan para no duplicarlas.
const RETRY_DELAYS_MS = [3000, 8000, 15000];

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function request(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const delays = method === "GET" ? RETRY_DELAYS_MS : [];
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetch(input, init);
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
      if (attempt < delays.length) {
        window.dispatchEvent(new CustomEvent("athletic:api-retrying", { detail: { attempt: attempt + 1 } }));
        await wait(delays[attempt]);
        continue;
      }
      throw new ApiError(
        `No se pudo conectar con el servidor ${API_ORIGIN || "de la aplicación"}. Puede estar iniciándose o reiniciándose: espera un minuto y vuelve a intentarlo.`,
        0,
      );
    }
  }
}

function handleUnauthorized(response: Response): void {
  if (response.status !== 401) return;
  localStorage.removeItem("athletic-token");
  window.dispatchEvent(new Event("athletic:session-expired"));
}

export function accessTokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

function storeAccessToken(token: string): void {
  localStorage.setItem("athletic-token", token);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = localStorage.getItem("athletic-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await request(`${API_ROOT}${path}`, { ...init, headers });
  handleUnauthorized(response);
  if (!response.ok) throw await apiError(response, `Error de API (${response.status})`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiPage<T>(path: string): Promise<{ items: T; total: number }> {
  const headers = new Headers();
  const token = localStorage.getItem("athletic-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await request(`${API_ROOT}${path}`, { headers });
  handleUnauthorized(response);
  if (!response.ok) throw await apiError(response, `Error de API (${response.status})`);
  return { items: await response.json() as T, total: Number(response.headers.get("X-Total-Count") ?? 0) };
}

export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = localStorage.getItem("athletic-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await request(`${API_ROOT}${path}`, { headers });
  handleUnauthorized(response);
  if (!response.ok) throw await apiError(response, "No se pudo descargar el archivo");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function apiBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = localStorage.getItem("athletic-token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await request(`${API_ROOT}${path}`, { headers });
  handleUnauthorized(response);
  if (!response.ok) throw await apiError(response, "No se pudo cargar el recurso");
  return response.blob();
}

export async function login(email: string, password: string): Promise<void> {
  const form = new URLSearchParams({ username: email, password });
  const response = await request(`${API_ROOT}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? "Correo o contraseña incorrectos", response.status);
  }
  const data = await response.json() as { access_token: string };
  storeAccessToken(data.access_token);
}

export async function register(
  fullName: string,
  email: string,
  phone: string,
  password: string,
): Promise<void> {
  const response = await request(`${API_ROOT}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ full_name: fullName, email, phone, password, role: "docente" }),
  });
  if (!response.ok) {
    throw await apiError(response, `Error de API (${response.status})`);
  }
  const data = await response.json() as { access_token: string };
  storeAccessToken(data.access_token);
}
