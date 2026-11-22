const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE}/${path.replace(/^\/+/, "")}`;
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  // ngrok's free endpoint warning page otherwise intercepts browser fetch requests.
  headers.set("ngrok-skip-browser-warning", "true");
  return fetch(apiUrl(path), { ...init, headers });
}
