# Island source readiness — Malpelo, Gorgona and eight minor-island candidates

Date: 14 November 2026. Repository: ColombiaTransit/colombia-height.

## Verified native DEM audit

[Successful GitHub Actions #43596436204](https://github.com/ColombiaTransit/colombia-height/actions/runs/43596436204) compared the original **137** selected Copernicus GLO-30 sources with one temporary extra COG per island. No source manifest was changed and no Terrain-RGB MBTiles were produced.

| Tested local metric | Malpelo, `N03_W082` | Gorgona, `N03_W079` |
| --- | ---: | ---: |
| Distinct local XYZ tiles tested at z11, z12 and z13 | 27 | 36 |
| Missing native DEM sample-pixels before adding temporary COG | 869,376 | 983,284 |
| Real source sample-pixels restored by candidate | 869,376 | 983,284 |
| Native DEM sample-pixels missing afterwards, **within tested tiles only** | **0** | **0** |
| Native COG assignment transitions between adjacent valid samples | 2,304 | 2,609 |
| Transitions with difference above 40 m | **0** | **5** |
| Maximum observed source-adjacent height gradient | 25.001 m | 62.829 m |
| Existing valid sample-height change | 0 m | 0 m |

**Counting caution:** The recovered sample totals sum across multiple zoom levels; they are *not unique independent 30m ground pixels* or a nationwide source coverage measurement. They refer only to the tested XYZ raster grids.

The five Gorgona transitions above 40 m are all in one coarser z11 tile, `11/579/1006`. There were no transitions above that threshold in the tested z12 or z13 tiles. A 40 m terrain gradient at coarse zoom is not by itself an error. The targeted original native 30m source-border investigation is available as [GitHub workflow](../.github/workflows/gorgona-native-border-review.yml), checking the N02/N03 boundary at 3° N near Gorgona and the N03/N04 boundary at 4° N near Malpelo. A source cannot be declared fully seam-certified solely from the statistics above.

## Eight previously nominated Natural Earth minor islands

The same successful workflow checked all eight registered polygon candidates in [data/minor-island-review.json](../data/minor-island-review.json), using each original COG's actual 30m DEM sample and z13 exact polygon pixel centers.

| Candidate | Study group | Native original sample height | z13 polygon land pixel centers | Missing native z13 DEM samples |
| --- | --- | ---: | ---: | ---: |
| ne_minor_01 | San Bernardo | 4.230 m | 844 | 0 |
| ne_minor_02 | San Bernardo | 2.987 m | 9,191 | 0 |
| ne_minor_03 | Serranilla | 0 m | 730 | 0 |
| ne_minor_04 | Serranilla | 0 m | 106 | 0 |
| ne_minor_05 | Serranilla | 0 m | 29 | 0 |
| ne_minor_06 | Serranilla | 0 m | 298 | 0 |
| ne_minor_07 | Serranilla | 0 m | 120 | 0 |
| ne_minor_08 | Bajo Nuevo | 0 m | 311 | 0 |
| **Total** | | | **11,629** | **0** |

The six 0-meter native point samples are **actual valid Copernicus COG values**, not fabricated water or patched NoData; this does not prove that these locations are naturally at sea level or that Natural Earth small-island outlines are accurate. Those six points particularly merit independent geographic/hydrographic review. Territorial classification remains **unverified** for all eight, and Quitasueño remains deliberately outside the project scope.

## Release and source-selection decision

- **Provisional engineering evidence:** The two omitted original COGs supply genuine DEM data in every tested island pixel. The original valid 137-source heights are unchanged; the exact 97 Malpelo and 86 Gorgona island-polygon gaps also recover completely in [earlier exact test #43594868906](https://github.com/ColombiaTransit/colombia-height/actions/runs/43594868906).
- **Still pending:** investigate Gorgona's five coarser z11 gradients on the original native 30m source boundary; approve Colombian terrestrial/island study scope using independent geographic evidence; perform national source-mask and all-zoom QA with approved additions.
- **Not authorized:** automatically promote the two COGs (or any of the 52 other candidate cells) to the permanent source inventory; assume outside OSM land equals ocean; synthesize 0 m ocean DEM; publish national Terrain-RGB MBTiles.

OSM coastline evidence, when reused: © OpenStreetMap contributors; ODbL 1.0 — https://www.openstreetmap.org/copyright. Natural Earth remains a provisional land-reference layer, not legal jurisdiction.

## Original 30m COG source-border diagnostic completed

[Successful native 30m edge test #43596823989](https://github.com/ColombiaTransit/colombia-height/actions/runs/43596823989) sampled **350 original native COG pixel locations** along each island's 1° latitude boundary, plus six rows inside each source. It also located all five previously reported z11 Gorgona gradients in the frozen tile `11/579/1006`.

| Edge | Sampled adjacent valid native pairs | Maximum original adjacent 30m difference | Disproportionate source-edge differences (>40m and >3× local gradient) |
| --- | ---: | ---: | ---: |
| Gorgona: original `N02_W079` versus staged `N03_W079` at 3° N | 350 | **24.725 m** | **0** |
| Malpelo: staged `N03_W082` versus original `N04_W082` at 4° N | 350 | **14.217 m** | **0** |

The five Gorgona z11 source transitions above 40m are located in a single north/south row near latitude 3.000° N. Their relative sizes are **0.899×, 1.334×, 1.377×, 1.444×, and 1.911×** the largest immediately adjacent same-source gradient. Thus none is an isolated >3× local pixel-gradient outlier. Their maximum coarse pixel difference remains **62.829 m**, and we preserve those observed values rather than erasing or smoothing them.

**Engineering disposition:** No evidence of an exceptional native 30m COG border discontinuity in these bounded samples. This is sufficient to propose both COGs for a controlled *staging* source list, not a full source-border certification or national release.

## Official geographic identity and strictly temporary source selection

Colombian Parques Nacionales Naturales directly documents [Santuario de Fauna y Flora Malpelo](https://www.parquesnacionales.gov.co/nuestros-parques/sff-malpelo/) and [Parque Nacional Natural Gorgona](https://www.parquesnacionales.gov.co/nuestros-parques/pnn-gorgona/). This supports their Colombian island identity; it does not replace high-resolution cadastral coastline or hydrographic verification for every pixel.

The reviewed, explicit allowlist is permanently recorded in [data/staged-island-source-selection-2026-11-14.json](../data/staged-island-source-selection-2026-11-14.json), requiring all exact OSM-native recovery and source-border QA run IDs.

[Successful staged-manifest workflow #43597073272](https://github.com/ColombiaTransit/colombia-height/actions/runs/43597073272) produced **`colombia_dem_manifest_island_staging_139.csv`**, containing exactly the original 137 verified COGs and these **two** extra original Copernicus COGs. The two verified upstream COG objects total **186,021 bytes**, both checked by HTTP HEAD; neither was created by resampling or height synthesis. The staged file is a one-day Actions artifact and can be regenerated by [`stage-two-island-sources.yml`](../.github/workflows/stage-two-island-sources.yml). The unchanged original source CSV was checked byte-for-byte during the job.

**The production 137-COG study input remains unchanged**. Staging is not a national feed publication. The other 50 COG candidates remain excluded from this staging variant. Tumaco `N01_W080`, although independently verified to recover Colombian IGAC-land height samples, must receive its own controlled source decision. Complete geographic, maritime, source-mask and all-zoom publication gates remain open.
