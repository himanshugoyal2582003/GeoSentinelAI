"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  Crosshair,
  Eye,
  EyeOff,
  Lock,
  Shield,
  User,
  CheckCircle2,
} from "lucide-react";
import { getStoredUser, saveAuthSession } from "../lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    // If already authenticated, redirect to dashboard
    const user = getStoredUser();
    if (user && user.token) {
      router.push("/dashboard");
    }
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Please enter both username and password.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          password,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Authentication failed. Invalid username or password.");
      }

      const data = await res.json();
      saveAuthSession(data);
      setSuccess(true);
      setTimeout(() => {
        router.push("/dashboard");
      }, 700);
    } catch (err: any) {
      setError(err.message || "Could not reach authentication server.");
    } finally {
      setLoading(false);
    }
  }

  function fillDemo() {
    setUsername("admin");
    setPassword("geosentinel-admin");
    setError("");
  }

  return (
    <main style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <header className="topbar">
        <Link href="/" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="brand-mark">
            <Crosshair size={20} />
          </div>
          <div>
            <strong>GEOSENTINEL</strong>
            <span>AI MONITORING COMMAND CENTER</span>
          </div>
        </Link>
        <div className="top-actions">
          <Link href="/" className="dashboard-home-link">Home</Link>
          <Link href="/dashboard" className="dashboard-home-link">Dashboard</Link>
        </div>
      </header>

      <div style={{ flex: 1, display: "grid", placeItems: "center", padding: "48px 16px" }}>
        <div
          style={{
            width: "100%",
            maxWidth: "460px",
            background: "#fff",
            border: "1px solid var(--line)",
            boxShadow: "0 12px 32px rgba(23, 32, 31, 0.06)",
            padding: "36px 32px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--dark)",
                color: "var(--green)",
                width: "28px",
                height: "28px",
              }}
            >
              <Shield size={16} />
            </span>
            <span className="eyebrow" style={{ margin: 0 }}>AUTHORIZATION GATEWAY</span>
          </div>

          <h2 style={{ margin: "4px 0 10px", fontSize: "24px", fontWeight: 600, letterSpacing: "-0.01em" }}>
            Officer Sign In
          </h2>
          <p style={{ margin: "0 0 24px", color: "var(--muted)", fontSize: "14px", lineHeight: "1.4" }}>
            Authenticate with secure session token to access model controls and case management.
          </p>

          {error && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                color: "#991b1b",
                padding: "12px 14px",
                marginBottom: "20px",
                fontSize: "13px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div
              style={{
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                color: "#166534",
                padding: "12px 14px",
                marginBottom: "20px",
                fontSize: "13px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <CheckCircle2 size={16} />
              <span>Authentication verified! Redirecting to command dashboard...</span>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label
                htmlFor="username"
                className="control-label"
                style={{ display: "block", marginBottom: "6px", fontSize: "11px" }}
              >
                OFFICER USERNAME
              </label>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "12px", top: "12px", color: "var(--muted)" }}>
                  <User size={16} />
                </span>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  required
                  style={{
                    width: "100%",
                    padding: "10px 14px 10px 38px",
                    border: "1px solid var(--line)",
                    background: "var(--paper)",
                    fontSize: "14px",
                    fontFamily: "inherit",
                    outline: "none",
                  }}
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="control-label"
                style={{ display: "block", marginBottom: "6px", fontSize: "11px" }}
              >
                SECURITY PASSWORD
              </label>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: "12px", top: "12px", color: "var(--muted)" }}>
                  <Lock size={16} />
                </span>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  style={{
                    width: "100%",
                    padding: "10px 42px 10px 38px",
                    border: "1px solid var(--line)",
                    background: "var(--paper)",
                    fontSize: "14px",
                    fontFamily: "inherit",
                    outline: "none",
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: "absolute",
                    right: "12px",
                    top: "10px",
                    background: "transparent",
                    border: "none",
                    color: "var(--muted)",
                    padding: "2px",
                  }}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || success}
              style={{
                marginTop: "8px",
                background: "var(--dark)",
                color: "#fff",
                border: "none",
                padding: "12px 18px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                fontWeight: 600,
                fontSize: "14px",
                cursor: loading || success ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
              }}
            >
              <span>{loading ? "AUTHENTICATING..." : "SIGN IN TO COMMAND CENTER"}</span>
              <ArrowRight size={16} />
            </button>
          </form>

          <div
            style={{
              marginTop: "24px",
              paddingTop: "20px",
              borderTop: "1px dashed var(--line)",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="eyebrow">DEMO CREDENTIALS</span>
              <button
                type="button"
                onClick={fillDemo}
                style={{
                  background: "#eef3d7",
                  border: "1px solid #879b1b",
                  color: "#526412",
                  padding: "4px 8px",
                  fontSize: "11px",
                  fontFamily: "'DM Mono', monospace",
                  cursor: "pointer",
                }}
              >
                1-CLICK FILL
              </button>
            </div>
            <div
              style={{
                background: "var(--paper)",
                padding: "8px 12px",
                fontSize: "12px",
                fontFamily: "'DM Mono', monospace",
                color: "var(--dark)",
                border: "1px solid var(--line)",
              }}
            >
              User: <code>admin</code> | Pass: <code>geosentinel-admin</code>
            </div>

            <p style={{ margin: "4px 0 0", fontSize: "11px", color: "var(--muted)", lineHeight: "1.4" }}>
              <strong>Idle Protection:</strong> Inactivity exceeding 15 minutes triggers automatic token invalidation to protect unmonitored field consoles.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
