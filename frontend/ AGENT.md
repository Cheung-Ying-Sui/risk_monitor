# AGENTS.md

## Project

This repository contains the frontend for an enterprise maritime vessel tracking and risk intelligence platform.

The frontend is built with:

* Next.js
* React
* TypeScript
* App Router
* Tailwind CSS

The Python backend is developed separately and may continue to change during frontend development.

---

# 1. Scope of Work

Unless explicitly instructed otherwise:

* modify only files inside the frontend project
* do not modify the Python backend
* do not move backend files
* do not rename backend modules
* do not change Supabase schemas
* do not change database migrations
* do not modify backend API behavior

Frontend work must remain isolated from unfinished backend development.

---

# 2. Architecture Principle

The frontend must not directly depend on Python implementation details.

Frontend code should interact with backend capabilities only through explicit interfaces such as:

```text
HTTP API

Supabase API

typed frontend service layer
```

Never import, parse, execute, or depend directly on Python files.

---

# 3. Technology Rules

Use:

```text
Next.js
React
TypeScript
App Router
Tailwind CSS
```

Do not introduce another frontend framework.

Do not introduce a component library without explicit approval.

Do not install new npm dependencies unless they provide clear functional value.

Before adding a dependency:

1. explain why it is required
2. check whether existing dependencies already solve the problem
3. prefer mature and actively maintained packages
4. keep dependency count low

---

# 4. TypeScript

Use strict and explicit TypeScript types.

Avoid:

```typescript
any
```

unless there is a documented technical reason.

Prefer:

```typescript
interface Vessel {
  id: string;
  mmsi: string;
  imo?: string;
  name: string;
}
```

Domain entities should have centralized types.

Recommended location:

```text
src/types/
```

---

# 5. Project Structure

Prefer the following organization:

```text
src/

  app/
    dashboard/
    vessels/
    routes/
    risk/
    sanctions/

  components/
    layout/
    navigation/
    map/
    vessel/
    route/
    risk/
    charts/
    tables/
    ui/

  lib/

  services/

  hooks/

  types/

  utils/
```

Do not place large amounts of reusable logic directly inside page components.

---

# 6. Page Components

Page files should primarily handle:

* page composition
* loading boundaries
* data orchestration
* route-specific behavior

They should not contain large reusable UI implementations.

Extract repeated UI into components.

---

# 7. Component Rules

Prefer small reusable components.

Good:

```text
VesselTable
VesselRow
VesselStatusBadge
VesselDetailPanel
RouteMetrics
RiskBadge
MapLayerControl
```

Avoid giant components that combine:

```text
data fetching
business logic
map logic
table logic
layout
filters
modals
```

into one file.

---

# 8. Design System

The UI must follow `FRONTEND_DESIGN_SYSTEM.md`.

The core visual direction is:

```text
dark enterprise interface
high information density
map-first
compact
analytical
operational
professional
```

The provided screenshots are visual references only.

Do not copy third-party branding or reproduce any reference interface pixel-for-pixel.

---

# 9. Color Usage

Use centralized design tokens.

Do not repeatedly hard-code colors inside individual components.

Prefer CSS variables or centralized Tailwind theme tokens.

Core semantic colors:

```text
green  → normal / safe / active

amber  → warning / elevated risk

red    → critical / sanctions / deviation

blue   → vessel / selection / information

gray   → neutral / secondary information
```

Color must have consistent semantic meaning across the entire application.

---

# 10. UI Density

This is an analytical workstation.

Prefer:

```text
compact spacing
compact table rows
compact controls
dense information layout
```

Avoid:

```text
large whitespace
large rounded cards
oversized headings
marketing layouts
```

---

# 11. Borders and Cards

Prefer:

```text
thin borders
low border radius
subtle panel separation
little or no box shadow
```

Recommended radius:

```text
2px–6px
```

Do not use large 16px–24px rounded cards unless specifically requested.

---

# 12. Navigation

Use a persistent left navigation sidebar.

Initial information architecture:

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

The sidebar should support a future collapsed state.

---

# 13. Map-First Principle

For vessel monitoring pages, the map is the primary workspace.

Do not reduce the map to a decorative card.

The map should normally occupy the majority of available content space.

Information panels may overlay or sit beside the map.

Where useful, panels should be collapsible.

---

# 14. Vessel Map Behavior

Vessel markers should communicate heading.

Preferred marker:

```text
directional triangular marker
```

Default meaning:

```text
blue    normal vessel
amber   warning vessel
red     critical vessel
```

Selected vessels should be visually distinct.

Do not use oversized markers.

---

# 15. Map Layers

Design the map system so additional layers can be added without rebuilding the map.

Potential layers include:

```text
Vessels
Ports
Historical Track
Predicted Route
Route Corridor
JWC Listed Areas
War Risk
Piracy
Weather
Sanctions
Alerts
```

Layer state should be modular.

---

# 16. Route Types

Different route types must be visually distinguishable.

Support the concepts:

```text
historical AIS track

current voyage route

predicted route

alternative route

high-risk segment

route deviation
```

Do not rely only on color to distinguish them.

---

# 17. Data Tables

Tables are first-class UI elements.

They should support future functionality such as:

```text
sorting
filtering
search
selection
pagination
status indicators
```

Keep rows compact.

Do not turn tabular operational data into large cards.

---

# 18. Charts

Charts should use a restrained analytical style.

Avoid:

```text
3D charts
large animations
gradients
decorative effects
```

Charts should emphasize accurate comparison and readable values.

---

# 19. Loading State

Do not leave blank panels during loading.

Use localized loading states.

Prefer:

```text
skeleton
small spinner
loading row
```

Avoid blocking the entire application unless necessary.

---

# 20. Error Handling

Never silently fail.

User-visible data errors should communicate:

```text
what failed

whether displayed data may be stale

last successful update if available
```

Errors should not expose internal stack traces to the user.

---

# 21. Empty States

Use precise operational language.

Good:

```text
No AIS positions found for the selected period.
```

Avoid casual wording.

---

# 22. API Layer

Do not scatter `fetch()` calls throughout UI components.

Prefer centralized API/service modules.

Recommended structure:

```text
src/services/vessels.ts

src/services/routes.ts

src/services/risk.ts

src/services/sanctions.ts
```

Page and component code should consume typed service functions.

---

# 23. Backend Instability

The backend is still under development.

Therefore:

* avoid assumptions about undocumented backend behavior
* isolate API contracts
* use adapters where necessary
* keep mock data easy to replace
* do not tightly couple UI structure to temporary backend response formats

---

# 24. Mock Data

Mock data is allowed during frontend development.

Place mock data in a clearly identifiable location.

Example:

```text
src/mock/
```

Do not mix mock data with production data access logic.

Mock data should use the same TypeScript interfaces expected from production APIs.

---

# 25. Data Formatting

Centralize formatting for:

```text
coordinates
dates
UTC timestamps
speed
distance
heading
percentage
tonnage
IMO
MMSI
```

Do not manually duplicate formatting logic across components.

---

# 26. Maritime Units

Use domain-appropriate units.

Examples:

```text
Speed       kn

Distance    NM

Heading     °

Latitude    decimal degrees

Longitude   decimal degrees
```

Time-sensitive maritime data should clearly state timezone where ambiguity is possible.

Prefer UTC for AIS and voyage timestamps unless the UI explicitly presents local time.

---

# 27. Accessibility

Interactive controls must:

* have visible hover states
* have visible focus states
* be keyboard accessible where practical
* have sufficient contrast
* not rely only on color

Icons without adjacent labels must have accessible names.

---

# 28. Performance

Avoid unnecessary rerenders.

For large vessel collections:

* avoid rendering unnecessarily complex markers
* support future clustering
* avoid excessive map recalculation
* memoize expensive transformations when useful

Do not optimize prematurely, but do not introduce obvious performance problems.

---

# 29. Code Quality

Before completing a coding task:

run:

```bash
npm run lint
```

If available, also run:

```bash
npm run build
```

Do not claim completion if linting fails.

Do not hide warnings without understanding them.

---

# 30. Change Discipline

For each task:

1. inspect existing implementation
2. identify the smallest coherent change
3. implement
4. run lint
5. run relevant tests if available
6. summarize files changed
7. mention remaining limitations

Avoid unrelated refactors.

Do not rewrite working modules simply for stylistic preference.

---

# 31. Safety Before Destructive Changes

Do not automatically:

```text
delete major folders
rewrite configuration
replace package.json
reset Git
change environment files
delete API clients
remove dependencies
```

without explicitly explaining the reason.

---

# 32. Environment Variables

Never hard-code:

```text
Supabase service keys
API secrets
tokens
credentials
private endpoints
```

Use environment variables.

Do not expose server-side secrets through variables prefixed with:

```text
NEXT_PUBLIC_
```

Only values safe for browser exposure may use `NEXT_PUBLIC_`.

---

# 33. Supabase

When using Supabase from the frontend:

* assume browser-facing code operates with restricted permissions
* never place service-role credentials in frontend code
* respect Row Level Security
* use typed query helpers where practical

Sensitive database operations should remain on a trusted backend.

---

# 34. First Development Priority

Initial frontend development should prioritize architecture and visual foundation before advanced backend integration.

Recommended sequence:

```text
1. Application shell

2. Sidebar

3. Top toolbar

4. Vessel Tracking workspace

5. Dark maritime map

6. Vessel list

7. Vessel detail panel

8. Historical track

9. Predicted route

10. Route evaluation

11. Risk layers

12. Alerts and analytics
```

---

# 35. Initial Vessel Tracking Layout

The initial target layout should follow this conceptual structure:

```text
┌──────────────────────────────────────────────────────────────┐
│ Context / Search / Filters                                  │
├─────────────┬────────────────────────────────────────────────┤
│             │                                                │
│ Sidebar     │                Vessel Map                      │
│             │                                                │
│             │                                                │
│             │                               ┌──────────────┐ │
│             │                               │ Vessel Info  │ │
│             │                               │              │ │
│             │                               │ Risk         │ │
│             │                               │ Voyage       │ │
│             │                               └──────────────┘ │
├─────────────┴────────────────────────────────────────────────┤
│ Optional timeline / AIS playback / route controls           │
└──────────────────────────────────────────────────────────────┘
```

The map should remain visually dominant.

---

# 36. Design Decision Priority

When requirements conflict, prioritize in this order:

```text
1. data accuracy

2. operational clarity

3. information hierarchy

4. usability

5. consistency

6. visual aesthetics

7. decorative effects
```

---

# 37. AI Agent Behavior

When implementing a request:

Do not immediately code if the requirement materially changes architecture.

First explain:

```text
what will change
which files will change
whether dependencies are required
whether API assumptions are being made
```

For normal small UI changes, proceed without unnecessary discussion.

Do not invent backend APIs.

If an API is unavailable, clearly use mock data or an adapter and label it accordingly.

---

# 38. Definition of Done

A frontend task is complete only when:

* requested functionality is implemented
* UI follows the design system
* TypeScript has no introduced type errors
* lint passes
* no unrelated backend files were modified
* newly added dependencies are justified
* loading and empty states are handled where applicable
* important errors are handled
* changed files are summarized
