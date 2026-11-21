"use client";

import Link from "next/link";
import { ArrowRight, ArrowUpRight, Crosshair, Waves } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import SatelliteComparePreview from "./components/SatelliteComparePreview";

export default function HomePage() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <main className="landing-shell">
      <header className="landing-header">
        <Link className="landing-brand" href="/" aria-label="GeoSentinel home">
          <span className="brand-mark"><Crosshair size={19} /></span>
          <span className="landing-brand-copy"><strong>GeoSentinel AI</strong><small>Monitoring command center</small></span>
        </Link>
        <nav className="landing-nav" aria-label="Main navigation">
          <Link className="landing-nav-link" href="/pricing">Pricing</Link>
          <Link className="landing-nav-link" href="/dashboard">Open dashboard <ArrowUpRight size={15} /></Link>
        </nav>
      </header>

      <motion.section
        className="hero landing-hero"
        initial={prefersReducedMotion ? false : { opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="hero-message">
          <p className="eyebrow">The change sentinel / T8.1</p>
          <h1>From satellite pixels<br /><em>to actionable intelligence.</em></h1>
          <p className="hero-copy">Detecting suspicious land-use change before it disappears into the landscape.</p>
          <div className="landing-actions">
            <Link className="landing-primary" href="/pricing#free-audit">Request free site audit <ArrowRight size={16} /></Link>
            <a className="landing-secondary" href="#comparison">See scene comparison</a>
          </div>
        </div>
        <div className="landing-window">
          <Waves size={16} />
          <span>Monitoring window</span>
          <strong>Historical <b>to</b> recent</strong>
          <small>Sentinel-2 scene pair</small>
        </div>
      </motion.section>

      <section className="landing-meta" aria-label="Monitoring setup">
        <div><span>Region</span><strong>Pune quarry belt</strong></div>
        <div><span>Sensor</span><strong>Sentinel-2 / 10 m</strong></div>
        <div><span>Detection mode</span><strong>ChangeCNN + differencing</strong></div>
        <div><span>Scheduled site checks</span><strong>At least 5 days apart</strong></div>
        <Link href="/dashboard">Dashboard <ArrowUpRight size={14} /></Link>
      </section>

      <SatelliteComparePreview />

      <footer className="landing-footer">
        <span>GeoSentinel / Pune region</span>
        <span>Detection is an intelligence signal; verify field conditions before enforcement.</span>
        <Link href="/pricing">Pricing & free audit <ArrowUpRight size={14} /></Link>
      </footer>
    </main>
  );
}
