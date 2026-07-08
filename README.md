> **Notice:** This project is currently in development. The documentation below provides a current overview of the architecture, pipeline, and features that are successfully working so far.

# London Cycle Maps


## TL;DR
The primary goal of the London Cycle Maps project is to deliver a routing application specifically tuned for cyclists in London. The system processes raw geographic data into a custom directed graph, factoring in elevation, traffic speed stress, cyclist collision history, and cycleway infrastructure. It currently consists of a fully functional data processing pipeline, a multi-factor routing backend with live disruption awareness, a user-facing map app, and an extensive debug application for data validation. Preset ride modes (**Fast**, **Safe**, **Leisure**) are designed and dependency-mapped, but not yet wired into the UI.
https://tuned-cycling.subscribepage.io/

<img width="959" height="452" alt="Screenshot 2026-06-18 190105" src="https://github.com/user-attachments/assets/3df32217-ee3b-4b17-af05-0c0d89bf2015" />
---

## Project Overview & Current Results

I am building a production-grade cycle route planner that goes beyond simple distance calculation. Rather than relying purely on the shortest path, the routing engine evaluates safety, comfort, infrastructure, and live conditions at request time.

Current major achievements include:
* **Custom Graph Generation:** A multi-stage data pipeline converts OpenStreetMap data, UK accident CSVs, and LIDAR elevation models into a consolidated, directed routing graph.
* **Multi-Factor Routing Engine:** Request-scoped A\* weights cover collision risk, lighting, surface, hills, speed stress, barriers, calming, junctions, signals, green space, and TfL infrastructure — with highway-type masks and vehicular-free penalty rules.
* **Live Transit Integration:** Real-time disruption data from TfL and TomTom is merged, snapped to the graph, and can dynamically reroute cyclists around closures or incidents.
* **Park Hours:** Closed parks are impassable at request time (London local time, OSM opening hours with dawn–dusk fallback).
* **Weight Dependency Matrix:** Parameter sweeps produced a coupling model (antagonisms, synergies, escape mechanisms) with per-mode tie-breakers for the planned presets — ready for a translation layer that keeps conflicting preferences coherent.
* **Data Inspection Suite:** A dedicated debugging frontend overlays surfaces, gradients, calming, barriers, and live disruptions for validation. The following image shows TomTom traffic incidents colour-coded by severity and type:
<img width="1916" height="910" alt="Debug app — live TomTom disruptions overlay" src="https://github.com/user-attachments/assets/573d4d38-5012-4670-943d-7385c28dbf22" />
---

## Planned User Experience

Modes are **not implemented in the app yet**. The intended flow:

1. **Pick a preset** — **Fast**, **Safe**, or **Leisure** (see below).
2. **Optionally fine-tune** preferences (sliders / toggles for safety, comfort, scenery, infrastructure). A translation layer will resolve tug-of-wars using the active mode’s tie-breakers so conflicting settings stay coherent. Users can fill out a delay budget to prioritise their choices. 
3. **Set bike-type and preferences** by answering a few simple questions ("Do you prefer illuminated roads at night?" or "Are you comfortable navigating through traffic jams to save time on your journey?").
4. **Set start and end** on the map (click or text search).
5. **Get Route** — compare the absolute fastest path with the mode-optimized path, stats (Δ vs fastest), and optional route overlays (lit segments, TfL network, barriers, etc.).

| Preset | Intent |
| :--- | :--- |
| **Fast** | Direct, low-friction routing — prioritises flow (signals, junctions, barriers) and keeps detours short. |
| **Safe** | Low-stress, low-risk routing — collision history, lit corridors, and infrastructure win when preferences conflict. |
| **Leisure** | Scenic / comfortable rides — green space and calming-oriented choices, with safety still in the mix where it matters. |

| | |
|:---:|:---:|
| <img width="334" height="328" alt="Screenshot 2026-07-04 235824" src="https://github.com/user-attachments/assets/30400eb8-b90b-45f8-a80e-8e1654f6ff93" /> | <img width="332" height="311" alt="Screenshot 2026-07-04 235852" src="https://github.com/user-attachments/assets/6e6fb93b-092c-4167-a9fe-9ed31e916c79" /> |
| <img width="332" height="421" alt="Screenshot 2026-07-04 235919" src="https://github.com/user-attachments/assets/e51ed325-d5ff-4e21-8125-fcbffc20378e" /> | <img width="337" height="397" alt="Screenshot 2026-07-04 235944" src="https://github.com/user-attachments/assets/7601bbf9-4415-4e27-9ee8-e821eca82e51" /> |

---

## System Architecture & Tech Stack

The architecture is divided into a frontend interface, a routing backend, and a robust data pipeline.

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend Applications** | React 19, Leaflet | Single-page applications for both main routing and debugging interfaces. |
| **Backend Engine** | Flask, NetworkX, Shapely | Handles $A^*$ routing, live disruption matching, park hours, and spatial snap. |
| **Data Processing** | Python, PostgreSQL, PostGIS | Scripts for importing shapefiles, calculating collision risks, and snapping point features. |
| **Graph Format** | GraphML / gpickle | Compiled graph with node and edge attributes used for memory-efficient routing. |

---

## The Data Pipeline

The core of the system is the data generation pipeline that builds the underlying road graph. The pipeline must be run sequentially to ensure accurate physical network attributes.

1. **Network Ingestion:** OpenStreetMap shapefiles are loaded into a PostgreSQL database.
2. **Accident Integration:** Cyclist collision records are imported and matched to road segments.
3. **Intersection Noding:** Highway lines are split at junctions in PostGIS/pgRouting so the graph connects at T-junctions while preserving OSM tags.
4. **Graph Construction:** A directed graph is built using NetworkX, banning motorways while respecting one-way streets and cycling contraflows.
5. **Island Cleanup:** Disconnected nodes and isolated road clusters are purged, leaving only the largest weakly connected component.
6. **Intersection Snapping:** Point features like traffic signals, crossings, and barriers are snapped to the nearest graph node or edge.
7. **Elevation Processing:** LIDAR raster data is sampled to attach elevation values to nodes and calculate physical grades for edges.
8. **TfL Tagging:** Geographic data for Cycleways, Quietways, and Superhighways is algorithmically mapped onto graph edges.

---

## Main Routing Application

The main app (**Tuned Cycling**) is the production environment where cyclists plan journeys. It focuses on clean route presentation rather than raw data exploration.

### Key Routing Features
* **Dual Route Output:** Simultaneously calculates and displays the absolute fastest route and the preference-optimized route.
* **Preference Weights:** Continuous activation scalars for safety, comfort, scenery, and infrastructure (profiles / Test Mode today; Fast / Safe / Leisure presets planned).
* **Location Search:** Mapbox-backed start/end search alongside map clicks.
* **Route Overlays:** A layers picker draws lit segments, TfL network, green space, barriers, signals, junctions, calming, and live disruptions on the optimized path.
* **Segment Inspector:** Right-click inspects underlying graph tags (and live disruption metadata when present).
* **Automated Night Mode:** Sunrise–sunset detection adjusts visual contrast and map layers for night riding.

### Routing Cost Functions

Edge cost is computed at request time. The base model is:

$$\text{Weight}(u,v) = (\text{Length} \times M_{\text{total}} \times M_{\text{highway}} \times R) + A_{\text{total}} + H$$

* $\text{Length}$ — edge length in metres.
* $M_{\text{total}}$ — penalty multiplier from user preferences (risk, light, surface, speed stress, etc.).
* $M_{\text{highway}}$ — always-on highway-type multiplier (e.g. steps and non-cycle footways are heavily discouraged).
* $R$ — reward multiplier for preferred edges (TfL cycleways, quietways, green space).
* $A_{\text{total}}$ — fixed additive penalties (signals, barriers, junctions, calming, …).
* $H$ — physical effort cost for steep ascents.

The **fastest** route uses length and highway masks only. Live closures and closed parks are hard-blocked on both routes.

---

## Data Debugging Application

To ensure the routing engine makes safe decisions, a separate visualization app audits the underlying graph. It uses the same network but disables A\* pathfinding.

### Validation Features
* **Uphill Heatmaps:** Highlights road segments with grades exceeding 3.3%.
* **Surface Toggles:** Color-codes road surfaces to identify cobblestone, gravel, mud, or unmapped terrain.
* **Infrastructure Overlays:** Visualizes barriers, signals, mini-roundabouts, give-way signs, and traffic calming.
* **Live Ground Truth:** Displays TfL and TomTom disruptions to verify spatial matching onto the road network.
* **Manual Map Edits:** Override TfL cycle route assignments on the map; changes save to a JSON ledger for the pipeline to re-apply.

---

*Note: Access to third-party routing disruption and location-search features requires active environment variables containing secure API credentials.*
