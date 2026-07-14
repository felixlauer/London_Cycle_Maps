# CSR A* Phase B report

Generated: 2026-07-11T11:59:10.200742+00:00
Repeats (median): 1
CSR build: 29.36s (1,924,143 nodes, 4,061,447 arcs)
ε optimized: 0.75 | ε fastest: 0.0
Parity OK: 88/88

## Summary (CSR modes)

- Mean nodes → phase_b: **1.354×**
- Mean phase_a → phase_b: **1.050×**
- Mean NX nodes_h → NX csr_h: **1.140×**

## Per-route CSR heuristic modes

| Preset | Route | Leg | nodes s | A s | B s | nodes→B | A→B | Exp | Path | OK |
|--------|-------|-----|---------|-----|-----|---------|-----|-----|------|----|
| fast | route 1: Imperial to Kings Cross | fastest | 0.472 | 0.198 | 0.190 | 2.485× | 1.044× | 28160 | Y | Y |
| fast | route 1: Imperial to Kings Cross | optimized | 1.120 | 0.789 | 0.781 | 1.434× | 1.011× | 59802 | Y | Y |
| fast | route 2: Imperial to Greenwich | fastest | 0.908 | 0.668 | 0.629 | 1.443× | 1.061× | 88187 | Y | Y |
| fast | route 2: Imperial to Greenwich | optimized | 2.856 | 2.220 | 1.938 | 1.474× | 1.145× | 138623 | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | fastest | 1.271 | 0.731 | 0.690 | 1.841× | 1.060× | 96319 | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | optimized | 4.985 | 3.882 | 3.877 | 1.286× | 1.001× | 250522 | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | fastest | 0.711 | 0.392 | 0.370 | 1.922× | 1.061× | 54897 | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | optimized | 4.418 | 3.331 | 3.160 | 1.398× | 1.054× | 223381 | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | fastest | 0.934 | 0.631 | 0.601 | 1.553× | 1.050× | 79576 | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | optimized | 5.715 | 4.700 | 4.567 | 1.251× | 1.029× | 296174 | Y | Y |
| fast | route 6: Battersea Park to Temple | fastest | 0.060 | 0.044 | 0.043 | 1.381× | 1.016× | 7439 | Y | Y |
| fast | route 6: Battersea Park to Temple | optimized | 1.167 | 0.906 | 0.889 | 1.311× | 1.019× | 49596 | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | fastest | 0.153 | 0.121 | 0.118 | 1.295× | 1.029× | 17782 | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | optimized | 0.447 | 0.415 | 0.401 | 1.114× | 1.034× | 28615 | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | fastest | 0.608 | 0.303 | 0.288 | 2.108× | 1.050× | 40338 | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | optimized | 2.787 | 3.162 | 3.156 | 0.883× | 1.002× | 142124 | Y | Y |
| fast | route 9: Earls court to Piccadilly | fastest | 0.013 | 0.013 | 0.010 | 1.216× | 1.202× | 1481 | Y | Y |
| fast | route 9: Earls court to Piccadilly | optimized | 0.387 | 0.362 | 0.363 | 1.064× | 0.997× | 24848 | Y | Y |
| fast | route 10: Bromley to Ealing | fastest | 3.682 | 2.621 | 2.345 | 1.570× | 1.118× | 290225 | Y | Y |
| fast | route 10: Bromley to Ealing | optimized | 12.889 | 11.396 | 9.038 | 1.426× | 1.261× | 621901 | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | fastest | 0.129 | 0.107 | 0.099 | 1.302× | 1.080× | 16307 | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | optimized | 0.360 | 0.317 | 0.328 | 1.099× | 0.966× | 23869 | Y | Y |
| safe | route 1: Imperial to Kings Cross | fastest | 0.245 | 0.204 | 0.188 | 1.305× | 1.087× | 28160 | Y | Y |
| safe | route 1: Imperial to Kings Cross | optimized | 0.828 | 0.734 | 0.723 | 1.144× | 1.015× | 52192 | Y | Y |
| safe | route 2: Imperial to Greenwich | fastest | 0.790 | 0.729 | 0.691 | 1.143× | 1.055× | 88187 | Y | Y |
| safe | route 2: Imperial to Greenwich | optimized | 1.782 | 1.542 | 1.555 | 1.146× | 0.992× | 103392 | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | fastest | 0.944 | 0.783 | 0.831 | 1.135× | 0.942× | 96319 | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | optimized | 5.591 | 4.797 | 3.785 | 1.477× | 1.267× | 226185 | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | fastest | 0.522 | 0.392 | 0.403 | 1.295× | 0.970× | 54897 | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | optimized | 2.172 | 1.832 | 2.036 | 1.067× | 0.900× | 128110 | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | fastest | 0.776 | 0.579 | 0.546 | 1.421× | 1.060× | 79576 | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | optimized | 2.604 | 2.303 | 2.311 | 1.127× | 0.997× | 159197 | Y | Y |
| safe | route 6: Battersea Park to Temple | fastest | 0.111 | 0.060 | 0.046 | 2.413× | 1.308× | 7439 | Y | Y |
| safe | route 6: Battersea Park to Temple | optimized | 0.083 | 0.077 | 0.081 | 1.031× | 0.948× | 6078 | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | fastest | 0.137 | 0.119 | 0.120 | 1.144× | 0.996× | 17782 | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | optimized | 0.400 | 0.389 | 0.415 | 0.964× | 0.936× | 27670 | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | fastest | 0.399 | 0.283 | 0.248 | 1.607× | 1.139× | 40338 | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | optimized | 1.149 | 0.984 | 0.956 | 1.203× | 1.030× | 73084 | Y | Y |
| safe | route 9: Earls court to Piccadilly | fastest | 0.012 | 0.011 | 0.010 | 1.206× | 1.076× | 1481 | Y | Y |
| safe | route 9: Earls court to Piccadilly | optimized | 0.184 | 0.176 | 0.170 | 1.084× | 1.037× | 13348 | Y | Y |
| safe | route 10: Bromley to Ealing | fastest | 2.771 | 2.271 | 2.266 | 1.223× | 1.002× | 290225 | Y | Y |
| safe | route 10: Bromley to Ealing | optimized | 9.120 | 8.561 | 8.102 | 1.126× | 1.057× | 541202 | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | fastest | 0.119 | 0.100 | 0.094 | 1.265× | 1.058× | 16307 | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | optimized | 0.828 | 0.707 | 0.690 | 1.200× | 1.025× | 54447 | Y | Y |

## NX heuristic: G.nodes vs CSR arrays

| Preset | Route | Leg | NX nodes_h s | NX csr_h s | Speedup | Exp | Path | OK |
|--------|-------|-----|--------------|------------|---------|-----|------|----|
| fast | route 1: Imperial to Kings Cross | fastest | 0.361 | 0.342 | 1.055× | 28160 | Y | Y |
| fast | route 1: Imperial to Kings Cross | optimized | 1.161 | 1.056 | 1.099× | 59802 | Y | Y |
| fast | route 2: Imperial to Greenwich | fastest | 1.174 | 1.003 | 1.171× | 88187 | Y | Y |
| fast | route 2: Imperial to Greenwich | optimized | 2.847 | 2.691 | 1.058× | 138623 | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | fastest | 1.492 | 1.174 | 1.271× | 96319 | Y | Y |
| fast | route 3: Imperial to New Spitalfields Market | optimized | 5.574 | 4.758 | 1.172× | 250522 | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | fastest | 1.078 | 0.652 | 1.653× | 54897 | Y | Y |
| fast | route 4: Twickenham Stadium to St. Pauls | optimized | 5.562 | 4.436 | 1.254× | 223381 | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | fastest | 1.292 | 1.013 | 1.276× | 79576 | Y | Y |
| fast | route 5: Wembley Stadium to Kings College Hospital | optimized | 7.093 | 6.280 | 1.129× | 296174 | Y | Y |
| fast | route 6: Battersea Park to Temple | fastest | 0.074 | 0.095 | 0.783× | 7439 | Y | Y |
| fast | route 6: Battersea Park to Temple | optimized | 1.188 | 1.088 | 1.092× | 49596 | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | fastest | 0.212 | 0.204 | 1.041× | 17782 | Y | Y |
| fast | route 7: Putney bridge to Notting Hill | optimized | 0.590 | 0.583 | 1.012× | 28615 | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | fastest | 0.792 | 0.529 | 1.498× | 40338 | Y | Y |
| fast | route 8: Tottenham Stadium to Hampstead | optimized | 4.000 | 2.994 | 1.336× | 142124 | Y | Y |
| fast | route 9: Earls court to Piccadilly | fastest | 0.017 | 0.017 | 0.977× | 1481 | Y | Y |
| fast | route 9: Earls court to Piccadilly | optimized | 0.483 | 0.509 | 0.948× | 24848 | Y | Y |
| fast | route 10: Bromley to Ealing | fastest | 6.081 | 4.055 | 1.500× | 290225 | Y | Y |
| fast | route 10: Bromley to Ealing | optimized | 19.947 | 13.102 | 1.522× | 621901 | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | fastest | 0.180 | 0.166 | 1.088× | 16307 | Y | Y |
| fast | route 11: Hill route, Elmers End to Streatham | optimized | 0.430 | 0.460 | 0.936× | 23869 | Y | Y |
| safe | route 1: Imperial to Kings Cross | fastest | 0.342 | 0.330 | 1.035× | 28160 | Y | Y |
| safe | route 1: Imperial to Kings Cross | optimized | 1.028 | 1.016 | 1.012× | 52192 | Y | Y |
| safe | route 2: Imperial to Greenwich | fastest | 1.135 | 1.083 | 1.048× | 88187 | Y | Y |
| safe | route 2: Imperial to Greenwich | optimized | 2.384 | 2.213 | 1.077× | 103392 | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | fastest | 1.551 | 1.318 | 1.177× | 96319 | Y | Y |
| safe | route 3: Imperial to New Spitalfields Market | optimized | 6.638 | 4.566 | 1.454× | 226185 | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | fastest | 0.753 | 0.663 | 1.136× | 54897 | Y | Y |
| safe | route 4: Twickenham Stadium to St. Pauls | optimized | 2.761 | 2.427 | 1.137× | 128110 | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | fastest | 1.181 | 0.897 | 1.316× | 79576 | Y | Y |
| safe | route 5: Wembley Stadium to Kings College Hospital | optimized | 3.432 | 3.044 | 1.127× | 159197 | Y | Y |
| safe | route 6: Battersea Park to Temple | fastest | 0.077 | 0.073 | 1.055× | 7439 | Y | Y |
| safe | route 6: Battersea Park to Temple | optimized | 0.102 | 0.096 | 1.064× | 6078 | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | fastest | 0.193 | 0.184 | 1.048× | 17782 | Y | Y |
| safe | route 7: Putney bridge to Notting Hill | optimized | 0.487 | 0.464 | 1.050× | 27670 | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | fastest | 0.500 | 0.454 | 1.103× | 40338 | Y | Y |
| safe | route 8: Tottenham Stadium to Hampstead | optimized | 1.427 | 1.329 | 1.074× | 73084 | Y | Y |
| safe | route 9: Earls court to Piccadilly | fastest | 0.016 | 0.014 | 1.135× | 1481 | Y | Y |
| safe | route 9: Earls court to Piccadilly | optimized | 0.224 | 0.220 | 1.016× | 13348 | Y | Y |
| safe | route 10: Bromley to Ealing | fastest | 3.711 | 3.569 | 1.040× | 290225 | Y | Y |
| safe | route 10: Bromley to Ealing | optimized | 11.163 | 10.825 | 1.031× | 541202 | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | fastest | 0.171 | 0.154 | 1.109× | 16307 | Y | Y |
| safe | route 11: Hill route, Elmers End to Streatham | optimized | 0.962 | 0.925 | 1.040× | 54447 | Y | Y |

JSON: `0_documentation/testing/csr_astar_phase_b_report.json`

---

## Analysis (11 Jul 2026) — CSR Phase B

**Decision:** Phase B is a **small incremental win** on top of Phase A — keep it (radians are production default; NX/bi use CSR arrays). **Do not expect another Phase-A-sized jump.** Next real gain is **Phase C (Numba)**.

### Headline

| Layer | Result |
|-------|--------|
| Parity (path / exp / cost) | **88/88** OK |
| Mean CSR nodes → phase_b | **1.354×** (lat/lon arrays were the big heuristic win; already in A) |
| Mean CSR phase_a → phase_b | **1.050×** (~5% from radian/`cos_lat` precompute) |
| Mean NX nodes_h → NX csr_h | **1.140×** |
| Bromley fast A→B | **2.62 → 2.35 s** (**1.12×**) |
| Bromley fast opt A→B | **11.40 → 9.04 s** (**1.26×**) |
| Bromley safe opt A→B | **8.56 → 8.10 s** (**1.06×**) |

### Notes

- `nodes` → `phase_b` mostly re-measures the lat/lon array win that shipped with Phase A.
- `phase_a` → `phase_b` is the true Phase B delta: **~5% mean**, noisy on short legs (some &lt;1× from run variance with `REPEATS=1`).
- NX heuristic wiring helps when `CSR_ASTAR=0` / `?alg=bi` (~**1.14×** mean); not the uni production path.
- Bench: `SKIP_DISRUPTION_FETCH=1`, `ε_opt=0.75`, live=False.

**Bottom line:** Keep Phase B on. Treat A→B as hygiene; prioritize Numba for the next order-of-magnitude cut.
