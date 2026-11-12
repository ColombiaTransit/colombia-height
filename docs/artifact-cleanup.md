# Temporary artifact cleanup

All test workflow artifacts now use GitHub Actions' minimum `retention-days: 1`.
This applies to **new** artifacts only; older artifacts keep their existing
expiration until explicitly deleted.

A manual and daily scheduled [Cleanup Temporary DEM Artifacts](../.github/workflows/cleanup-artifacts.yml)
workflow deletes **only artifacts produced by finished workflow runs** whose
names match these explicit prefixes:

- `colombia-dem-inventory`
- `medellin-terrain-rgb-pilot`
- `antioquia-terrain-rgb-pilot`
- `antioquia-terrain-strict`
- `colombia-coast-island-audit-`

The scheduled cleanup deletes matching finished-run artifacts older than 24
hours. The manual workflow defaults to deletion with a minimum age of 0 hours
to allow immediate cleanup of previous finished tests. Use mode `dry-run`
to inspect the candidate list without deleting anything.

No release assets, git content, action logs, or package data are deleted.
Do not use the temporary Actions artifacts as permanent storage for validated
national elevation datasets; publish accepted products separately.

To clean historic completed test runs **right now**:
Actions → Cleanup Temporary DEM Artifacts → Run workflow →
mode=`delete`, minimum_age_hours=`0`.
The workflow prints artifact IDs, names, reclaimed nominal bytes and totals.
