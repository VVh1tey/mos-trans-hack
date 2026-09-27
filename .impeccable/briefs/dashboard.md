# Dispatcher dashboard

Mode: Operate. Seed: inherited-user-references (no new visual world).

## Task
Implement user's three supplied PNGs as a working React/TypeScript/MapLibre app:
network, route and What-if. Real HTTP mock backend; genuine route geometry from
data/additional. Network operator and route operator need risks, telemetry freshness,
history and a hypothetical additional-vehicle comparison.

## First viewport
Dark graphite navigation, light workspace, burgundy selection, five network KPI
panels, a dominant map with risk-colored lines and vehicles, attention list on right,
route table underneath. Route keeps the vocabulary, four KPIs, route map, stops/chart.

## Signature interaction
Clicking a map line or catalog row opens route details on the current page. Only
the explicit Go action opens a new browser tab. Star multiple favorites, persisted
across tabs and sorted first in the catalog. Select vehicle to inspect forecast. What-if submits parameters
to API and compares baseline with scenario; changed parameters invalidate the result.

## Visual authority
frontend/references/notes.md and three PNGs therein. Preserve their palette, topology,
calm analytic density. Actual geography replaces fictitious geography in the concepts.

## Behavior and states
Real API polling; explicit demo labeling; errors with retry, last-good snapshot,
empty filters, loading, keyboard focus, responsive mobile layout. What-if is an
illustrative formula, not a learned model. Geographic stop association approximate.

## Verification
1600×1000 desktop and 390×844 mobile for all three screens. Playwright interaction
tests, Python provider consistency tests, tsc/Vite build. No Docker daemon available.
