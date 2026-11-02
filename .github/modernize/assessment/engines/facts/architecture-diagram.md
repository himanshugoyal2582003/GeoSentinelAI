# Architecture Diagram

GeoSentinel AI is a Next.js dashboard backed by a FastAPI image-analysis
service. The service acquires public Sentinel-2 previews, compares imagery,
persists scan history, and returns findings for map-based review.

## Application Architecture

<!-- mermaid-checked: no \n, no em-dash/en-dash, no {} in labels, subgraphs are id["label"], arrows are -->|"label"|, all subgraphs closed by end, ids unique -->
~~~mermaid
flowchart TD
    subgraph ClientLayer["Client Layer"]
        Browser["Web Browser"]
    end
    subgraph FrontendLayer["Frontend Layer"]
        Dashboard["Next.js Dashboard"]
        Map["Leaflet Map"]
    end
    subgraph BackendLayer["Backend Layer"]
        API["FastAPI API"]
        Analysis["NumPy Image Analysis"]
        CNN["PyTorch ChangeCNN"]
        History["CSV History"]
    end
    subgraph StorageLayer["Storage Layer"]
        Media[("PNG Media Cache")]
        Records[("CSV Records")]
        Model[("CNN Model Artifact")]
    end
    subgraph ExternalLayer["External Services"]
        Planetary["Planetary Computer"]
        OSM["OpenStreetMap"]
        Geocode["Nominatim"]
        Google["Google Maps Links"]
    end

    Browser -->|"uses"| Dashboard
    Dashboard -->|"renders"| Map
    Dashboard -->|"JSON and CORS"| API
    Map -->|"map tiles"| OSM
    API -->|"analyzes pairs"| Analysis
    API -->|"scores changes"| CNN
    API -->|"reads and writes"| History
    Analysis -->|"comparison images"| Media
    History -->|"scan and finding rows"| Records
    CNN -->|"loads weights"| Model
    API -->|"STAC search and previews"| Planetary
    API -->|"reverse geocoding"| Geocode
    Dashboard -->|"opens finding links"| Google
~~~

### Technology Stack Summary

| Layer | Technology | Version | Purpose |
|---|---|---:|---|
| Client | Modern browser | Current | Dashboard access and map interaction |
| Frontend | Next.js and React | 16.4.3 / 19.0.0 | Dashboard rendering and API calls |
| Frontend | Leaflet and Recharts | 1.9.4 / 2.15.0 | Maps and scan visualizations |
| Backend | FastAPI and Uvicorn | 0.115.6 / 0.34.0 | HTTP API and local server |
| Analysis | NumPy and Pillow | 2.2.1 / 11.1.0 | Image alignment and differencing |
| Model | PyTorch | 2.13.0 | Optional CNN scoring |
| Persistence | CSV and local files | N/A | Scan history, findings, media, and model |

### Data Storage & External Services

The backend uses local CSV files for scan and finding history, PNG files for
the latest comparison pair, and a PyTorch artifact for model weights. Public
Planetary Computer STAC data supplies Sentinel-2 previews. The browser uses
OpenStreetMap tiles, while Nominatim provides reverse geocoding and Google Maps
links provide optional location context.

### Key Architectural Decisions

- The API keeps a deterministic image-difference fallback when the CNN
  artifact is unavailable.
- Acquisition, analysis, model scoring, and CSV persistence are separated into
  focused backend modules.
- The frontend and backend deploy independently and communicate through a
  configurable JSON API URL with exact-origin CORS.

## Component Relationships

<!-- mermaid-checked: no \n, no em-dash/en-dash, no {} in labels, subgraphs are id["label"], arrows are -->|"label"|, all subgraphs closed by end, ids unique -->
~~~mermaid
flowchart LR
    subgraph cPresentation["Presentation"]
        cDashboard["Dashboard Page"]
        cMap["Leaflet Map"]
    end
    subgraph cBusiness["Business Logic"]
        cLiveRoute["Live Detect Route"]
        cUploadRoute["Upload Detect Route"]
        cAnalysis["Pair Analysis"]
        cModel["ChangeCNN Scoring"]
    end
    subgraph cData["Data Access"]
        cHistory["History Store"]
        cMedia["Media Store"]
        cDataset["Training Dataset"]
    end
    subgraph cInfra["Infrastructure"]
        cAcquire["Scene Acquisition"]
        cGeocode["Geocoding Client"]
        cCors["CORS Middleware"]
    end

    cDashboard -->|"requests scans"| cLiveRoute
    cDashboard -->|"uploads pairs"| cUploadRoute
    cDashboard -->|"renders findings"| cMap
    cLiveRoute -->|"fetches scenes"| cAcquire
    cLiveRoute -->|"analyzes latest pair"| cAnalysis
    cUploadRoute -->|"analyzes upload pair"| cAnalysis
    cAnalysis -->|"optional score"| cModel
    cAnalysis -->|"saves images"| cMedia
    cLiveRoute -->|"persists results"| cHistory
    cUploadRoute -->|"returns report"| cDashboard
    cModel -->|"loads training output"| cDataset
    cLiveRoute -->|"resolves locations"| cGeocode
    cCors -.->|"protects API origins"| cLiveRoute
    cCors -.->|"protects API origins"| cUploadRoute
~~~

### Component Inventory

| Component | Layer | Type | Responsibility |
|---|---|---|---|
| Dashboard Page | Presentation | Next.js page | Starts scans, displays status, findings, and reports |
| Leaflet Map | Presentation | UI component | Displays findings and map context |
| Live Detect Route | Business Logic | FastAPI route | Acquires scenes and returns live or cached results |
| Upload Detect Route | Business Logic | FastAPI route | Validates uploaded image pairs and analyzes them |
| Pair Analysis | Business Logic | Image pipeline | Aligns, masks, compares, and scores image differences |
| ChangeCNN Scoring | Business Logic | PyTorch model | Adds optional learned change confidence |
| History Store | Data Access | CSV persistence | Stores scans and findings |
| Media Store | Data Access | File persistence | Stores latest comparison images and cached response |
| Training Dataset | Data Access | Dataset files | Supplies imagery and labels for training |
| Scene Acquisition | Infrastructure | Provider client | Searches and downloads public Sentinel-2 previews |
| Geocoding Client | Infrastructure | HTTP client | Resolves finding coordinates to area names |
| CORS Middleware | Infrastructure | FastAPI middleware | Restricts browser origins |
