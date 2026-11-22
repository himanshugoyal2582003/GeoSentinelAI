"use client";

const TOKEN_KEY = "geosentinel_token";
const USER_KEY = "geosentinel_user";
const LAST_ACTIVE_KEY = "geosentinel_last_active";
const IDLE_LIMIT_MS = 15 * 60 * 1000; // 15 minutes

export interface AuthUser {
  username: string;
  token: string;
  idleTimeoutSeconds: number;
  loginTime: number;
}

export function saveAuthSession(data: { access_token: string; username: string; idle_timeout_seconds: number }) {
  if (typeof window === "undefined") return;
  const user: AuthUser = {
    username: data.username,
    token: data.access_token,
    idleTimeoutSeconds: data.idle_timeout_seconds || 900,
    loginTime: Date.now(),
  };
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.setItem(LAST_ACTIVE_KEY, String(Date.now()));
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function recordActivity() {
  if (typeof window === "undefined") return;
  localStorage.setItem(LAST_ACTIVE_KEY, String(Date.now()));
}

export function isSessionIdle(): boolean {
  if (typeof window === "undefined") return false;
  const lastActive = Number(localStorage.getItem(LAST_ACTIVE_KEY) || 0);
  if (!lastActive) return false;
  return Date.now() - lastActive > IDLE_LIMIT_MS;
}

export function clearAuthSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(LAST_ACTIVE_KEY);
}
