PRD — Learned Suitability Scoring (Shallow ML Model)
Add AI-Based Buildability Heatmaps to Improve Site Layout Generation
1. Objective

Add a lightweight machine learning module that predicts site buildability (“suitability”) for each pixel/cell of a project site.
The suitability score will be integrated directly into the existing layout generator to improve placement decisions for assets (solar arrays, batteries, generators, inverters, substations, turbines).

This feature:

Does not require any historical Pacifico data

Uses synthetically labeled data derived from engineering rule-based constraints

Produces a probability heatmap (0–1) representing how suitable each location is for asset placement

Runs fast (seconds) and works with the existing terrain pipeline

2. Why We Are Building This

The MVP generator currently relies on:

slope thresholds

exclusion zones

Poisson disk sampling

grid-based placement

These rules work but are binary and rigid.
Suitability scoring adds a continuous intelligence layer that:

smooths out decision boundaries

captures interactions (e.g., “slope ok but too far from road”)

improves asset clustering

reduces bad placements

increases usable area detection

This aligns with PRD goals to enhance layout quality using AI
.

3. Feature Summary
The system will:

Generate synthetic labels (“good” vs “bad” buildable area) using existing rules.

Train a shallow ML model (XGBoost or RandomForest).

Produce a suitability score (0–1) for each spatial cell of the site.

Output a raster/array representing buildability.

Integrate the score into:

Poisson disk sampling weighting

Grid-based array placement

Filtering out low-suitability zones

4. Functional Requirements
4.1 Data Inputs

This feature must consume existing pipeline outputs:

slope per pixel

elevation

aspect

distance_to_road

distance_to_boundary

land_cover_class

All data is already present in terrain preprocessing.

4.2 Synthetic Label Generator

Create a labeling module that assigns:

1 → “good buildable area”

0 → “bad buildable area”

Using rules such as:

slope > 15% → bad

landcover ∈ {water, wetlands, dense forest} → bad

distance_to_boundary < setback buffer → bad

dist_to_road > threshold → bad

everything else → good

This dataset trains the model.

4.3 ML Model

Use XGBoost (preferred) or RandomForest

Train on synthetic labels

Save model to disk (ml_models/suitability_model.pkl)

Latency target: <200 ms for 100k cells

Provide method:

predict_proba(features) -> suitability score

4.4 Output

The system must produce:

2D raster matrix (numpy array) representing suitability probability

Geo-referenced (aligned with DEM)

Range: 0–1

4.5 Integration with Layout Generator
Poisson Disk Sampling

Modify sampler to weight candidate points by suitability score

Higher score → increased sampling probability

Lower score → reduced sampling probability or excluded entirely

Grid Placement

Skip cells below a suitability threshold (configurable, default 0.5)

Visualization

Add optional overlay in map viewer:

blue → low suitability

yellow → medium

red → high

5. Non-Functional Requirements
Performance

Model must predict suitability raster within < 1 second for sites up to 10–20 hectares.

Training time is irrelevant (offline).

Scalability

Must work with any DEM resolution (1m, 3m, 10m).

Must operate per-site without global training.

Maintainability

Model code must be modular:

/ml/feature_engineering.py

/ml/train_suitability_model.py

/ml/suitability_predictor.py

Security

All processing is local to backend; no external API calls.

6. Technical Design
6.1 Folder Structure
/backend
  /ml
    feature_engineering.py
    train_suitability_model.py
    suitability_predictor.py
    models/
      suitability_model.pkl
  layout/
    terrain_preprocessing.py
    poisson_sampler.py
    grid_placer.py
    suitability_integration.py

6.2 Pipeline Overview

Step 1 — Feature Extraction
From terrain/raster outputs → vector per pixel.

Step 2 — Synthetic Labeling
Apply rule-based heuristics → labels.

Step 3 — Train ML Model
XGBoost fits the decision surface.

Step 4 — Predict Suitability Heatmap
Return pixel-level probability.

Step 5 — Feed into Layout Generator
Use suitability to:

bias sampling

mask placement zones

improve overall layout quality

7. Edge Cases

Sites with extremely flat terrain (slope ≈ 0) → ensure model doesn’t predict 1 everywhere; use additional features (landcover, distance).

Missing landcover classes → default to neutral class.

Zero roads detected → fallback to distance-to-boundary and slope features.

High-res DEMs (1m LiDAR scale) → ensure feature computation is vectorized (NumPy/Dask).

8. Configuration Options
config/suitability.yml
training:
  slope_bad_threshold: 0.15
  boundary_buffer: 10
  max_distance_to_road: 400

prediction:
  min_score_for_placement: 0.5
  weighting_power: 1.5   # exponent shaping sampling probability

model:
  type: xgboost
  max_depth: 4
  n_estimators: 120
  learning_rate: 0.1

9. Acceptance Criteria
Model Training

 Model trains successfully using synthetic labels

 Stored model is loadable and predicts within 200 ms

Prediction / Output

 Suitability heatmap generated for any site

 Heatmap values range 0–1

 Raster aligns with DEM grid

Integration

 Poisson sampler incorporates suitability weighting

 Grid placement filters cells below threshold

 Layout quality improves (visually and by active area utilization)

Validation

 Synthetic test sites show intuitive suitability gradients

 Planners can visualize suitability layer in the UI

10. Future Enhancements (Optional)

Swap synthetic labels with real Pacifico layouts when available

Add deep-learning terrain classifier

Use reinforcement learning for multi-objective layout optimization

Model cost functions (earthwork, trenching) directly