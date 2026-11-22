"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowUpRight, CalendarDays, Crosshair, FileText, MapPin, Upload, Waves, BrainCircuit, Trash2, Pencil, Save } from "lucide-react";
import type { Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";
import { getStoredUser, clearAuthSession, recordActivity, isSessionIdle, type AuthUser } from "../lib/auth";

const LIVE_SCAN_INTERVAL_MS = 30 * 60 * 1000;

type Finding = {
  id: string;
  label: string;
  severity: "high" | "medium" | "low";
  confidence: number;
  areaSqm: number;
  coordinates: [number, number];
  changeType: string;
  firstObserved: string;
  lastObserved: string;
  status: string;
  areaName?: string;
  regionBbox?: [number, number, number, number];
  detectionErrorSqm?: number;
  modelScore?: number;
  miningFootprintProbability?: number;
  googleMapsUrl?: string;
  googleSatelliteUrl?: string;
};

type SiteGeometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };

type MonitoringSite = {
  siteId: string;
  name: string;
  geometry: SiteGeometry;
  bbox: [number, number, number, number];
  active: boolean;
};

type Dataset = {
  scanId?: string;
  mode: string;
  region: string;
  historicalDate: string;
  recentDate: string;
  findings: Finding[];
  summary: {
    changedAreaSqm: number;
    changedAreaHa: number;
    highRiskCount: number;
    averageConfidence: number;
  };
  timeline: { month: string; areaSqm: number }[];
  areaBreakdown?: { label: string; areaSqm: number; severity: "high" | "medium" | "low" }[];
  timelineNote?: string;
  source?: {
    bbox: number[];
    historicalImage: string;
    recentImage: string;
    provider: string;
    note: string;
    stale?: boolean;
    cacheAgeSeconds?: number;
    sceneCount?: number;
    geometry?: SiteGeometry;
    siteId?: string;
  };
  regionId?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function parseApiError(response: Response, defaultMessage: string): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || data.message || defaultMessage;
  } catch {
    return response.statusText ? `${defaultMessage} (${response.status} ${response.statusText})` : defaultMessage;
  }
}

function resolveImageUrl(path: string | undefined): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("data:")) return path;
  return `${API}${path.startsWith("/") ? "" : "/"}${path}`;
}

function getSatelliteUrl(finding: Finding): string {
  if (finding.googleSatelliteUrl) return finding.googleSatelliteUrl;
  return `https://www.google.com/maps/@${finding.coordinates[0]},${finding.coordinates[1]},17z/data=!3m1!1e3`;
}

export default function Home() {
  const [data, setData] = useState<Dataset | null>(null);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [liveScanning, setLiveScanning] = useState(false);
  const [reportTemplate, setReportTemplate] = useState<"quarry-compliance" | "landowner-evidence">("quarry-compliance");
  const [reportBrandName, setReportBrandName] = useState("");
  const [generatingReport, setGeneratingReport] = useState(false);
  const [nextScanAt, setNextScanAt] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [sites, setSites] = useState<MonitoringSite[]>([]);
  const [siteName, setSiteName] = useState("");
  const [siteGeometry, setSiteGeometry] = useState<SiteGeometry | null>(null);
  const [siteDrawMode, setSiteDrawMode] = useState(false);
  const [siteBusy, setSiteBusy] = useState(false);
  const [siteError, setSiteError] = useState("");
  const [siteLoadAttempt, setSiteLoadAttempt] = useState(0);
  const [siteLoading, setSiteLoading] = useState(false);
  const [mineTraining, setMineTraining] = useState(false);
  const [mineTrainingMessage, setMineTrainingMessage] = useState("");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const waitingForDashboard = loading || (liveScanning && !data);

  function handleLogout() {
    clearAuthSession();
    setAuthUser(null);
  }

  function applyLiveResult(value: Dataset) {
    setData(value);
    setSelected(value.findings[0] || null);
    const cacheAgeMs = (value.source?.cacheAgeSeconds || 0) * 1000;
    const refreshDelayMs =
      value.source?.stale && cacheAgeMs >= LIVE_SCAN_INTERVAL_MS
        ? LIVE_SCAN_INTERVAL_MS
        : Math.max(0, LIVE_SCAN_INTERVAL_MS - cacheAgeMs);
    setNextScanAt(Date.now() + refreshDelayMs);
  }

  useEffect(() => {
    fetch(`${API}/api/live-detect`)
      .then((response) => {
        if (!response.ok) throw new Error("Live satellite feed unavailable.");
        return response.json();
      })
      .then((value: Dataset) => {
        applyLiveResult(value);
        setLoading(false);
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "Live satellite feed unavailable.");
        setNextScanAt(Date.now() + LIVE_SCAN_INTERVAL_MS);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let active = true;
    setSiteLoading(true);
    setSiteError("");
    fetch(`${API}/api/sites`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await parseApiError(response, "Could not load monitoring sites."));
        return response.json() as Promise<{ sites: MonitoringSite[] }>;
      })
      .then((value) => {
        if (active) setSites(value.sites);
      })
      .catch((reason) => {
        if (active) {
          setSiteError(
            reason instanceof TypeError
              ? `Cannot reach the API at ${API}. Check that the backend is running and CORS allows ${window.location.origin}.`
              : reason instanceof Error
                ? reason.message
                : "Could not load monitoring sites.",
          );
        }
      })
      .finally(() => {
        if (active) setSiteLoading(false);
      });
    return () => {
      active = false;
    };
  }, [siteLoadAttempt]);

  useEffect(() => {
    if (liveScanning || nextScanAt === null) return;
    const timer = window.setTimeout(() => {
      void runLiveScan();
    }, Math.max(0, nextScanAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [liveScanning, nextScanAt]);

  useEffect(() => {
    setAuthUser(getStoredUser());
    const onActivity = () => recordActivity();
    window.addEventListener("mousemove", onActivity);
    window.addEventListener("keydown", onActivity);
    window.addEventListener("click", onActivity);

    const idleTimer = window.setInterval(() => {
      if (getStoredUser() && isSessionIdle()) {
        clearAuthSession();
        setAuthUser(null);
        setError("Your officer session expired due to 15 minutes of idle inactivity. Please log in again.");
      }
    }, 10000);

    return () => {
      window.removeEventListener("mousemove", onActivity);
      window.removeEventListener("keydown", onActivity);
      window.removeEventListener("click", onActivity);
      window.clearInterval(idleTimer);
    };
  }, []);

  const maxArea = useMemo(() => {
    const areas = data?.timeline?.map((item) => item.areaSqm) || [];
    return areas.length ? Math.max(...areas, 1) : 1;
  }, [data]);

  const chartHeight = (area: number) => (area && maxArea > 0 ? Math.max(18, Math.sqrt(area / maxArea) * 150) : 18);

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length < 2) {
      setError("Please select at least 2 satellite images (historical and recent).");
      if (event.target) event.target.value = "";
      return;
    }
    const body = new FormData();
    body.append("historical", files[0]);
    body.append("recent", files[1]);
    setUploading(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/detect`, { method: "POST", body });
      if (!response.ok) {
        throw new Error(await parseApiError(response, "Detection failed"));
      }
      const value = (await response.json()) as Dataset;
      applyLiveResult(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Detection failed");
    } finally {
      setUploading(false);
      if (event.target) event.target.value = "";
    }
  }

  async function importSiteFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setSiteDrawMode(false);
    setSiteGeometry(null);
    const form = new FormData();
    form.append("name", siteName.trim() || file.name.replace(/\.(kml|geojson|json)$/i, ""));
    form.append("file", file);
    setSiteBusy(true);
    setSiteError("");
    try {
      const response = await fetch(`${API}/api/sites/import`, { method: "POST", body: form });
      if (!response.ok) throw new Error(await parseApiError(response, "Site import failed."));
      const site = (await response.json()) as MonitoringSite;
      setSites((current) => [...current, site].sort((a, b) => a.name.localeCompare(b.name)));
      setSiteName("");
      setSiteGeometry(null);
    } catch (reason) {
      setSiteError(reason instanceof Error ? reason.message : "Site import failed.");
    } finally {
      setSiteBusy(false);
      event.target.value = "";
    }
  }

  async function saveDrawnSite() {
    if (!siteGeometry) {
      setSiteError("Draw a polygon or import a KML/GeoJSON file first.");
      return;
    }
    setSiteBusy(true);
    setSiteError("");
    try {
      const response = await fetch(`${API}/api/sites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: siteName, geometry: siteGeometry }),
      });
      if (!response.ok) throw new Error(await parseApiError(response, "Could not save monitoring site."));
      const site = (await response.json()) as MonitoringSite;
      setSites((current) => [...current, site].sort((a, b) => a.name.localeCompare(b.name)));
      setSiteName("");
      setSiteGeometry(null);
    } catch (reason) {
      setSiteError(reason instanceof Error ? reason.message : "Could not save monitoring site.");
    } finally {
      setSiteBusy(false);
    }
  }

  async function scanSite(siteId: string) {
    setLiveScanning(true);
    setSiteBusy(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/sites/${encodeURIComponent(siteId)}/scan`, { method: "POST" });
      if (!response.ok) throw new Error(await parseApiError(response, "Monitoring-site scan failed."));
      applyLiveResult((await response.json()) as Dataset);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Monitoring-site scan failed.");
    } finally {
      setLiveScanning(false);
      setSiteBusy(false);
    }
  }

  async function removeSite(siteId: string) {
    setSiteBusy(true);
    setSiteError("");
    try {
      const response = await fetch(`${API}/api/sites/${encodeURIComponent(siteId)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await parseApiError(response, "Could not remove monitoring site."));
      setSites((current) => current.filter((site) => site.siteId !== siteId));
    } catch (reason) {
      setSiteError(reason instanceof Error ? reason.message : "Could not remove monitoring site.");
    } finally {
      setSiteBusy(false);
    }
  }

  function handleDrawnGeometry(geometry: SiteGeometry | null) {
    setSiteGeometry(geometry);
    setSiteDrawMode(false);
    if (geometry) setSiteError("");
  }

  async function runLiveScan() {
    setLiveScanning(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/live-detect`);
      if (!response.ok) {
        throw new Error(await parseApiError(response, "Live scan failed"));
      }
      const value = (await response.json()) as Dataset;
      applyLiveResult(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Live scan failed");
      setNextScanAt(Date.now() + LIVE_SCAN_INTERVAL_MS);
    } finally {
      setLiveScanning(false);
    }
  }

  async function trainMineModel() {
    setMineTraining(true);
    setMineTrainingMessage("Starting public mine footprint training...");
    try {
      const response = await fetch(`${API}/api/train/mining`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await parseApiError(response, "Mine footprint training could not start."));
      }
      let state = (await response.json()) as { status: string; message: string; output?: string };
      setMineTrainingMessage(state.message);
      let attempts = 0;
      while (state.status === "running" && attempts < 600) {
        attempts++;
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const statusResponse = await fetch(`${API}/api/train/mining`);
        if (!statusResponse.ok) {
          throw new Error(await parseApiError(statusResponse, "Could not read mine footprint training status"));
        }
        state = (await statusResponse.json()) as { status: string; message: string; output?: string };
        setMineTrainingMessage(state.message);
      }
      if (state.status === "failed") throw new Error([state.message, state.output].filter(Boolean).join("\n"));
      if (state.status === "running") setMineTrainingMessage("Training is still running. Check the backend status for the result.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Mine footprint training failed");
    } finally {
      setMineTraining(false);
    }
  }

  async function downloadReport() {
    if (!selected || !data) return;
    if (!data.scanId) {
      setError("A persisted scan is required to generate a PDF report. Run a new scan and try again.");
      return;
    }

    setGeneratingReport(true);
    setError("");
    try {
      const query = new URLSearchParams({
        template: reportTemplate,
        brand_name: reportBrandName.trim() || "GeoSentinel AI",
        finding_id: selected.id,
      });
      const response = await fetch(
        `${API}/api/scans/${encodeURIComponent(data.scanId)}/report.pdf?${query.toString()}`,
      );
      if (!response.ok) {
        throw new Error(await parseApiError(response, "Could not generate the PDF report"));
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${selected.id.replace(/[^A-Za-z0-9_-]/g, "-")}-${reportTemplate}.pdf`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "PDF report generation failed");
    } finally {
      setGeneratingReport(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Crosshair size={20} />
          </div>
          <div>
            <strong>GEOSENTINEL</strong>
            <span>AI MONITORING COMMAND CENTER</span>
          </div>
        </div>
        <div className="top-actions">
          <a className="dashboard-home-link" href="/">Overview</a>
          <span className="live-dot" /> {waitingForDashboard || liveScanning ? "SCANNING SATELLITE FEED" : "SYSTEM OPERATIONAL"}
          <button className="live-button" onClick={runLiveScan} disabled={waitingForDashboard || liveScanning}>
            <Waves size={15} /> {waitingForDashboard || liveScanning ? "SCANNING..." : "LIVE SATELLITE SCAN"}
          </button>
          <button className="live-button" onClick={trainMineModel} disabled={mineTraining || waitingForDashboard}>
            <BrainCircuit size={15} /> {mineTraining ? "TRAINING MINE MODEL..." : "TRAIN MINE MODEL"}
          </button>
          <label className={`upload-button ${uploading || waitingForDashboard ? "disabled" : ""}`}>
            <Upload size={15} /> {uploading ? "PROCESSING..." : "UPLOAD PAIR"}
            <input type="file" accept="image/*" multiple onChange={handleUpload} disabled={uploading || waitingForDashboard} />
          </label>
          {authUser ? (
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                padding: "6px 12px",
                fontSize: "11px",
                color: "#166534",
                fontFamily: "'DM Mono', monospace",
              }}
            >
              <span>OFFICER: <strong>{authUser.username}</strong></span>
              <button
                type="button"
                onClick={handleLogout}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#991b1b",
                  textDecoration: "underline",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: "10px",
                }}
              >
                LOGOUT
              </button>
            </div>
          ) : (
            <a
              href="/login"
              style={{
                border: "1px solid var(--line)",
                background: "#fff",
                color: "var(--dark)",
                padding: "8px 12px",
                fontSize: "11px",
                fontFamily: "'DM Mono', monospace",
                textDecoration: "none",
                letterSpacing: ".06em",
              }}
            >
              OFFICER LOGIN
            </a>
          )}
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">THE CHANGE SENTINEL / LIVE OPERATIONS</p>
          <h1>
            From satellite pixels
            <br />
            <em>to actionable intelligence.</em>
          </h1>
          <p className="hero-copy">Detecting suspicious land-use change before it disappears into the landscape.</p>
        </div>
        <div className="scan-status">
          <Waves size={16} />
          <span>MONITORING WINDOW</span>
          <strong>
            {data ? (
              <>
                {data.historicalDate} <b>→</b> {data.recentDate}
              </>
            ) : waitingForDashboard ? (
              "Awaiting live scan"
            ) : (
              "No scan available"
            )}
          </strong>
        </div>
      </section>

      {waitingForDashboard && (
        <section className="dashboard-loading" role="status" aria-live="polite">
          <span className="loading-spinner" aria-hidden="true" />
          <div>
            <strong>Preparing your dashboard</strong>
            <p>The hero is ready. Live satellite findings will appear here when the scan completes.</p>
          </div>
        </section>
      )}

      {error && (
        <div className="error">
          <AlertTriangle size={17} /> {error}
          <button className="retry-button" onClick={runLiveScan}>
            RETRY LIVE SCAN
          </button>
        </div>
      )}

      {mineTrainingMessage && (
        <div className="cache-note">
          <BrainCircuit size={16} /> {mineTrainingMessage}
        </div>
      )}

      <section className="site-manager">
        <div className="site-manager-heading">
          <div>
            <span className="eyebrow">CUSTOM AREAS OF INTEREST</span>
            <h2>Monitoring sites</h2>
            <p>Import a KML/GeoJSON boundary or draw a polygon on the map, then scan within that site.</p>
          </div>
          <span className="site-count">{sites.length} SAVED</span>
        </div>
        <div className="site-form">
          <input
            aria-label="Monitoring site name"
            value={siteName}
            onChange={(event) => setSiteName(event.target.value)}
            maxLength={120}
            placeholder="Site name"
          />
          <button
            className={`site-action ${siteDrawMode ? "active" : ""}`}
            onClick={() => {
              setSiteDrawMode((current) => !current);
              setSiteGeometry(null);
              setSiteError("");
            }}
            disabled={siteBusy}
          >
            <Pencil size={14} /> {siteDrawMode ? "CANCEL DRAWING" : "DRAW ON MAP"}
          </button>
          <label className={`site-action site-import ${siteBusy ? "disabled" : ""}`}>
            <Upload size={14} /> IMPORT KML / GEOJSON
            <input type="file" accept=".kml,.geojson,.json" onChange={importSiteFile} disabled={siteBusy} />
          </label>
          <button className="site-action primary" onClick={saveDrawnSite} disabled={siteBusy || !siteGeometry}>
            <Save size={14} /> SAVE SITE
          </button>
        </div>
        {siteDrawMode && <p className="site-hint">Click at least three boundary points on the map below, then finish the polygon.</p>}
        {siteGeometry && <p className="site-hint">Polygon ready. Add a name and select SAVE SITE.</p>}
        {siteError && (
          <div className="site-error-row" role="alert">
            <p className="site-error">{siteError}</p>
            <button
              className="site-action"
              onClick={() => setSiteLoadAttempt((attempt) => attempt + 1)}
              disabled={siteLoading}
            >
              {siteLoading ? "RETRYING..." : "RETRY"}
            </button>
          </div>
        )}
        {!data && (
          <div className="site-draw-map">
            <LiveMap data={null} onSelect={setSelected} drawMode={siteDrawMode} draftGeometry={siteGeometry} onGeometryDrawn={handleDrawnGeometry} />
          </div>
        )}
        <div className="site-list">
          {sites.map((site) => (
            <div className="site-row" key={site.siteId}>
              <span><MapPin size={14} /> {site.name}</span>
              <div>
                <button className="site-action primary" onClick={() => scanSite(site.siteId)} disabled={siteBusy || liveScanning}>
                  <Waves size={13} /> {liveScanning ? "SCANNING..." : "SCAN SITE"}
                </button>
                <button className="site-icon-button" aria-label={`Remove ${site.name}`} onClick={() => removeSite(site.siteId)} disabled={siteBusy}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {sites.length === 0 && !siteError && <p className="site-empty">No custom sites saved yet.</p>}
        </div>
      </section>

      {!waitingForDashboard && data && (
        <>
          <section className="controls">
            <div>
              <span className="control-label">REGION</span>
              <strong>
                <MapPin size={15} /> {data?.region}
              </strong>
            </div>
            <div>
              <span className="control-label">SENSOR</span>
              <strong>Sentinel-2 / 10m</strong>
            </div>
            <div>
              <span className="control-label">DETECTION MODE</span>
              <strong>ChangeCNN + differencing</strong>
            </div>
            <div>
              <span className="control-label">AUTO MONITORING</span>
              <strong>Every 30 minutes</strong>
              <small>{nextScanAt ? `Next scan ${new Date(nextScanAt).toLocaleTimeString()}` : "Starting..."}</small>
            </div>
            <div className="demo-badge">{data?.source ? "LIVE SATELLITE" : "DEMO DATASET"}</div>
          </section>

          {data?.source && (
            <section className="satellite-compare">
              <div className="satellite-head">
                <div>
                  <span className="eyebrow">
                    {data.regionId ? "LIVE EVIDENCE / CUSTOM MONITORING SITE" : "LIVE EVIDENCE / STATIC MONITORING LOCATION"}
                  </span>
                  <h2>Satellite comparison</h2>
                  <p>
                    {data.source.provider} · {data.source.sceneCount || 0} scenes · approximately 5-day Sentinel-2 revisit · BBOX{" "}
                    {data.source.bbox.join(", ")}
                  </p>
                </div>
                <span className="live-tag">{data.source.stale ? "CACHED REAL FEED" : "LIVE FEED"}</span>
              </div>
              <div className="satellite-images">
                <figure>
                  <img src={resolveImageUrl(data.source.historicalImage)} alt="Historical Sentinel-2 scene" />
                  <figcaption>HISTORICAL / {data.historicalDate}</figcaption>
                </figure>
                <div className="compare-arrow">→</div>
                <figure>
                  <img src={resolveImageUrl(data.source.recentImage)} alt="Recent Sentinel-2 scene" />
                  <figcaption>RECENT / {data.recentDate}</figcaption>
                </figure>
              </div>
              {data.source.note && <p className="cache-note">{data.source.note}</p>}
            </section>
          )}

          <section className="kpis">
            <Kpi
              label="CHANGED AREA"
              value={`${data?.summary.changedAreaHa ?? 0} ha`}
              detail={`${(data?.summary.changedAreaSqm ?? 0).toLocaleString()} m² mapped`}
              icon={<ArrowUpRight />}
            />
            <Kpi
              label="HIGH-RISK FINDINGS"
              value={String(data?.summary.highRiskCount ?? 0).padStart(2, "0")}
              detail="Requires field verification"
              icon={<AlertTriangle />}
              alert
            />
            <Kpi
              label="MODEL CONFIDENCE"
              value={`${Math.round((data?.summary.averageConfidence || 0) * 100)}%`}
              detail="Across detected regions"
              icon={<Crosshair />}
            />
            <Kpi
              label="CASE FILES"
              value={String(data?.findings.length ?? 0).padStart(2, "0")}
              detail="Evidence packages ready"
              icon={<FileText />}
            />
          </section>

          <section className="workspace">
            <div className="panel map-panel">
              <div className="panel-head">
                <div>
                  <span className="eyebrow">SPATIAL OVERVIEW</span>
                  <h2>Live change map</h2>
                </div>
                <span className="map-legend">
                  <i className="legend-dot high" /> HIGH RISK <i className="legend-dot medium" /> REVIEW
                </span>
              </div>
              <LiveMap
                data={data}
                onSelect={setSelected}
                drawMode={siteDrawMode}
                draftGeometry={siteGeometry}
                onGeometryDrawn={handleDrawnGeometry}
              />
            </div>

            <div className="panel findings-panel">
              <div className="panel-head">
                <div>
                  <span className="eyebrow">DETECTION QUEUE</span>
                  <h2>
                    Flagged regions <small>{data?.findings.length || 0}</small>
                  </h2>
                </div>
                <button
                  className="text-button"
                  onClick={() => {
                    const list = document.querySelector(".findings-list");
                    list?.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                >
                  VIEW ALL <ArrowUpRight size={14} />
                </button>
              </div>
              <div className="findings-list">
                {(data?.findings || []).map((finding, index) => (
                  <button
                    className={`finding ${selected?.id === finding.id ? "selected" : ""}`}
                    key={finding.id}
                    onClick={() => setSelected(finding)}
                  >
                    <span className={`finding-index ${finding.severity}`}>{String(index + 1).padStart(2, "0")}</span>
                    <span className="finding-main">
                      <strong>{finding.areaName || finding.label}</strong>
                      <small>
                        {finding.changeType} · {finding.coordinates.join(", ")}
                      </small>
                    </span>
                    <span className="finding-area">{(finding.areaSqm / 10000).toFixed(2)} ha</span>
                    <ArrowUpRight size={16} />
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="lower-grid">
            <div className="panel timeline-panel">
              <div className="panel-head">
                <div>
                  <span className="eyebrow">TEMPORAL ANALYSIS</span>
                  <h2>Expansion trajectory</h2>
                </div>
                <span className="unit">AREA / M²</span>
              </div>
              <p className="timeline-note">{data?.timelineNote || "Historical scene baseline compared with the recent scene."}</p>
              <div className="trajectory-chart">
                {(data?.timeline || []).map((item) => (
                  <div className="trajectory-column" key={item.month}>
                    <strong>{item.areaSqm.toLocaleString()}</strong>
                    <div className="trajectory-track">
                      <div className="trajectory-bar" style={{ height: `${chartHeight(item.areaSqm)}px` }} />
                    </div>
                    <span>{item.month}</span>
                  </div>
                ))}
              </div>
              <div className="area-breakdown">
                <div className="breakdown-title">DETECTED REGION AREA</div>
                {(data?.areaBreakdown || []).map((item, index) => (
                  <button
                    className="breakdown-row"
                    key={`${item.label}-${index}`}
                    onClick={() => {
                      const match = data?.findings[index];
                      if (match) setSelected(match);
                    }}
                  >
                    <span className={`breakdown-dot ${item.severity}`} />
                    <strong>
                      {String(index + 1).padStart(2, "0")} {data?.findings[index]?.areaName || item.label}
                    </strong>
                    <b>{item.areaSqm.toLocaleString()} m²</b>
                  </button>
                ))}
              </div>
            </div>

            <div className="panel case-panel">
              <div className="panel-head">
                <div>
                  <span className="eyebrow">EVIDENCE PACKAGE</span>
                  <h2>Case file</h2>
                </div>
                <FileText size={18} />
              </div>
              {selected ? (
                <div className="case-content">
                  <div className="case-id">
                    {selected.id}
                    <span className={`severity ${selected.severity}`}>{selected.severity.toUpperCase()}</span>
                  </div>
                  <h3>{selected.areaName || selected.label}</h3>
                  <p>
                    Surface change detected between observation windows. The signal should be verified against permits and field conditions
                    before enforcement.
                  </p>
                  <div className="case-meta">
                    <span>
                      <MapPin size={14} /> {selected.coordinates.join(", ")}
                    </span>
                    <span>
                      <CalendarDays size={14} /> {selected.lastObserved}
                    </span>
                  </div>
                  <div className="evidence-grid">
                    <span>
                      FLAGGED AREA <b>{selected.areaSqm.toLocaleString()} m²</b>
                    </span>
                    <span>
                      EST. ERROR <b>±{(selected.detectionErrorSqm || 0).toLocaleString()} m²</b>
                    </span>
                    <span>
                      REGION BBOX <b>{selected.regionBbox?.join(", ") || "Unavailable"}</b>
                    </span>
                    <span>
                      CHANGE MODEL SCORE <b>{selected.modelScore != null ? `${Math.round(selected.modelScore * 100)}%` : "Unavailable"}</b>
                    </span>
                    <span>
                      MINE FOOTPRINT LIKELIHOOD <b>{selected.miningFootprintProbability != null ? `${Math.round(selected.miningFootprintProbability * 100)}%` : "Not trained"}</b>
                    </span>
                  </div>
                  <div className="case-links">
                    {selected.googleMapsUrl && (
                      <a href={selected.googleMapsUrl} target="_blank" rel="noreferrer">
                        OPEN GOOGLE MAPS <ArrowUpRight size={14} />
                      </a>
                    )}
                    <a href={getSatelliteUrl(selected)} target="_blank" rel="noreferrer">
                      SATELLITE VIEW <ArrowUpRight size={14} />
                    </a>
                  </div>
                  <div className="report-controls">
                    <label>
                      REPORT TEMPLATE
                      <select
                        value={reportTemplate}
                        onChange={(event) => setReportTemplate(event.target.value as typeof reportTemplate)}
                      >
                        <option value="quarry-compliance">Quarry / EIA compliance</option>
                        <option value="landowner-evidence">Landowner evidence</option>
                      </select>
                    </label>
                    <label>
                      WHITE-LABEL BRAND
                      <input
                        value={reportBrandName}
                        onChange={(event) => setReportBrandName(event.target.value.slice(0, 80))}
                        placeholder="GeoSentinel AI"
                        maxLength={80}
                      />
                    </label>
                  </div>
                  <button
                    className="generate-button"
                    onClick={downloadReport}
                    disabled={generatingReport || !data?.scanId}
                  >
                    {generatingReport ? "GENERATING PDF..." : "DOWNLOAD PDF REPORT"} <ArrowUpRight size={15} />
                  </button>
                </div>
              ) : (
                <p className="empty">Select a flagged region to inspect its evidence package.</p>
              )}
            </div>
          </section>

          <footer>
            <span>GEOSENTINEL AI / HACKFRONT INDIA 2026</span>
            <span>Detection is an intelligence signal, not a legal determination.</span>
          </footer>
        </>
      )}
    </main>
  );
}

function Kpi({ label, value, detail, icon, alert = false }: { label: string; value: string; detail: string; icon: React.ReactNode; alert?: boolean }) {
  return (
    <div className={`kpi ${alert ? "alert" : ""}`}>
      <div className="kpi-top">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function LiveMap({
  data,
  onSelect,
  drawMode,
  draftGeometry,
  onGeometryDrawn,
}: {
  data: Dataset | null;
  onSelect: (finding: Finding) => void;
  drawMode: boolean;
  draftGeometry: SiteGeometry | null;
  onGeometryDrawn: (geometry: SiteGeometry | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markersGroupRef = useRef<import("leaflet").LayerGroup | null>(null);
  const rectRef = useRef<import("leaflet").Rectangle | null>(null);
  const geometryLayerRef = useRef<import("leaflet").GeoJSON | null>(null);
  const drawingLayerRef = useRef<import("leaflet").Polygon | null>(null);
  const createDrawingLayerRef = useRef<((points: [number, number][]) => import("leaflet").Polygon) | null>(null);
  const drawingPointsRef = useRef<[number, number][]>([]);
  const onGeometryDrawnRef = useRef(onGeometryDrawn);
  const [drawMessage, setDrawMessage] = useState("");
  const [drawPointCount, setDrawPointCount] = useState(0);
  const [mapReady, setMapReady] = useState(false);
  onGeometryDrawnRef.current = onGeometryDrawn;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;

    import("leaflet").then(({ default: L }) => {
      if (disposed || !containerRef.current) return;

      const bbox = data?.source?.bbox || [73.82, 18.48, 73.90, 18.56];
      const southWest: [number, number] = [bbox[1], bbox[0]];
      const northEast: [number, number] = [bbox[3], bbox[2]];
      const displayedGeometry = data?.source?.geometry || draftGeometry;

      if (!mapRef.current) {
        const map = L.map(containerRef.current, { scrollWheelZoom: false }).fitBounds([southWest, northEast]);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: 19,
        }).addTo(map);

        const rect = L.rectangle([southWest, northEast], {
          color: "#879b1b",
          weight: 2,
          fillColor: "#b7d334",
          fillOpacity: 0.08,
        }).addTo(map);
        rectRef.current = rect;

        const markersGroup = L.layerGroup().addTo(map);
        markersGroupRef.current = markersGroup;

        mapRef.current = map;
      } else {
        const map = mapRef.current;
        if (!map) return;
        if (rectRef.current) {
          rectRef.current.setBounds([southWest, northEast]);
        }
      }

      const map = mapRef.current;
      if (!map) return;
      setMapReady(true);
      createDrawingLayerRef.current = (points) => L.polygon(points, {
        color: "#dc8050",
        weight: 2,
        fillColor: "#e89056",
        fillOpacity: 0.12,
      }).addTo(map);
      if (geometryLayerRef.current) {
        geometryLayerRef.current.remove();
        geometryLayerRef.current = null;
      }
      if (displayedGeometry) {
        const layer = L.geoJSON(displayedGeometry, {
          style: { color: "#879b1b", weight: 3, fillColor: "#b7d334", fillOpacity: 0.14 },
        }).addTo(map);
        geometryLayerRef.current = layer;
        if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds(), { padding: [20, 20] });
        rectRef.current?.setStyle({ opacity: 0, fillOpacity: 0 });
      } else {
        rectRef.current?.setStyle({ opacity: 1, fillOpacity: 0.08 });
        map.fitBounds([southWest, northEast]);
      }

      if (markersGroupRef.current) {
        markersGroupRef.current.clearLayers();
        data?.findings.forEach((finding, index) => {
          const color = finding.severity === "high" ? "#e89056" : finding.severity === "medium" ? "#a6b93c" : "#75817c";
          const marker = L.circleMarker(finding.coordinates, {
            radius: 9,
            color,
            fillColor: color,
            fillOpacity: 0.9,
            weight: 3,
          });
          marker.bindTooltip(`${index + 1}. ${finding.label}<br>${finding.coordinates.join(", ")}`, { direction: "top" });
          marker.on("click", () => onSelect(finding));
          markersGroupRef.current?.addLayer(marker);
        });
      }
    });

    return () => {
      disposed = true;
    };
  }, [data, draftGeometry, onSelect]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !drawMode) return;

    drawingPointsRef.current = [];
    setDrawPointCount(0);
    setDrawMessage("");
    const drawPoint = (event: import("leaflet").LeafletMouseEvent) => {
      if (drawingPointsRef.current.length >= 5000) {
        setDrawMessage("The polygon reached the 5,000-vertex limit.");
        return;
      }
      drawingPointsRef.current = [
        ...drawingPointsRef.current,
        [event.latlng.lat, event.latlng.lng],
      ];
      setDrawPointCount(drawingPointsRef.current.length);
      drawingLayerRef.current?.remove();
      drawingLayerRef.current = createDrawingLayerRef.current?.(drawingPointsRef.current) || null;
    };
    map.on("click", drawPoint);
    return () => {
      map.off("click", drawPoint);
      drawingLayerRef.current?.remove();
      drawingLayerRef.current = null;
      drawingPointsRef.current = [];
    };
  }, [drawMode, mapReady]);

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        markersGroupRef.current = null;
        rectRef.current = null;
        geometryLayerRef.current = null;
        drawingLayerRef.current = null;
      }
    };
  }, []);

  function finishDrawing() {
    if (drawingPointsRef.current.length < 3) {
      setDrawMessage("Add at least three boundary points before finishing.");
      return;
    }
    const ring = drawingPointsRef.current.map(([latitude, longitude]) => [longitude, latitude]);
    ring.push([...ring[0]]);
    onGeometryDrawnRef.current({ type: "Polygon", coordinates: [ring] });
  }

  function cancelDrawing() {
    onGeometryDrawnRef.current(null);
    setDrawMessage("");
  }

  return (
    <div className="map-frame">
      <div ref={containerRef} className="real-map" aria-label="OpenStreetMap showing flagged areas" />
      {drawMode && (
        <div className="draw-toolbar" role="group" aria-label="Polygon drawing controls">
          <span>CLICK MAP TO ADD POINTS · {drawPointCount} POINTS</span>
          {drawMessage && <small role="status">{drawMessage}</small>}
          <button onClick={finishDrawing}>FINISH POLYGON</button>
          <button onClick={cancelDrawing}>CANCEL</button>
        </div>
      )}
    </div>
  );
}
