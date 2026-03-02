> **Notice:** This project is currently in development. The documentation below provides a current overview of the architecture, pipeline, and features that are successfully working so far.

# London Cycle Maps


## TL;DR
The primary goal of the London Cycle Maps project is to deliver a routing application specifically tuned for cyclists in London. The system processes raw geographic data into a custom directed graph, factoring in elevation, traffic speed stress, cyclist collision history, and cycleway infrastructure. It currently consists of a fully functional data processing pipeline, a user-facing routing frontend with highly customizable safety and comfort toggles, and an extensive debug application for data validation.
<img width="1917" height="906" alt="Image" src="https://github.com/user-attachments/assets/13b9a73f-e0f5-4c31-a56c-2571e25b1ee0" />
---

## Project Overview & Current Results

We are building a production-grade cycle route planner that goes beyond simple distance calculation. Rather than relying purely on the shortest path, the routing engine successfully evaluates complex safety and comfort parameters. 

Current major achievements include:
* **Custom Graph Generation:** A multi-stage data pipeline successfully converts OpenStreetMap data, UK accident CSVs, and LIDAR elevation models into a consolidated, directed routing graph.
* **Multi-Factor Routing Engine:** The backend dynamically calculates route weights based on real-time user toggles for safety, comfort, and scenery.
* **TfL Infrastructure Integration:** Transport for London (TfL) Cycleways, Quietways, and Superhighways are algorithmically tagged and visually represented.
* **Live Transit Integration:** Real-time disruption data from TfL and TomTom is fully integrated, parsed spatially, and capable of dynamically rerouting cyclists around closures or incidents.
* **Data Inspection Suite:** A dedicated debugging frontend allows administrators to visually overlay and inspect road surfaces, gradient heatmaps, and precise points of traffic calming. The following image details the current disruptions from the TomTom traffic API, colour-coded by severity and type: 
<img width="1916" height="910" alt="Image" src="https://github.com/user-attachments/assets/573d4d38-5012-4670-943d-7385c28dbf22" /> 
---

## System Architecture & Tech Stack

The architecture is divided into a frontend interface, a routing backend, and a robust data pipeline.

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend Applications** | React 19, Leaflet | Single-page applications for both main routing and debugging interfaces. |
| **Backend Engine** | Flask, NetworkX, Shapely | Handles $A^*$ routing calculations, closure optimizations, and spatial data matching. |
| **Data Processing** | Python, PostgreSQL, PostGIS | Scripts for importing shapefiles, calculating collision risks, and snapping point features. |
| **Graph Format** | GraphML | The final compiled format containing all node and edge attributes used for memory-efficient routing. |

---

## The Data Pipeline


The core of the system is the data generation pipeline that builds the underlying road graph. The pipeline must be run sequentially to ensure accurate physical network attributes.

1. **Network Ingestion:** OpenStreetMap shapefiles are loaded into a PostgreSQL database.
2. **Accident Integration:** Cyclist collision records are imported and matched to road segments.
3. **Graph Construction:** A directed graph is built using NetworkX, banning motorways while respecting one-way streets and cycling contraflows.
4. **Island Cleanup:** Disconnected nodes and isolated road clusters are purged, leaving only the largest weakly connected component.
5. **Intersection Snapping:** Point features like traffic signals, crossings, and barriers are snapped to the nearest graph node or edge using KD-trees and STRtrees.
6. **Elevation Processing:** LIDAR raster data is sampled to attach elevation values to nodes and calculate physical grades for edges.
7. **TfL Tagging:** Geographic JSON data for Cycleways is algorithmically mapped onto the graph edges.

---

## Main Routing Application


The main app is the production environment where cyclists plan their journeys. It completely avoids raw data exploration in favor of clean route presentation.

### Key Routing Features
* **Dual Route Output:** The system simultaneously calculates and displays both the absolute fastest route and the dynamically optimized route.
* **Safety Toggles:** Users can penalize intersections, speed stress, narrow facilities, unlit roads, and collision hotspots.
* **Comfort & Scenery:** Users can prioritize flat routes, road-bike-friendly surfaces, green spaces, and official TfL Quietways.
* **Segment Inspector:** A right-click functionality allows users to inspect the underlying graph data of any specific road segment.
* **Automated Night Mode:** The application queries a local sunrise-sunset API and automatically adjusts visual contrast and map layers for night riding.

### Routing Cost Functions

The routing relies on a custom dynamic weight calculation applied at request-time. The base mathematical model for calculating edge cost is defined as follows:

$$\text{Weight}(u,v) = (\text{Length} \times M_{\text{total}} \times R) + A_{\text{total}} + H$$

Variables within the function dynamically change based on user preferences:
* The base distance of the edge in meters is represented by $\text{Length}$.
* The penalty multiplier based on surface quality, lighting, and collision risk is represented by $M_{\text{total}}$.
* The reward multiplier prioritizing favorable routes like cycleways is represented by $R$.
* Fixed metric penalties for obstacles like traffic signals or barriers are summed up as $A_{\text{total}}$.
* The physical effort cost for steep ascents is represented by $H$.

---

## Data Debugging Application

To ensure the routing engine makes safe decisions, a separate visualization app allows developers to audit the underlying GraphML file. It utilizes the exact same routing graph but disables A* pathfinding.

### Validation Features
* **Uphill Heatmaps:** Highlights road segments with grades exceeding 3.3%.
* **Surface Toggles:** Color-codes road surfaces to identify cobblestone, gravel, mud, or unmapped terrain.
* **Infrastructure Overlays:** Visualizes exact coordinates of node-tags like mini-roundabouts, give-way signs, barriers, and traffic calming measures.
* **TfL Live Ground Truth:** Displays raw geometric disruptions straight from the TfL API to verify that the spatial matching algorithm correctly snaps closures to the road network.
* **Manual Map Edits:** Includes a specialized tool to manually override TfL cycle route assignments directly on the map, which safely saves to a JSON ledger for the pipeline to re-apply.

---

*Note: Access to third-party routing disruption features requires active environment variables containing secure API credentials.*
