# Frontend Design System

## 1. Product Design Direction

The frontend is an enterprise-grade maritime intelligence and vessel monitoring platform.

The interface should feel like an operational command center rather than a consumer application or marketing website.

Core visual characteristics:

* Dark enterprise interface
* High information density
* Map-first layout
* Compact data tables
* Strong spatial hierarchy
* Minimal decorative elements
* Clear operational status indicators
* Professional maritime / risk-management aesthetic
* Data should dominate the interface
* Controls should be compact and functional

The visual references may inspire layout, density, spacing, hierarchy, and interaction patterns, but the application must not reproduce third-party branding, logos, proprietary icons, or layouts pixel-for-pixel.

---

# 2. Design Principles

## 2.1 Information First

Every UI element should support one of the following:

* vessel identification
* vessel location
* voyage monitoring
* route prediction
* AIS history
* risk assessment
* sanctions screening
* operational alerts
* route evaluation
* geographic risk visualization

Avoid visual elements without operational value.

---

## 2.2 Map as a Primary Workspace

For vessel tracking and geographic risk pages, the map should be treated as the primary workspace.

Preferred layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ Global Header / Context Controls                            │
├──────────────┬───────────────────────────────────────────────┤
│              │                                               │
│ Navigation   │                                               │
│              │                Main Workspace                 │
│              │                                               │
│              │            Map / Table / Analytics            │
│              │                                               │
├──────────────┴───────────────────────────────────────────────┤
│ Optional Status / Event / Playback Bar                      │
└──────────────────────────────────────────────────────────────┘
```

On map-focused pages:

* map should normally occupy at least 60% of the usable workspace
* side panels should not unnecessarily reduce map visibility
* panels should be collapsible where appropriate
* map overlays should be compact and semi-opaque
* map interaction should remain available even when information panels are open

---

# 3. Color System

The following colors are project design tokens, not exact copies of any reference interface.

## 3.1 Background

```css
--bg-app: #111318;
--bg-sidebar: #17191F;
--bg-panel: #080B16;
--bg-panel-secondary: #151820;
--bg-elevated: #1C1F27;
--bg-hover: #242832;
```

Usage:

* `bg-app`: global application background
* `bg-sidebar`: persistent navigation
* `bg-panel`: major data panels
* `bg-panel-secondary`: charts and nested containers
* `bg-elevated`: dropdowns, tooltips, menus
* `bg-hover`: active row and hover state

---

## 3.2 Borders

```css
--border-primary: #262B35;
--border-secondary: #343A46;
--border-subtle: rgba(255,255,255,0.06);
```

Borders should generally be thin.

Avoid strong card shadows.

Hierarchy should primarily come from:

* spacing
* background contrast
* borders
* typography

rather than shadows.

---

## 3.3 Text

```css
--text-primary: #F3F4F6;
--text-secondary: #A6ABB5;
--text-muted: #6F7580;
--text-disabled: #505660;
```

Rules:

* important values use `text-primary`
* labels use `text-secondary`
* metadata uses `text-muted`
* disabled functions use `text-disabled`

---

## 3.4 Operational Colors

```css
--status-positive: #45C978;
--status-warning: #E3B341;
--status-critical: #E65252;
--status-info: #3EA6FF;
--status-neutral: #8B919D;
```

These colors must communicate meaning consistently.

### Green

Use for:

* normal
* active
* safe
* compliant
* positive change
* route adherence

### Yellow / Amber

Use for:

* caution
* elevated risk
* pending review
* warning area
* uncertainty

### Red

Use for:

* high risk
* critical alert
* sanctions hit
* route deviation
* system failure

### Blue

Use for:

* vessel position
* primary interactive state
* informational status
* selected objects

---

## 3.5 Interface Themes

Dark mode remains the default operational theme. A light enterprise theme is
also available for bright environments and must preserve the same information
density, spacing, status colors, and interaction hierarchy.

Theme switching must use shared semantic tokens rather than page-specific
business logic. Map-focused pages pair the dark interface with CARTO Dark
Matter and the light interface with CARTO Positron.

Status labels must remain readable in both themes. Insurance workflow and
vessel risk status labels use solid semantic color blocks with white text and
no glow.

---

# 4. Typography

Primary UI font:

```css
font-family:
  "IBM Plex Sans",
  ui-sans-serif,
  system-ui,
  -apple-system,
  BlinkMacSystemFont,
  "Segoe UI",
  sans-serif;
```

Recommended hierarchy:

```text
Page Title          18–22px / 600
Panel Title         13–15px / 600
Section Heading     10–11px / 600 / 0.08–0.12em
Body                13–14px / 400
Table Body          12–13px / 400
Table Header        10–11px / 600 / 0.04–0.08em
Metadata            10–11px / 500–600 / 0.06–0.10em
Navigation          13–14px / 400–500
Button              12–13px / 500
Numeric KPI         18–22px / 500–600
```

The interface should remain compact.

Avoid oversized marketing-style typography.

Use letter spacing only for section headings, metadata labels, table headers,
and system status labels. Body copy, vessel names, port names, client names,
and business names should retain natural letter spacing.

Operational numbers—including IMO, MMSI, coordinates, speed, heading, time,
financial values, and percentages—must use tabular numerals:

```css
font-variant-numeric: tabular-nums;
```

Load IBM Plex Sans through `next/font` and expose it as the global UI font to
avoid runtime CDN requests and minimize layout shift.

---

# 5. Spacing System

Use a 4px-based spacing scale.

```text
4px
8px
12px
16px
20px
24px
32px
```

Typical usage:

```text
table cell padding       8–12px
panel padding            12–16px
major section gap        16px
sidebar item height      40–44px
toolbar height           40–48px
global header height     44–52px
```

Avoid excessive whitespace.

This is a professional analytical system where screen real estate is valuable.

---

# 6. Layout System

## 6.1 Global Sidebar

Recommended width:

```text
Expanded: 200–220px
Collapsed: 52–64px
```

Primary navigation structure:

```text
Dashboard

Vessel Tracking

Routes

Voyages

Risk Monitor

Sanctions

Alerts

Analytics

Data Management

Settings
```

Navigation should use:

* icon
* label
* selected state
* subtle hover state

Selected state should use either:

* slim left indicator
* brighter foreground
* slightly elevated background

Do not use large colorful navigation buttons.

---

# 7. Global Header

The header is used for context rather than branding.

Potential controls:

```text
Current Vessel / Fleet
Date Range
Location
Voyage
Risk Filter
Search
Notification
User
```

The header should remain compact.

Avoid large logos or excessive branding.

---

# 8. Panel System

Panels are the primary structural primitive.

Recommended structure:

```text
┌──────────────────────────────────────┐
│ Panel Title              Controls    │
├──────────────────────────────────────┤
│                                      │
│            Panel Content             │
│                                      │
└──────────────────────────────────────┘
```

Panel characteristics:

* dark surface
* 1px border
* low or no shadow
* 2–4px radius
* compact header
* clear content hierarchy

Avoid large rounded cards.

Preferred border radius:

```text
2px – 6px
```

---

# 9. Table Design

Tables are a major UI pattern.

Tables should support:

* sticky header
* sorting
* filtering
* row selection
* hover
* compact density
* status badges
* contextual actions
* horizontal scrolling where necessary

Example vessel table:

```text
NAME
IMO
MMSI
TYPE
SOG
COG
DESTINATION
ETA
LAST AIS
RISK
STATUS
```

Table rows should remain visually compact.

Recommended row height:

```text
32–40px
```

Use tabular numbers where possible.

---

# 10. Status Badges

Badges should be rectangular and compact.

Examples:

```text
ACTIVE
IN PORT
UNDER WAY
WARNING
HIGH RISK
SANCTIONS HIT
ROUTE DEVIATION
AIS STALE
```

Avoid pill-shaped consumer-style badges unless space constraints justify them.

---

# 11. Maritime Map Design

The maritime map is one of the most important product surfaces.

Preferred map appearance:

* dark basemap
* low-saturation land
* dark ocean
* subtle administrative boundaries
* ports clearly visible
* vessel markers visually dominant
* risk zones semi-transparent
* predicted routes clearly distinguished

---

# 12. Vessel Marker System

Recommended vessel marker:

* triangular directional marker
* heading represented by marker rotation
* default vessel color: blue
* selected vessel: brighter cyan / blue
* warning vessel: amber
* critical vessel: red

Marker size should not overwhelm the map.

Cluster vessels at low zoom levels.

---

# 13. Route Visualization

Different route concepts must be visually distinguishable.

Suggested model:

```text
Historical AIS track
→ muted blue / gray line

Active voyage route
→ solid blue line

Predicted route
→ brighter blue or cyan line

Alternative route
→ dashed line

High-risk route segment
→ amber / red

Route deviation
→ red connector or deviation indicator
```

Do not rely only on color.

Use:

* line pattern
* opacity
* thickness
* labels

where necessary.

---

# 14. Risk Zone Visualization

Risk layers may include:

* JWC listed areas
* piracy
* war risk
* sanctions-related ports
* weather
* conflict zones
* chokepoints
* route anomalies

Risk polygons should use transparent fills.

Example:

```text
low risk       subtle
medium risk    amber
high risk      red
critical       stronger red outline
```

The map must remain readable underneath overlays.

---

# 15. Map Layer Control

Provide a compact layer selector.

Potential layers:

```text
Vessels

Ports

Historical Track

Predicted Route

Route Corridor

JWC Areas

War Risk

Piracy

Weather

Sanctions

Alerts
```

Users should be able to toggle layers independently.

---

# 16. Vessel Detail Panel

Recommended vessel detail structure:

```text
VESSEL NAME

IMO
MMSI
Call Sign
Flag
Ship Type

────────────

NAVIGATION

Latitude
Longitude
SOG
COG
Heading
Navigation Status
Last AIS

────────────

VOYAGE

Origin
Destination
ETA

────────────

RISK

Overall Risk
War Risk
Sanctions
Route Deviation
AIS Freshness
```

Important values should be visually stronger than labels.

---

# 17. Dashboard

Dashboard should provide operational awareness.

Possible modules:

```text
Tracked Vessels
Active Voyages
High Risk Vessels
Route Deviations
AIS Stale
Sanctions Alerts
JWC Exposure
Recent Alerts
```

Avoid unnecessary KPI cards.

Each KPI must correspond to a meaningful operational condition.

---

# 18. Charts

Charts should use the same dark analytical aesthetic.

Rules:

* minimal grid lines
* clear axis labels
* muted secondary lines
* highlighted active series
* no unnecessary gradients
* compact legends
* visible tooltip
* no 3D charts

Potential charts:

```text
SOG history

Route deviation distance

Prediction error

AIS coverage

Fleet risk distribution

Voyage exposure

Historical risk events
```

---

# 19. Route Evaluation UI

Route evaluation should emphasize quantitative metrics.

Suggested metrics:

```text
Mean Error
Median Error
P90 Error
Max Error
Route Adherence
Progress Ratio
Evaluation Points
```

Use numerical formatting consistently.

Example:

```text
Mean Error
14.2 NM

P90 Error
28.6 NM

Adherence
87.4%
```

---

# 20. Interaction Principles

Hover should reveal additional information without disturbing layout.

Clicking a vessel should:

```text
select vessel
→ highlight marker
→ open vessel detail
→ optionally focus map
```

Do not automatically zoom aggressively unless explicitly requested.

---

# 21. Loading States

Use:

* skeleton rows
* subtle loading indicator
* panel-local loading states

Avoid full-screen loading unless the application itself cannot initialize.

---

# 22. Empty States

Empty state language should be operational.

Good:

```text
No AIS positions found for this period.
```

Bad:

```text
Oops! Nothing here yet!
```

---

# 23. Error States

Errors should clearly state:

```text
what failed
whether data may be stale
what the user can do
```

Example:

```text
Unable to retrieve the latest AIS position.

Last successful update:
14 Aug 2026 21:32 UTC
```

---

# 24. Responsive Strategy

Primary target:

```text
Desktop
1440px–1920px
```

Secondary target:

```text
Laptop
1280px+
```

Tablet and mobile support are secondary.

For narrow displays:

* sidebar collapses
* secondary panels become drawers
* table horizontal scrolling is allowed
* map remains the primary surface

Do not compromise desktop information density merely to achieve mobile symmetry.

---

# 25. Component Philosophy

Prefer reusable primitives.

Core components may include:

```text
AppShell
Sidebar
TopBar
Panel
PanelHeader
DataTable
StatusBadge
Metric
Tabs
FilterBar
SearchInput
MapToolbar
MapLayerControl
VesselMarker
VesselDetailPanel
RiskIndicator
RouteLegend
Timeline
PlaybackControl
ChartPanel
AlertRow
```

Avoid building every page independently.

---

# 26. Visual Style to Avoid

Do not use:

* excessive gradients
* glassmorphism
* neon cyberpunk aesthetic
* large rounded cards
* oversized headings
* decorative illustrations
* marketing website layouts
* excessive animation
* glowing borders
* large empty whitespace
* consumer mobile-app styling
* random accent colors

The interface should resemble professional operational software.

---

# 27. Product Personality

The application should feel:

```text
Precise
Analytical
Professional
Controlled
Technical
Operational
Dense
Reliable
```

It should not feel:

```text
Playful
Lifestyle-oriented
Futuristic for its own sake
Game-like
Marketing-oriented
Decorative
```

---

# 28. Reference Interpretation

The provided reference screenshots are used specifically for:

* dark color direction
* information density
* narrow sidebar
* panel hierarchy
* compact controls
* dark maps
* tables embedded in dashboards
* map overlays
* professional trading-terminal-like feel

They must not be used to reproduce:

* Owari branding
* Owari logo
* exact proprietary layout
* exact typography
* proprietary icons
* exact colors
* third-party content

The final interface should develop its own maritime risk-management identity.
