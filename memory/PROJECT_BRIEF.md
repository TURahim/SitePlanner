# Pacifico Site Layouts - Project Brief

## Overview
AI-powered geospatial layout tool for DG/microgrid/data center site planning. Generates terrain-aware asset placement and road routing for solar installations.

## Tech Stack
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL/PostGIS
- **Frontend**: React + TypeScript + Vite + MapLibre GL
- **Infrastructure**: AWS (ECS, RDS, S3, CloudFront, SQS)
- **Terrain Data**: USGS 3DEP elevation data

## Key Features
- KML/KMZ site boundary upload
- Terrain-aware layout generation (slope, aspect, curvature analysis)
- Multiple layout strategies (Balanced, Density, Low Earthwork, Clustered)
- Exclusion zone management
- Cut/fill earthwork estimation
- Export to KMZ/PDF

## Current Phase
Phase E: Layout Algorithm Enhancements
- Composite suitability scoring
- Poisson-disk sampling for asset placement
- MST-based road network optimization
- Road corridor earthwork calculation
