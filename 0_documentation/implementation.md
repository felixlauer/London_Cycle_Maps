# Technical Task Sheet: London Cycle Maps — Advanced Routing Engine 2.0

**Target System:** `4_backend_engine/app.py` & `5_frontend`
**Goal:** Implement node-aware routing and advanced heuristic "Modes" to better simulate safe/pleasant cycling behavior.

---

## 1. Architectural Changes

### 1.1 Node Data Integration
* **Current State:** The routing engine (`weight_optimized`) currently relies almost exclusively on edge attributes (`d`).
* **Requirement:** Refactor the cost function to access **Target Node (`v`)** attributes.
* **Goal:** Enable penalties for point-features like barriers, traffic signals, and intersection types which are already present in our graph (`traffic_signals`, `barrier`, `crossing`, etc.) but currently unused.

### 1.2 Base Physics Constants
* **Standard Speed:** Derive a global constant `CYCLIST_SPEED_MPS` based on the existing logic (currently approx. 16 km/h or 4.4 m/s).
* **Usage:** Use this constant to convert time-based penalties (e.g., "15 seconds wait") into distance-based costs (meters) for the A* algorithm.

---

## 2. New Routing "Modes" (Cost Factors)

Implement the following weighting factors. Each should be controlled by a new API parameter (0.0 to 1.0) passed from the frontend.

### A. TfL Infrastructure Preference (Two distinct modes)
**Tag:** `tfl_cycle_programme`

1.  **Mode: Cycleways & Superhighways**
    * **Logic:** Apply a cost reduction (reward) *only* if the edge belongs to the "Cycleway" or "Cycle Superhighway" networks.
    * **Constraint:** Explicitly exclude "Quietways" from this specific mode.
    * **Math:** Apply a fractional length reduction (e.g., multiplier < 1.0).

2.  **Mode: Quietways**
    * **Logic:** Apply a separate cost reduction (reward) if the edge is tagged as a "Quietway".
    * **Goal:** Allow users to specifically target quieter, low-traffic routes defined by TfL.

### B. Speed Difference Stress
**Tag:** `maxspeed` (Edge)
**Reference:** Literature Table 7 (Speed Difference)

* **Logic:** Compare the road's speed limit against the cyclist's standard speed (~16km/h).
* **Correction:** The previous proposed factors were too aggressive. Use a milder linear or stepped scale.
* **Mapping Idea:**
    * < 20 km/h difference: Negligible penalty.
    * 20-30 km/h difference: Low penalty.
    * > 30 km/h difference: Moderate penalty.
* **Fallback:** If `maxspeed` is missing, infer standard London limits based on `highway` type (e.g., residential=30km/h, primary=50km/h).

### C. Cycle Facility Width
**Tag:** `width` or `cycleway_width` (Edge)
**Reference:** Literature Table 7 (Width of bicycle facility)

* **Logic:** Penalize segments where the facility width is below standard comfortable levels.
* **Correction:** Use gentler penalty factors than initially proposed.
* **Thresholds:**
    * Standard ($w_{std}$): 1.5m.
    * Minimum ($w_{min}$): 1.25m.
* **Implementation:**
    * Width >= 1.5m: No penalty.
    * 1.25m <= Width < 1.5m: Slight penalty.
    * Width < 1.25m: Moderate penalty (do not make it effectively impassable, just discouraged).

### D. Intersection & Obstacle Density
**Tag:** Node attributes (`crossing`, `give_way`, `mini_roundabout`, etc.)
**Reference:** Literature Table 7 (Intersections/km)

* **Logic:** The goal is to penalize routes with frequent stops/interruptions.
* **Implementation:** Since A* operates edge-by-edge, add a **fixed distance cost** for every node encountered that contains specific tags.
    * **Target Tags:** Crossings, Give Ways, and small roundabouts.
    * **Result:** A route with 10 crossings per km will naturally accumulate a higher cost than one with 2 per km.

### E. Green / Scenic Routes
**Tags:** `highway`, `surface`, `lit` (Edge)

* **Goal:** Prioritize routes through parks or near water.
* **Heuristic:** Since we lack a dedicated "is_park" tag, construct a composite detection logic:
    * Identify edges that likely represent park paths (e.g., specific `highway` types like footway/cycleway/bridleway combined with natural surfaces or lack of lighting).
    * Apply a "Green Bonus" (cost reduction) to these edges.

### F. Barriers
**Tag:** `barrier` (Node)

* **Goal:** Penalize physical restrictions that disrupt flow.
* **Logic:** Differentiate based on `barrier` value.
    * **Passable (e.g., bollards):** Very low or zero penalty.
    * **Disruptive (e.g., gates, chicanes):** Moderate penalty (forcing a slow-down).
    * **Dismount Required (e.g., stiles, steps):** High penalty (effectively blocking the route unless necessary).

### G. Traffic Calming
**Tag:** `traffic_calming` (Edge)

* **Goal:** Avoid uncomfortable infrastructure.
* **Logic:** Add a fixed distance penalty for each segment containing calming measures.
* **Scalability:** Differentiate severity if data permits (e.g., `cushion` = low penalty vs `hump` = higher penalty).

### H. Right Turn Penalty (Safety)
**Goal:** Penalize right turns (crossing oncoming traffic in Left-Hand Traffic UK).

* **Challenge:** Standard graph traversal $(u, v)$ does not inherently know the "previous" node $(t)$ required to calculate the turn angle.
* **Requirement:**
    * **Preferred:** Implement a mechanism to detect direction changes between the incoming edge vector and outgoing edge vector. If the angle indicates a right turn (~90 degrees +/- threshold), apply a significant safety penalty.
    * **Alternative:** If strict turn detection is unfeasible in the current architecture, implement a "Junction Danger" penalty on nodes likely to involve complex merging (e.g., large intersections without signals), but prioritize the directional penalty if possible.

### I. Traffic Signal Penalty
**Tag:** `traffic_signals` (Node)

* **Logic:** Traffic lights imply a probability of stopping.
* **Implementation:** Convert a standard wait time (e.g., 15 seconds) into a **Virtual Distance Penalty**.
* **Formula:** `Added_Cost = Wait_Time_Seconds * CYCLIST_SPEED_MPS`.

---

## 3. Mathematical Formulation Guidelines

The final `weight_optimized` function should follow this structure to ensure stability and tunability:

1.  **Base Cost:** $Cost = Length$
2.  **Multipliers ($M$):** Factors that scale with length (Surface, Risk, Speed Stress, Width, TfL/Green Bonuses).
    * $M_{total} = 1.0 + \sum (Factor_i \times UserWeight_i)$
    * *Constraint:* Ensure $M_{total}$ never drops below a small positive epsilon (e.g., 0.1) to prevent zero or negative edge weights which break A*.
3.  **Additives ($A$):** Fixed costs added regardless of length (Signals, Barriers, Calming, Intersections).
    * $A_{total} = \sum (FixedCost_j \times UserWeight_j)$
4.  **Hill Cost ($H$):** (Existing implementation).

**Final Edge Weight Formula:**
$$Weight(u,v) = (Length \times M_{total}) + A_{total} + H$$

---

## 4. Frontend Requirements

**File:** `5_frontend/src/App.js`

The backend update is useless without UI controls. The following updates are required in the React application:

1.  **State Management:** Add state variables for all new weight factors (TfL Cycleways, Quietways, Speed, Width, Green, Barriers, etc.).
2.  **API Integration:** Update the `GET /route` fetch call to include these new parameters in the query string.
3.  **UI Components:**
    * Expand the "Control Panel" to accommodate the new toggles/sliders.
    * Consider grouping them (e.g., "Safety", "Comfort", "Scenery") to avoid clutter.
4.  **Route Visualization:** Ensure the "Optimized" polyline reflects these new choices (no change needed in rendering logic, just the data fetch).
5.  **Overlay:** When it makes sense use graphical overlays like in flat route or night mode to show the segments that fulfill this requirement. 
6.  **Route Analysis:** Come up with suitable analysis criteria for every mode and include it in the same manner as for current modes. 