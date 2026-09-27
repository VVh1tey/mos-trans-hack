---
name: Диспетчерская городского транспорта
description: Calm transport operations workspace with burgundy selection and explicit risk semantics.
colors:
  accent: "#900b37"
  accent-hover: "#74072c"
  nav: "#202d39"
  ink: "#182638"
  muted: "#68758a"
  workspace: "#f5f6f7"
  surface: "#fff"
  border: "#e2e7ed"
  field-border: "#d8dfe7"
  focus: "#b86584"
  risk-low: "#24855b"
  risk-medium: "#bd7608"
  risk-high: "#b52238"
  nav-active: "#78233f"
  nav-indicator: "#d285a1"
  nav-text: "#eef1f4"
  hover: "#f1f3f6"
typography:
  headline:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-1px"
  title:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.3px"
  body:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  label:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 600
  metric:
    fontFamily: "Manrope, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.8px"
rounded:
  badge: "4px"
  control: "5px"
  feedback: "6px"
  panel: "8px"
  pill: "20px"
spacing:
  control-gap: "8px"
  compact-gap: "12px"
  panel-gap: "14px"
  section: "16px"
  workspace: "22px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  navigation-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-text}"
    padding: "16px 12px"
  route-number:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.badge}"
    padding: "3px 8px"
  risk-badge-high:
    textColor: "{colors.risk-high}"
---

# Design System: Диспетчерская городского транспорта

## Overview

**Creative North Star: "Спокойная диспетчерская"**

The approved reference screens define a calm, professional operator workspace: a light canvas, white surfaces, graphite navigation and restrained burgundy selection. This name describes that existing direction; it does not introduce a new visual identity.

Dense operational information remains scannable through compact typography, aligned numbers, thin dividers and a dominant geographic map. Decoration stays subordinate to route identity, predicted delay, confidence and telemetry freshness. Short Russian labels distinguish observed signals, forecasts and demonstration calculations.

**Key Characteristics:**

- Light surfaces and graphite navigation.
- Burgundy selection with separate risk colors.
- Large maps and compact, aligned operational data.
- Explicit freshness, forecast and demonstration labels.

## Colors

The palette combines cool light neutrals with a deep burgundy accent; amber, red and green communicate operational meaning.

### Primary

- **Burgundy (`accent`)** identifies primary actions, route number chips, active tabs, pins and selection. `accent-hover` strengthens primary button hover.
- **Navigation burgundy (`nav-active`)** and its lighter indicator identify the active destination on the graphite rail.

### Neutral

- **Graphite (`nav`)** anchors navigation; `nav-text` keeps its labels legible.
- **Dark ink (`ink`)** carries primary reading. `muted` supports metadata and freshness labels.
- **Light workspace (`workspace`)**, white `surface` and fine `border` separate working regions without heavy decoration.
- **Field border (`field-border`)** outlines editable controls; `focus` marks keyboard position.

### Operational semantics

- `risk-low` indicates low risk or confirmed normal status; it is not the brand accent.
- `risk-medium` indicates warning; `risk-high` indicates high predicted risk.
- Risk colors are configurable defaults. Keep legend, route segments, vehicle markers and textual badges consistent after a change.

**The Risk Meaning Rule.** Pair risk color with a label, value or legend; never turn a predicted disruption into a claim of a confirmed accident.

## Typography

Manrope is used throughout, with Arial and sans-serif fallbacks. Rounded letterforms soften the compact data layout while strong weights keep identifiers and numeric comparisons clear.

- **Headline:** page titles; smaller at compact widths and larger on wide displays.
- **Title:** panel headings; compact attention panels use a slightly smaller heading.
- **Body:** application text. Table content uses compact 11px text; metadata ranges from 8px to 11px according to context.
- **Label:** metric captions and navigation labels.
- **Metric:** prominent totals. Table cells, clocks, metric values, comparisons and vehicle delays use tabular numerals.

Vehicle detail gives its key delay a 48px reading. Page headings adapt to 34px above 1700px, 26px below 1000px and 25px below 760px. Preserve short Russian labels and keep long explanations in help text rather than large promotional headings.

## Layout

Desktop uses a fixed 116px navigation rail and a main workspace capped at 2050px. Default horizontal workspace padding is 22px. The network view places five compact metrics above a dominant map and a 340px attention column; operational tables sit below. The route view uses four metrics, the same map/attention relationship and a chart/stop-table pair. What-if uses a 285px parameter column with map and comparison results beside it.

At 1700px and above the rail grows to 132px, workspace padding to 28px and attention column to 370px. At 1250px and below, spacing compresses and the route chart/table stack. At 1000px and below, the rail becomes a 72px icon rail and table filters wrap. At 760px and below, navigation becomes a fixed 60px bottom bar; metrics use two columns, maps and attention stack, scenarios become one column, and tables retain horizontal scrolling. Settings and favorite routes remain reachable through mobile shortcuts. Mobile map height is 370px, or 330px in What-if.

Charts use fluid SVG geometry and readable labels rather than fixed desktop dimensions. Mobile content reserves 65px for bottom navigation; toast feedback appears above it.

## Elevation & Depth

Panels are flat white regions separated by thin borders. Shadows identify map overlays, vehicle markers and transient feedback rather than lifting every card. The map provides geographic depth; the vehicle drawer uses a tinted backdrop to separate its focused task.

- Map tools and legend: `0 3px 10px #283c471a`.
- Map caption: `0 2px 8px #293c4814`.
- Vehicle markers: `0 2px 5px #1f2e4259`.
- Toast: `0 5px 20px #1e2d3d33`.
- Drawer backdrop: `#15243a48`.

## Shapes

Gently rounded panels contain denser rectangular controls. Use the panel radius for cards/maps, control radius for fields/buttons and badge radius for route identifiers. Circles identify status dots, map stops and metric icon grounds. Risk badges remain light inline text with a colored dot. Active tabs use a straight burgundy underline; the desktop active navigation item uses a left indicator, becoming a top indicator on mobile.

## Components

### Buttons and inputs

Primary buttons use burgundy with white text; secondary buttons stay white with a fine border. Hover changes background and border. Disabled buttons reduce opacity to one half. Keyboard focus uses a 3px outline with a 3px offset; composite search fields use a 2px outline with a 2px offset. Inputs keep visible labels and burgundy caret color. Validation appears adjacent to the form in a pale red message.

### Panels, chips and navigation

Panels use a one-pixel border, rounded corners and clipped contents. Section headings combine a title and compact actions with a subtle divider. Route chips are compact solid burgundy identifiers. Navigation shows an active background and edge indicator; mobile links retain icon and text. Route tabs share the accent underline without introducing another navigation color.

### Maps and attention

Keep the map visually dominant. Floating caption, controls and risk legend sit on white surfaces. Vehicles use white-bordered colored markers; selected vehicles gain a burgundy ring, and a hypothetical additional vehicle uses a dashed outline. Attention rows expose route, vehicle, predicted delay, probability, signal and freshness. Selecting a vehicle opens a right drawer (400px desktop, 360px mobile, capped to viewport width).

### Operational tables and comparisons

Use subdued table headers, horizontal dividers and tabular numbers. Clicking a route opens a non-modal details panel on the current page. Its explicit “Перейти” action opens a new browser tab. Outline/filled burgundy stars toggle multiple favorites; they persist across tabs and sort first in the route catalog. The worst stop gets a pale risk tint. What-if compares baseline and scenario values, visibly identifies the illustrative calculation, and invalidates results when inputs change.

### Feedback and motion

Loading, empty results, retryable failures and stale data each need explicit text. Preserve the last successful snapshot when polling fails and pair it with an error/freshness indication. A loading spinner rotates linearly over one second; reduced-motion preference disables animation and transitions. The incumbent system does not use decorative motion.

## Do's and Don'ts

### Do:

- Do preserve the approved light burgundy and graphite reference direction.
- Do keep risk labels, map colors and configured thresholds consistent.
- Do retain visible keyboard focus and access to settings and favorite routes on mobile.
- Do distinguish demonstration data, predicted outcomes and telemetry freshness.

### Don't:

- Don't use green as the primary brand color.
- Don't describe an unconfirmed forecast as an accident or breakdown.
- Don't replace the operational map and compact data with decorative oversized cards.
- Don't present stale data or an invalidated scenario as a fresh result.
