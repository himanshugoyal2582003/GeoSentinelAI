"use client";

import { useState } from "react";
import { ArrowRight, Crosshair, LockKeyhole, Mail, MapPin, Satellite } from "lucide-react";
import Link from "next/link";

type AuthMode = "login" | "signup";

export default function Home() {
  const [mode, setMode] = useState<AuthMode>("login");
  const [notice, setNotice] = useState("");

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setNotice("");
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("Account access is not connected yet. Your credentials were not sent or stored.");
  }

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <header className="auth-header">
          <Link className="auth-brand" href="/" aria-label="GeoSentinel home">
            <span className="auth-brand-mark"><Crosshair size={19} /></span>
            <span>
              <strong>GEOSENTINEL</strong>
              <small>LAND CHANGE INTELLIGENCE</small>
            </span>
          </Link>
          <Link className="auth-demo-link" href="/dashboard">
            VIEW LIVE DEMO <ArrowRight size={14} />
          </Link>
        </header>

        <div className="auth-layout">
          <section className="auth-intro">
            <span className="auth-kicker"><span /> SATELLITE MONITORING FOR YOUR LAND</span>
            <h1>Know what’s changing on the ground.</h1>
            <p className="auth-intro-copy">
              Track land-surface changes with satellite imagery and keep clear, dated evidence in one place.
            </p>

            <div className="auth-benefits">
              <div>
                <span className="auth-benefit-icon"><Satellite size={17} /></span>
                <p><strong>Consistent observation</strong><small>Sentinel-2 imagery revisits approximately every five days.</small></p>
              </div>
              <div>
                <span className="auth-benefit-icon"><MapPin size={17} /></span>
                <p><strong>Changes with context</strong><small>Review mapped findings, dates, and estimated affected area.</small></p>
              </div>
              <div>
                <span className="auth-benefit-icon"><Crosshair size={17} /></span>
                <p><strong>Evidence to verify</strong><small>Use satellite signals to guide review, not as a legal determination.</small></p>
              </div>
            </div>

            <div className="auth-footnote">
              <span className="auth-footnote-line" />
              <span>PUBLIC SATELLITE DATA <b>·</b> HUMAN REVIEW REQUIRED</span>
            </div>
          </section>

          <section className="auth-card" aria-labelledby="auth-title">
            <div className="auth-card-heading">
              <span className="auth-card-kicker">YOUR MONITORING WORKSPACE</span>
              <h2 id="auth-title">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
              <p>{mode === "login" ? "Sign in to continue to your sites." : "Start monitoring the land that matters to you."}</p>
            </div>

            <div className="auth-tabs" role="group" aria-label="Choose sign-in or sign-up">
              <button
                type="button"
                aria-pressed={mode === "login"}
                className={mode === "login" ? "active" : ""}
                onClick={() => changeMode("login")}
              >
                Sign in
              </button>
              <button
                type="button"
                aria-pressed={mode === "signup"}
                className={mode === "signup" ? "active" : ""}
                onClick={() => changeMode("signup")}
              >
                Sign up
              </button>
            </div>

            <form className="auth-form" onSubmit={handleSubmit}>
              {mode === "signup" && (
                <label>
                  <span>FULL NAME</span>
                  <input name="name" type="text" autoComplete="name" placeholder="Your name" required />
                </label>
              )}
              <label>
                <span>EMAIL ADDRESS</span>
                <span className="auth-input-wrap">
                  <Mail size={16} aria-hidden="true" />
                  <input name="email" type="email" autoComplete="email" placeholder="you@example.com" required />
                </span>
              </label>
              <label>
                <span>PASSWORD</span>
                <span className="auth-input-wrap">
                  <LockKeyhole size={16} aria-hidden="true" />
                  <input
                    name="password"
                    type="password"
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    placeholder="At least 8 characters"
                    minLength={8}
                    required
                  />
                </span>
              </label>

              {notice && <p className="auth-notice" role="status">{notice}</p>}

              <button className="auth-submit" type="submit">
                {mode === "login" ? "SIGN IN" : "CREATE ACCOUNT"} <ArrowRight size={16} />
              </button>
            </form>

            <p className="auth-setup-note">
              Account authentication is not configured in this MVP. Form details are not sent or saved.
            </p>
            <div className="auth-divider"><span>OR</span></div>
            <Link className="auth-dashboard-link" href="/dashboard">
              Explore the live dashboard <ArrowRight size={15} />
            </Link>
          </section>
        </div>

        <footer className="auth-footer">
          <span>GEOSENTINEL AI</span>
          <span>Automated land-change signals require field verification.</span>
        </footer>
      </div>
    </main>
  );
}
