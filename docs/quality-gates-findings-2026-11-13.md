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
coast/island sample tests. Pending: investigate the north-south native
source junction, analyze Tumaco gap, verify authoritative island
boundary/scope and countrywide completeness and ownership.
No national output is authorized by this report.
