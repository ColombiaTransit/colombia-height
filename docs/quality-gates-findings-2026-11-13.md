# DEM QA findings — 2026-11-13

This record summarizes the successful read-only diagnostic
[run 43417941461](https://github.com/ColombiaTransit/colombia-height/actions/runs/43417941461).
It is retained in the repository because one-day GitHub Actions artifacts expire.

## Four-source junction, 74° W / 6° N

A z10 Web Mercator terrain pixel spans an appreciable ground distance.
Absolute difference between adjacent output pixel-center heights is
**not** sufficient to diagnose source discontinuities.

| Metric (metres) | East-west neighboring source switch | North-south neighboring source switch |
| --- | ---: | ---: |
| Observed source-switch pairs | 256 | 256 |
| Largest source-switch elevation delta | 111.4229 | 225.3751 |
| Source-switch p95 | 62.5623 | 116.2687 |
| Same-source p95 | 69.7925 | 66.7809 |
| Same-source p99 | 102.0270 | 112.0526 |
| Source-switch pairs above 100 m | 1 | 17 |

**Finding:** The previously observed 225.375m north-south delta is
reproduced. No assertion of bad DEM stitching is justified without
testing native-resolution pixels and immediate same-source slopes.
These metre deltas do **not** represent the previously validated
0.05m *Terrain-RGB vs native-source reference* encoding discrepancy.

**Next check:** sample around the exact 6° parallel at original
Copernicus pixel resolution using native source arrays, then compare
cross-boundary deltas against gradients immediately 1–5 native pixels
inside both source COGs. Record actual sampling distance and terrain
slope; do not 'smooth' or interpolate source heights until diagnosed.

## Six 3x3 tile areas at zoom 11

Each area contains 9 × 256² = 589,824 sampled output pixels.
Natural Earth 1:10m land/minor islands is used **only** as a geographic
reference, not an official country boundary or ocean classifier.

| Site | Complete tiles | Missing inside NE land | Missing outside NE land |
| --- | ---: | ---: | ---: |
| Cartagena | 9/9 | 0 | 0 |
| Buenaventura | 9/9 | 0 | 0 |
| San Andrés | 9/9 | 0 | 0 |
| Providencia | 9/9 | 0 | 0 |
| Malpelo | 9/9 | 0 | 0 |
| Tumaco | 8/9 | 0 | 23,384 |

**Finding:** This sampled 3×3 area around Tumaco includes one
incomplete output tile; the missing values are outside the selected
Natural Earth land polygons. 'Outside' does not prove ocean. Do not
represent this gap as valid height 0 or as an RGB 0,0,0 trench.

**Next check:** identify precise z/x/y and source nodata footprint for
Tumaco, compare with coastline reference and original COG masks. Keep
the tile excluded if any missing required land elevations remain.

## Release state

`national_publication_allowed = false`.

Completed, successful stage: small and medium batch merges and
coast/island sample tests. The north-south sample and Tumaco gap have targeted follow-up results\nrecorded below. Still pending: authoritative island boundary/scope,\ncountrywide completeness, source-edge sampling and ownership.
No national output is authorized by this report.

## Follow-up — targeted per-case investigation, run 43419286112

[Successful independent jobs](https://github.com/ColombiaTransit/colombia-height/actions/runs/43419286112)
used original source COG sampling for case 1 and a tile-specific
pixel/provenance mask for case 2. The first attempt
[43418992885](https://github.com/ColombiaTransit/colombia-height/actions/runs/43418992885)
exposed an invalid assumption that native COG footprint bounds
exactly equal integer-degree lines; sampling was corrected to the
actual northern/southern pixel-edge transforms.

### Case 1 — Native pixel seam near 6°N: targeted diagnostic complete

In **each** of the N05/N06 source pairs at 75°W and 74°W,
350 longitude points were measured at native COG edge pixels,
along with five consecutive within-source steps.

| 1° longitude cell | Native border maximum | Median | p95 | Samples | Investigative seam flags |
| --- | ---: | ---: | ---: | ---: | ---: |
| W075 | 31.861 m | 3.689 m | 15.899 m | 350 | 0 |
| W074 | 41.881 m | 4.490 m | 19.443 m | 350 | 0 |

Flags require border delta **>40m and >3× both immediate local
native-pixel gradients**. No samples met both conditions.
The previous 225.375m difference was measured between much more
widely spaced zoom-10 pixel centers, not at the native COG edge
pixels. The new result therefore **does not support an obvious
artificial source seam in these sampled areas**. It also does not
prove absence of localized source errors between the samples, nor
validate every national COG edge. No smoothing or height correction
was applied.

**Case disposition:** sampled 6°N transition cleared for further
regional **testing**, not blanket national publication.

### Case 2 — Tumaco missing tile: cause and strict treatment identified

The **only** incomplete tile in the nine tested zoom-11 tiles is:

- XYZ: **11/574/1012**; TMS y = **1035**
- Full tile bbox: W **-79.1015625** to **-78.9257812**;
  N **1.9332268** to **2.1088987**
- Missing subset bbox: W **-79.1015625** to **-78.9999390**;
  N **2.0004784** to **2.1088987**
- Missing output pixels: **23,384**, none within the Natural
  Earth 10m land reference used for this test
- All **64 sampled missing pixels** were outside the spatial
  extent of the available downloaded native Copernicus COGs
- Sources present in the batch include N01_W079, N01_W080,
  and N02_W079; the missing upper-left patch falls outside
  their footprints.

**Case disposition:** the observed missing region is consistent
with **no available source COG coverage** in the offshore patch,
rather than lost data from batch merges. It must remain missing;
never fill with 0m or -10000m. The strict complete-tile policy
excludes XYZ 11/574/1012 from production until a separate
publication-approved over-water / partial-tile policy is defined.
Natural Earth outside-land is not itself proof of sea.
Official coastline and island boundaries remain a countrywide
publication prerequisite.

### Release gate

The two identified local anomalies have now been analyzed to
a usable **test-level disposition**. Neither result authorizes
national release. The remaining gates are the nationwide source mask,
territorial geometry and island coverage, complete/partial tile
policy and systematic COG edge QA.
