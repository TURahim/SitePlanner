# Frontend Map

- Entry: `frontend/src/main.tsx` mounts `App` wrapped with routing/auth contexts; styles via `index.css`.
- Pages: `pages/LandingPage`, `LoginPage`, `SignupPage`, `ProjectsPage`, `SiteDetailPage`; landing handles marketing, auth pages hook into Cognito/Amplify config, projects list user projects, site detail hosts map + panels.
- Components: `components/Layout.tsx` renders map + control panels; `LayoutVariants` toggles variant cards; `ExclusionZonePanel` handles drawing/removal; `AssetIcons` centralizes icon mapping.
- Contexts/Hooks: `AuthContext` manages Amplify session; `useLayoutPolling` polls backend for long-running layout jobs.
- Map utilities: `lib/mapUtils.ts` sets up MapLibre layers (slope heatmap, contours, buildable zones) fed by backend raster/vector tiles; assets pulled from API and rendered as sprites.

