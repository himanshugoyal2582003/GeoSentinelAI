"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, CalendarDays, Crosshair, FileText, MapPin, Upload, Waves } from "lucide-react";
import type { Map as LeafletMap } from "leaflet";
import "leaflet/dist/leaflet.css";

const LIVE_SCAN_INTERVAL_MS = 10 * 60 * 1000;

type Finding = {
  id: string; label: string; severity: "high" | "medium" | "low"; confidence: number;
  areaSqm: number; coordinates: [number, number]; changeType: string; firstObserved: string;
  lastObserved: string; status: string; areaName?: string; regionBbox?: [number, number, number, number];
  detectionErrorSqm?: number; modelScore?: number; googleMapsUrl?: string; googleSatelliteUrl?: string;
};
type Dataset = {
  mode: string; region: string; historicalDate: string; recentDate: string; findings: Finding[];
  summary: { changedAreaSqm: number; changedAreaHa: number; highRiskCount: number; averageConfidence: number };
  timeline: { month: string; areaSqm: number }[];
  areaBreakdown?: { label: string; areaSqm: number; severity: "high" | "medium" | "low" }[];
  timelineNote?: string;
  source?: { bbox: number[]; historicalImage: string; recentImage: string; provider: string; note: string; stale?: boolean; sceneCount?: number };
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [data, setData] = useState<Dataset | null>(null);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [liveScanning, setLiveScanning] = useState(false);
  const [nextScanAt, setNextScanAt] = useState<number | null>(null);
  const [error, setError] = useState("");

  function applyLiveResult(value: Dataset) {
    setData(value);
    setSelected(value.findings[0] || null);
    setNextScanAt(Date.now() + LIVE_SCAN_INTERVAL_MS);
  }

  useEffect(() => {
    fetch(`${API}/api/live-detect`).then((response) => {
      if (!response.ok) throw new Error("Live satellite feed unavailable.");
      return response.json();
    }).then((value: Dataset) => {
      applyLiveResult(value); setLoading(false);
    }).catch((reason) => { setError(reason instanceof Error ? reason.message : "Live satellite feed unavailable."); setLoading(false); });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!liveScanning) void runLiveScan();
    }, LIVE_SCAN_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [liveScanning]);

  const maxArea = useMemo(() => Math.max(...(data?.timeline.map((item) => item.areaSqm) || [1])), [data]);
  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length < 2) return;
    const body = new FormData(); body.append("historical", files[0]); body.append("recent", files[1]);
    setUploading(true); setError("");
    try {
      const response = await fetch(`${API}/api/detect`, { method: "POST", body });
      if (!response.ok) throw new Error((await response.json()).detail || "Detection failed");
      const value = await response.json() as Dataset; applyLiveResult(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Detection failed"); }
    finally { setUploading(false); }
  }
  async function runLiveScan() {
    setLiveScanning(true); setError("");
    try {
      const response = await fetch(`${API}/api/live-detect`);
      if (!response.ok) throw new Error((await response.json()).detail || "Live scan failed");
      const value = await response.json() as Dataset; applyLiveResult(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Live scan failed"); }
    finally { setLiveScanning(false); }
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
    anchor.href = url; anchor.download = `${selected.id}-change-report.json`; anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <main className="loading">Loading GeoSentinel command center...</main>;
  return (
    <main>
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Crosshair size={20} /></div><div><strong>GEOSENTINEL</strong><span>AI MONITORING COMMAND CENTER</span></div></div>
        <div className="top-actions"><span className="live-dot" /> SYSTEM OPERATIONAL <button className="live-button" onClick={runLiveScan}><Waves size={15} /> {liveScanning ? "SCANNING..." : "LIVE SATELLITE SCAN"}</button><label className="upload-button"><Upload size={15} /> {uploading ? "PROCESSING..." : "UPLOAD PAIR"}<input type="file" accept="image/*" multiple onChange={handleUpload} /></label></div>
      </header>
      <section className="hero">
        <div><p className="eyebrow">THE CHANGE SENTINEL / T8.1</p><h1>From satellite pixels<br /><em>to actionable intelligence.</em></h1><p className="hero-copy">Detecting suspicious land-use change before it disappears into the landscape.</p></div>
        <div className="scan-status"><Waves size={16} /><span>MONITORING WINDOW</span><strong>{data?.historicalDate} <b>→</b> {data?.recentDate}</strong></div>
      </section>
      {error && <div className="error"><AlertTriangle size={17} /> {error}<button className="retry-button" onClick={runLiveScan}>RETRY LIVE SCAN</button></div>}
      <section className="controls"><div><span className="control-label">REGION</span><strong><MapPin size={15} /> {data?.region}</strong></div><div><span className="control-label">SENSOR</span><strong>Sentinel-2 / 10m</strong></div><div><span className="control-label">DETECTION MODE</span><strong>ChangeCNN + differencing</strong></div><div><span className="control-label">AUTO MONITORING</span><strong>Every 10 minutes</strong><small>{nextScanAt ? `Next scan ${new Date(nextScanAt).toLocaleTimeString()}` : "Starting..."}</small></div><div className="demo-badge">{data?.source ? "LIVE SATELLITE" : "DEMO DATASET"}</div></section>
      {data?.source && <section className="satellite-compare"><div className="satellite-head"><div><span className="eyebrow">LIVE EVIDENCE / STATIC MONITORING LOCATION</span><h2>Satellite comparison</h2><p>{data.source.provider} · {data.source.sceneCount || 0} scenes · approximately 5-day Sentinel-2 revisit · BBOX {data.source.bbox.join(", ")}</p></div><span className="live-tag">{data.source.stale ? "CACHED REAL FEED" : "LIVE FEED"}</span></div><div className="satellite-images"><figure><img src={`${API}${data.source.historicalImage}`} alt="Historical Sentinel-2 scene" /><figcaption>HISTORICAL / {data.historicalDate}</figcaption></figure><div className="compare-arrow">→</div><figure><img src={`${API}${data.source.recentImage}`} alt="Recent Sentinel-2 scene" /><figcaption>RECENT / {data.recentDate}</figcaption></figure></div>{data.source.stale && <p className="cache-note">{data.source.note}</p>}</section>}
      <section className="kpis">
        <Kpi label="CHANGED AREA" value={`${data?.summary.changedAreaHa} ha`} detail={`${data?.summary.changedAreaSqm.toLocaleString()} m² mapped`} icon={<ArrowUpRight />} />
        <Kpi label="HIGH-RISK FINDINGS" value={String(data?.summary.highRiskCount).padStart(2, "0")} detail="Requires field verification" icon={<AlertTriangle />} alert />
        <Kpi label="MODEL CONFIDENCE" value={`${Math.round((data?.summary.averageConfidence || 0) * 100)}%`} detail="Across detected regions" icon={<Crosshair />} />
        <Kpi label="CASE FILES" value={String(data?.findings.length).padStart(2, "0")} detail="Evidence packages ready" icon={<FileText />} />
      </section>
      <section className="workspace">
        <div className="panel map-panel"><div className="panel-head"><div><span className="eyebrow">SPATIAL OVERVIEW</span><h2>Live change map</h2></div><span className="map-legend"><i className="legend-dot high" /> HIGH RISK <i className="legend-dot medium" /> REVIEW</span></div><LiveMap data={data} onSelect={setSelected} /></div>
        <div className="panel findings-panel"><div className="panel-head"><div><span className="eyebrow">DETECTION QUEUE</span><h2>Flagged regions <small>{data?.findings.length}</small></h2></div><button className="text-button">VIEW ALL <ArrowUpRight size={14} /></button></div><div className="findings-list">{data?.findings.map((finding, index) => <button className={`finding ${selected?.id === finding.id ? "selected" : ""}`} key={finding.id} onClick={() => setSelected(finding)}><span className={`finding-index ${finding.severity}`}>0{index + 1}</span><span className="finding-main"><strong>{finding.areaName || finding.label}</strong><small>{finding.changeType} · {finding.coordinates.join(", ")}</small></span><span className="finding-area">{(finding.areaSqm / 10000).toFixed(2)} ha</span><ArrowUpRight size={16} /></button>)}</div></div>
      </section>
      <section className="lower-grid"><div className="panel timeline-panel"><div className="panel-head"><div><span className="eyebrow">TEMPORAL ANALYSIS</span><h2>Expansion trajectory</h2></div><span className="unit">AREA / M²</span></div><p className="timeline-note">{data?.timelineNote || "Historical scene baseline compared with the recent scene."}</p><div className="trajectory-chart">{(data?.timeline || []).map((item) => <div className="trajectory-column" key={item.month}><strong>{item.areaSqm.toLocaleString()}</strong><div className="trajectory-track"><div className="trajectory-bar" style={{ height: `${item.areaSqm ? Math.max(18, item.areaSqm / maxArea * 150) : 18}px` }} /></div><span>{item.month}</span></div>)}</div><div className="area-breakdown"><div className="breakdown-title">DETECTED REGION AREA</div>{(data?.areaBreakdown || []).map((item, index) => <button className="breakdown-row" key={item.label} onClick={() => data && setSelected(data.findings[index])}><span className={`breakdown-dot ${item.severity}`} /><strong>{String(index + 1).padStart(2, "0")} {data?.findings[index]?.areaName || item.label}</strong><b>{item.areaSqm.toLocaleString()} m²</b></button>)}</div></div><div className="panel case-panel"><div className="panel-head"><div><span className="eyebrow">EVIDENCE PACKAGE</span><h2>Case file</h2></div><FileText size={18} /></div>{selected ? <div className="case-content"><div className="case-id">{selected.id}<span className={`severity ${selected.severity}`}>{selected.severity.toUpperCase()}</span></div><h3>{selected.areaName || selected.label}</h3><p>Surface change detected between observation windows. The signal should be verified against permits and field conditions before enforcement.</p><div className="case-meta"><span><MapPin size={14} /> {selected.coordinates.join(", ")}</span><span><CalendarDays size={14} /> {selected.lastObserved}</span></div><div className="evidence-grid"><span>FLAGGED AREA <b>{selected.areaSqm.toLocaleString()} m²</b></span><span>EST. ERROR <b>±{(selected.detectionErrorSqm || 0).toLocaleString()} m²</b></span><span>REGION BBOX <b>{selected.regionBbox?.join(", ") || "Unavailable"}</b></span><span>MODEL SCORE <b>{selected.modelScore ? `${Math.round(selected.modelScore * 100)}%` : "Unavailable"}</b></span></div><div className="case-links"><a href={selected.googleMapsUrl} target="_blank" rel="noreferrer">OPEN GOOGLE MAPS <ArrowUpRight size={14} /></a><a href={selected.googleSatelliteUrl} target="_blank" rel="noreferrer">SATELLITE VIEW <ArrowUpRight size={14} /></a></div><button className="generate-button" onClick={downloadReport}>DOWNLOAD FULL REPORT <ArrowUpRight size={15} /></button></div> : <p className="empty">Select a flagged region to inspect its evidence package.</p>}</div></section>
      <footer><span>GEOSENTINEL AI / HACKFRONT INDIA 2026</span><span>Detection is an intelligence signal, not a legal determination.</span></footer>
    </main>
  );
}

function Kpi({ label, value, detail, icon, alert = false }: { label: string; value: string; detail: string; icon: React.ReactNode; alert?: boolean }) {
  return <div className={`kpi ${alert ? "alert" : ""}`}><div className="kpi-top"><span>{label}</span>{icon}</div><strong>{value}</strong><small>{detail}</small></div>;
}

function LiveMap({ data, onSelect }: { data: Dataset | null; onSelect: (finding: Finding) => void }) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!container) return;
    let map: LeafletMap | undefined;
    let disposed = false;
    import("leaflet").then(({ default: L }) => {
      if (disposed) return;
      const bbox = data?.source?.bbox || [73.82, 18.48, 73.90, 18.56];
      const southWest: [number, number] = [bbox[1], bbox[0]];
      const northEast: [number, number] = [bbox[3], bbox[2]];
      map = L.map(container, { scrollWheelZoom: false }).fitBounds([southWest, northEast]);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);
      L.rectangle([southWest, northEast], { color: "#879b1b", weight: 2, fillColor: "#b7d334", fillOpacity: 0.08 }).addTo(map);
      const activeMap = map;
      data?.findings.forEach((finding, index) => {
        const color = finding.severity === "high" ? "#e89056" : finding.severity === "medium" ? "#a6b93c" : "#75817c";
        const marker = L.circleMarker(finding.coordinates, { radius: 9, color, fillColor: color, fillOpacity: 0.9, weight: 3 });
        marker.bindTooltip(`${index + 1}. ${finding.label}<br>${finding.coordinates.join(", ")}`, { direction: "top" });
        marker.on("click", () => onSelect(finding));
        marker.addTo(activeMap);
      });
    });
    return () => {
      disposed = true;
      map?.remove();
    };
  }, [container, data, onSelect]);
  return <div ref={setContainer} className="real-map" aria-label="OpenStreetMap showing flagged areas" />;
}
