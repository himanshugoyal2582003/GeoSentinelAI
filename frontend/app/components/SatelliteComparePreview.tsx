function SceneTile({ recent }: { recent: boolean }) {
  return (
    <svg viewBox="0 0 520 280" role="img" aria-label={`Illustrative ${recent ? "recent" : "historical"} satellite scene`}>
      <rect width="520" height="280" fill="#354433" />
      <path d="M0 0H196L240 38L207 89L130 116L0 93Z" fill="#455a3d" />
      <path d="M290 0H520V104L460 126L402 84L336 70Z" fill="#4d583f" />
      <path d="M0 174L82 134L172 153L201 224L130 280H0Z" fill="#4e633e" />
      <path d="M278 174L350 136L428 157L520 129V280H346Z" fill="#48573b" />
      <path d="M-12 121C83 102 130 138 206 130S341 104 537 142" fill="none" stroke="#a7a184" strokeOpacity=".72" strokeWidth="7" />
      <path d="M-12 121C83 102 130 138 206 130S341 104 537 142" fill="none" stroke="#45483e" strokeWidth="2" />
      <path d="M245 -12C226 52 275 94 252 154S225 233 260 292" fill="none" stroke="#b1a98e" strokeOpacity=".64" strokeWidth="5" />
      <path d="M245 -12C226 52 275 94 252 154S225 233 260 292" fill="none" stroke="#45483e" strokeWidth="1.5" />
      <g fill="none" stroke="#91a078" strokeOpacity=".42" strokeWidth="1.5">
        <path d="M24 27L107 43L144 18M323 31L400 50L482 25M35 228L96 204L160 242M365 233L414 194L496 217" />
        <path d="M50 57L105 68L152 49M350 74L410 87L476 66M22 202L87 181L139 204M375 199L425 170L490 187" />
      </g>
      <path d={recent ? "M304 111L347 94L394 105L420 134L408 169L371 187L328 177L306 150Z" : "M310 115L341 103L372 111L391 132L382 153L352 164L323 156L309 139Z"} fill="#c17a4b" fillOpacity=".78" />
      <path d={recent ? "M304 111L347 94L394 105L420 134L408 169L371 187L328 177L306 150Z" : "M310 115L341 103L372 111L391 132L382 153L352 164L323 156L309 139Z"} fill="none" stroke="#f0b27e" strokeWidth="2" strokeDasharray="5 4" />
      <g fill="#d5c8a6" fillOpacity=".74">
        <circle cx="64" cy="91" r="2" /><circle cx="77" cy="97" r="2" /><circle cx="88" cy="87" r="2" />
        <circle cx="456" cy="201" r="2" /><circle cx="468" cy="208" r="2" /><circle cx="480" cy="198" r="2" />
      </g>
    </svg>
  );
}

export default function SatelliteComparePreview() {
  return (
    <section className="satellite-compare landing-comparison" id="comparison" aria-labelledby="comparison-title">
      <div className="satellite-head">
        <div>
          <span className="eyebrow">Surface change / scene pair</span>
          <h2 id="comparison-title">Satellite comparison</h2>
          <p>Illustrative preview. Current imagery and findings are available in the dashboard.</p>
        </div>
        <span className="live-tag">Illustrative</span>
      </div>
      <div className="satellite-images">
        <figure>
          <div className="scene-tile"><SceneTile recent={false} /></div>
          <figcaption>Historical / Sentinel-2</figcaption>
        </figure>
        <div className="compare-arrow" aria-hidden="true">→</div>
        <figure>
          <div className="scene-tile"><SceneTile recent /></div>
          <figcaption>Recent / Sentinel-2</figcaption>
        </figure>
      </div>
    </section>
  );
}
