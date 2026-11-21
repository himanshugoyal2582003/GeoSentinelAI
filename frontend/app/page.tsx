"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowUpRight, CalendarDays, Crosshair, FileText, MapPin, Upload, Waves, BrainCircuit } from "lucide-react";
import type { Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";

const LIVE_SCAN_INTERVAL_MS = 10 * 60 * 1000;

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
  googleMapsUrl?: string;
  googleSatelliteUrl?: string;
};

type Dataset = {
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
    sceneCount?: number;
  };
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
  const [training, setTraining] = useState(false);
  const [trainingMessage, setTrainingMessage] = useState("");
  const [nextScanAt, setNextScanAt] = useState<number | null>(null);
  const [error, setError] = useState("");

  function applyLiveResult(value: Dataset) {
    setData(value);
    setSelected(value.findings[0] || null);
    setNextScanAt(Date.now() + LIVE_SCAN_INTERVAL_MS);
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
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!liveScanning) void runLiveScan();
    }, LIVE_SCAN_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [liveScanning]);

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
    } finally {
      setLiveScanning(false);
    }
  }

  async function trainCnn() {
    setTraining(true);
    setTrainingMessage("Starting CNN training...");
    try {
      const response = await fetch(`${API}/api/train`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await parseApiError(response, "CNN training could not start. Enable TRAINING_ENABLED on the backend."));
      }
      let state = (await response.json()) as { status: string; message: string };
      setTrainingMessage(state.message);
      let attempts = 0;
      while (state.status === "running" && attempts < 60) {
        attempts++;
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const statusResponse = await fetch(`${API}/api/train`);
        if (!statusResponse.ok) {
          throw new Error(await parseApiError(statusResponse, "Could not read CNN training status"));
        }
        state = (await statusResponse.json()) as { status: string; message: string };
        setTrainingMessage(state.message);
      }
      if (state.status === "failed") throw new Error(state.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "CNN training failed");
    } finally {
      setTraining(false);
    }
  }

  function downloadReport() {
    if (!selected || !data) return;
    const report = {
      reportTitle: `GeoSentinel change report - ${selected.id}`,
      generatedAt: new Date().toISOString(),
      source: data.source,
      observationWindow: { historical: data.historicalDate, recent: data.recentDate },
      finding: selected,
      interpretation: "Automated surface-change signal from Sentinel-2 imagery. Verify permits and field conditions before enforcement.",
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selected.id}-change-report.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <main className="loading">Loading GeoSentinel command center...</main>;

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
          <span className="live-dot" /> SYSTEM OPERATIONAL
          <button className="live-button" onClick={runLiveScan} disabled={liveScanning}>
            <Waves size={15} /> {liveScanning ? "SCANNING..." : "LIVE SATELLITE SCAN"}
          </button>
          <button className="live-button" onClick={trainCnn} disabled={training}>
            <BrainCircuit size={15} /> {training ? "TRAINING..." : "TRAIN CNN"}
          </button>
          <label className={`upload-button ${uploading ? "disabled" : ""}`}>
            <Upload size={15} /> {uploading ? "PROCESSING..." : "UPLOAD PAIR"}
            <input type="file" accept="image/*" multiple onChange={handleUpload} disabled={uploading} />
          </label>
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">THE CHANGE SENTINEL / T8.1</p>
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
            {data?.historicalDate} <b>→</b> {data?.recentDate}
          </strong>
        </div>
      </section>

      {error && (
        <div className="error">
          <AlertTriangle size={17} /> {error}
          <button className="retry-button" onClick={runLiveScan}>
            RETRY LIVE SCAN
          </button>
        </div>
      )}

      {trainingMessage && (
        <div className="cache-note">
          <BrainCircuit size={16} /> {trainingMessage}
        </div>
      )}

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
          <strong>Every 10 minutes</strong>
          <small>{nextScanAt ? `Next scan ${new Date(nextScanAt).toLocaleTimeString()}` : "Starting..."}</small>
        </div>
        <div className="demo-badge">{data?.source ? "LIVE SATELLITE" : "DEMO DATASET"}</div>
      </section>

      {data?.source && (
        <section className="satellite-compare">
          <div className="satellite-head">
            <div>
              <span className="eyebrow">LIVE EVIDENCE / STATIC MONITORING LOCATION</span>
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
          <LiveMap data={data} onSelect={setSelected} />
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
                  MODEL SCORE <b>{selected.modelScore ? `${Math.round(selected.modelScore * 100)}%` : "Unavailable"}</b>
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
              <button className="generate-button" onClick={downloadReport}>
                DOWNLOAD FULL REPORT <ArrowUpRight size={15} />
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

function LiveMap({ data, onSelect }: { data: Dataset | null; onSelect: (finding: Finding) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markersGroupRef = useRef<import("leaflet").LayerGroup | null>(null);
  const rectRef = useRef<import("leaflet").Rectangle | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;

    import("leaflet").then(({ default: L }) => {
      if (disposed || !containerRef.current) return;

      const bbox = data?.source?.bbox || [73.82, 18.48, 73.90, 18.56];
      const southWest: [number, number] = [bbox[1], bbox[0]];
      const northEast: [number, number] = [bbox[3], bbox[2]];

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
        map.fitBounds([southWest, northEast]);
        if (rectRef.current) {
          rectRef.current.setBounds([southWest, northEast]);
        }
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
  }, [data, onSelect]);

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        markersGroupRef.current = null;
        rectRef.current = null;
      }
    };
  }, []);

  return <div ref={containerRef} className="real-map" aria-label="OpenStreetMap showing flagged areas" />;
}
