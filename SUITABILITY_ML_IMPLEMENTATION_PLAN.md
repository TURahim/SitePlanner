# ML-Based Suitability Scoring Implementation Plan

> **Feature:** Learned Suitability Scoring (Shallow ML Model)  
> **PRD:** `suitabilityscoreprd.md`  
> **Target Completion:** 3-5 development days

---

## 1. Executive Summary

This document outlines the implementation plan for adding a lightweight machine learning module that predicts site buildability ("suitability") for each pixel/cell of a project site. The ML model will be trained on synthetic labels derived from existing engineering rules and will produce a 0–1 probability heatmap representing placement suitability.

### Key Goals
- **No historical data required** — Uses synthetically labeled data
- **Fast inference** — <200ms for 100k cells
- **Seamless integration** — Works with existing terrain pipeline
- **Improved layout quality** — Captures multi-factor interactions

---

## 2. Current State Analysis

### 2.1 Existing Suitability Scoring
The current system already has rule-based suitability scoring in `terrain_analysis_service.py`:

```python
# Current approach (lines 374-479)
def compute_suitability_score(
    self,
    metrics: TerrainMetrics,
    boundary_mask: np.ndarray,
    config: Optional[SuitabilityConfig] = None,
    asset_type: str = "solar_array",
) -> np.ndarray:
    """
    Weighted linear combination:
    - slope_weight: 0.65
    - aspect_weight: 0.10
    - curvature_weight: 0.15
    - roughness_weight: 0.10
    """
```

**Limitations of Current Approach:**
1. Binary thresholds (slope > limit → unsuitable)
2. Linear weighted combination doesn't capture interactions
3. No consideration of distance-to-road or boundary setbacks
4. Equal treatment of boundary conditions

### 2.2 Layout Generator Integration Points
The `terrain_layout_generator.py` already accepts `suitability_scores` parameter:

```python
def generate(
    self,
    ...
    suitability_scores: Optional[dict[str, np.ndarray]] = None,
    ...
)
```

And uses Poisson-disk sampling with multi-factor scoring (lines 700-800):
- `_position_scoring()` - Combines slope, proximity, suitability
- `_select_candidates_poisson()` - Weighted sampling

---

## 3. Architecture Design

### 3.1 New Directory Structure

```
pacifico-site-layouts/backend/
├── app/
│   ├── ml/                                    # NEW: ML module
│   │   ├── __init__.py
│   │   ├── feature_engineering.py             # Feature extraction from terrain
│   │   ├── synthetic_labeler.py               # Rule-based label generation
│   │   ├── suitability_model.py               # Model training and inference
│   │   ├── suitability_predictor.py           # High-level prediction service
│   │   └── models/                            # Persisted model files
│   │       └── .gitkeep
│   ├── services/
│   │   ├── terrain_analysis_service.py        # MODIFY: Add ML suitability method
│   │   └── terrain_layout_generator.py        # MODIFY: Integration hooks
│   └── api/
│       └── terrain.py                         # MODIFY: New endpoint for ML heatmap
├── config/
│   └── suitability.yml                        # NEW: ML configuration
└── tests/
    └── test_ml_suitability.py                 # NEW: Unit tests
```

### 3.2 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ML SUITABILITY PIPELINE                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐     │
│  │   Terrain    │───▶│     Feature      │───▶│    Synthetic     │     │
│  │  Analysis    │    │   Engineering    │    │     Labeler      │     │
│  │  Service     │    │                  │    │   (Training)     │     │
│  └──────────────┘    └──────────────────┘    └────────┬─────────┘     │
│        │                     │                        │               │
│        │                     │                        ▼               │
│        │                     │              ┌──────────────────┐     │
│        │                     │              │   XGBoost/RF     │     │
│        │                     │              │   Model Train    │     │
│        │                     │              └────────┬─────────┘     │
│        │                     │                        │               │
│        │                     ▼                        ▼               │
│        │            ┌──────────────────┐    ┌──────────────────┐     │
│        │            │  Feature Vector  │───▶│    Suitability   │     │
│        │            │   (Per Pixel)    │    │    Predictor     │     │
│        │            └──────────────────┘    └────────┬─────────┘     │
│        │                                             │               │
│        │                                             ▼               │
│        │                                    ┌──────────────────┐     │
│        └───────────────────────────────────▶│   Layout Gen     │     │
│                                             │   Integration    │     │
│                                             └──────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Tasks

### Phase 1: Core ML Module (Day 1-2)

#### Task 1.1: Feature Engineering Module
**File:** `backend/app/ml/feature_engineering.py`

```python
"""
Feature extraction from terrain rasters for ML suitability model.

Extracts per-pixel features:
- slope (degrees)
- elevation (meters, normalized)
- aspect (sine/cosine encoded)
- distance_to_boundary (meters)
- distance_to_road (meters, if available)
- curvature (profile and plan)
- roughness index
- land_cover_class (categorical, encoded)
"""

@dataclass
class FeatureConfig:
    """Configuration for feature extraction."""
    include_elevation: bool = True
    include_slope: bool = True
    include_aspect: bool = True
    include_curvature: bool = True
    include_roughness: bool = True
    include_distance_to_boundary: bool = True
    include_distance_to_road: bool = True
    normalize_features: bool = True
    aspect_encoding: str = "sincos"  # "sincos" or "degrees"


class FeatureExtractor:
    """
    Extracts feature vectors from terrain rasters.
    
    All features are computed per-pixel and returned as a
    (H, W, num_features) array or (N, num_features) for flat output.
    """
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self._feature_names: list[str] = []
    
    def extract_features(
        self,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        boundary_mask: np.ndarray,
        transform: Affine,
        aspect_array: Optional[np.ndarray] = None,
        curvature_array: Optional[np.ndarray] = None,
        plan_curvature_array: Optional[np.ndarray] = None,
        roughness_array: Optional[np.ndarray] = None,
        road_geometry: Optional[LineString] = None,
    ) -> tuple[np.ndarray, list[str]]:
        """
        Extract feature array from terrain data.
        
        Returns:
            Tuple of (features array shape (H, W, F), feature names list)
        """
        pass
    
    def _compute_distance_to_boundary(
        self,
        boundary_mask: np.ndarray,
        cell_size_m: float,
    ) -> np.ndarray:
        """Compute Euclidean distance transform from boundary edges."""
        pass
    
    def _compute_distance_to_road(
        self,
        road_geometry: LineString,
        transform: Affine,
        shape: tuple[int, int],
    ) -> np.ndarray:
        """Compute distance to nearest road point per pixel."""
        pass
    
    def _encode_aspect(self, aspect_array: np.ndarray) -> np.ndarray:
        """Encode aspect as sine/cosine components (handles circular nature)."""
        pass
```

**Acceptance Criteria:**
- [ ] Extracts 8+ features per pixel
- [ ] Handles nodata/NaN values gracefully
- [ ] Distance transforms computed efficiently (<100ms for 500×500 grid)
- [ ] Aspect encoded as sine/cosine to handle circularity

---

#### Task 1.2: Synthetic Label Generator
**File:** `backend/app/ml/synthetic_labeler.py`

```python
"""
Generates synthetic training labels from engineering rules.

Labels:
- 1 = "good buildable area"
- 0 = "bad buildable area"

Rules (configurable):
- slope > 15% → bad
- landcover ∈ {water, wetlands, dense_forest} → bad
- distance_to_boundary < setback_buffer → bad
- distance_to_road > max_road_distance → bad
- everything else → good
"""

@dataclass
class LabelingRules:
    """Configurable rules for synthetic label generation."""
    # Slope thresholds (in degrees for consistency with terrain service)
    slope_bad_threshold_deg: float = 15.0
    slope_marginal_threshold_deg: float = 10.0
    
    # Boundary setback (meters)
    boundary_setback_m: float = 10.0
    
    # Road proximity (meters)
    max_road_distance_m: float = 500.0
    road_distance_penalty_start_m: float = 200.0
    
    # Curvature thresholds
    max_curvature_magnitude: float = 0.2
    
    # Roughness threshold
    max_roughness: float = 5.0
    
    # Land cover classes that are unbuildable
    unbuildable_landcover: set[str] = field(
        default_factory=lambda: {"water", "wetland", "dense_forest", "rock"}
    )


class SyntheticLabeler:
    """
    Generates binary labels (0/1) and soft labels (0-1) from features.
    
    Supports two labeling modes:
    - Binary: Hard 0/1 labels for classification
    - Soft: Continuous 0-1 scores for regression targets
    """
    
    def __init__(self, rules: Optional[LabelingRules] = None):
        self.rules = rules or LabelingRules()
    
    def generate_binary_labels(
        self,
        features: np.ndarray,
        feature_names: list[str],
        boundary_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Generate hard 0/1 labels using rule-based heuristics.
        
        Returns:
            Binary label array (H, W) or (N,) depending on input shape
        """
        pass
    
    def generate_soft_labels(
        self,
        features: np.ndarray,
        feature_names: list[str],
        boundary_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Generate soft 0-1 labels capturing gradients near thresholds.
        
        Uses sigmoid transitions instead of hard cutoffs for smoother
        learning targets.
        """
        pass
    
    def _apply_slope_rule(self, slope: np.ndarray) -> np.ndarray:
        """Returns 1 where slope is acceptable, 0 where too steep."""
        pass
    
    def _apply_boundary_rule(self, dist_to_boundary: np.ndarray) -> np.ndarray:
        """Returns 1 where far enough from boundary, 0 in setback zone."""
        pass
    
    def _apply_road_rule(self, dist_to_road: np.ndarray) -> np.ndarray:
        """Returns 1 where close enough to road, penalty when far."""
        pass
```

**Acceptance Criteria:**
- [ ] Generates labels matching existing rule behavior
- [ ] Soft labels provide smoother gradients than hard cutoffs
- [ ] All rules are configurable via `LabelingRules`
- [ ] Labels 100k+ cells in <50ms

---

#### Task 1.3: ML Model Training & Inference
**File:** `backend/app/ml/suitability_model.py`

```python
"""
XGBoost-based suitability prediction model.

Supports:
- Training on synthetic labels
- Fast batch prediction
- Model persistence (pickle)
- Feature importance analysis
"""

from dataclasses import dataclass
import xgboost as xgb
import numpy as np
from pathlib import Path
import pickle
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """XGBoost model hyperparameters."""
    model_type: str = "xgboost"  # "xgboost" or "random_forest"
    max_depth: int = 4
    n_estimators: int = 120
    learning_rate: float = 0.1
    min_child_weight: int = 5
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    random_state: int = 42
    n_jobs: int = -1


class SuitabilityModel:
    """
    Machine learning model for suitability prediction.
    
    Wraps XGBoost (or RandomForest) with methods for:
    - Training on (features, labels) pairs
    - Predicting suitability probabilities
    - Model serialization
    """
    
    MODEL_DIR = Path(__file__).parent / "models"
    DEFAULT_MODEL_NAME = "suitability_model.pkl"
    
    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self._model: Optional[xgb.XGBClassifier] = None
        self._feature_names: list[str] = []
        self._is_fitted = False
    
    def train(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        feature_names: list[str],
        validation_split: float = 0.2,
    ) -> dict[str, float]:
        """
        Train the suitability model.
        
        Args:
            features: Feature array (N, num_features)
            labels: Binary labels (N,)
            feature_names: List of feature names
            validation_split: Fraction for validation
            
        Returns:
            Dictionary of training metrics (accuracy, AUC, etc.)
        """
        pass
    
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """
        Predict suitability probability for each sample.
        
        Args:
            features: Feature array (N, num_features) or (H, W, num_features)
            
        Returns:
            Probability array (N,) or (H, W) with values in [0, 1]
        """
        pass
    
    def predict_raster(
        self,
        features: np.ndarray,
        boundary_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Predict suitability for entire raster, returning 2D probability map.
        
        Masks out-of-boundary areas with 0.
        """
        pass
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Save model to disk."""
        pass
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "SuitabilityModel":
        """Load model from disk."""
        pass
    
    def get_feature_importance(self) -> dict[str, float]:
        """Return feature importance scores."""
        pass
```

**Acceptance Criteria:**
- [ ] XGBoost classifier trains successfully on synthetic data
- [ ] Prediction latency <200ms for 100k cells
- [ ] Model persists to/from disk correctly
- [ ] Feature importance is extractable for debugging

---

#### Task 1.4: High-Level Predictor Service
**File:** `backend/app/ml/suitability_predictor.py`

```python
"""
High-level service orchestrating ML suitability prediction.

Provides a simple interface for the layout generator to request
suitability scores without managing feature extraction or model loading.
"""

from typing import Optional
import numpy as np
from rasterio.transform import Affine
from shapely.geometry import Polygon, LineString

from app.ml.feature_engineering import FeatureExtractor, FeatureConfig
from app.ml.suitability_model import SuitabilityModel, ModelConfig
from app.services.terrain_analysis_service import TerrainMetrics


class MLSuitabilityPredictor:
    """
    Service for ML-based suitability prediction.
    
    Encapsulates:
    - Feature extraction
    - Model loading (lazy)
    - Batch prediction
    - Caching (optional)
    """
    
    _instance: Optional["MLSuitabilityPredictor"] = None
    
    def __init__(
        self,
        feature_config: Optional[FeatureConfig] = None,
        model_config: Optional[ModelConfig] = None,
        model_path: Optional[str] = None,
    ):
        self.feature_extractor = FeatureExtractor(feature_config)
        self._model: Optional[SuitabilityModel] = None
        self._model_path = model_path
        self._model_config = model_config
    
    @classmethod
    def get_instance(cls) -> "MLSuitabilityPredictor":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def predict_suitability(
        self,
        dem_array: np.ndarray,
        slope_array: np.ndarray,
        boundary_mask: np.ndarray,
        transform: Affine,
        terrain_metrics: Optional[TerrainMetrics] = None,
        road_geometry: Optional[LineString] = None,
        asset_type: str = "solar_array",
    ) -> np.ndarray:
        """
        Predict suitability scores for the given terrain.
        
        Args:
            dem_array: Elevation data
            slope_array: Slope in degrees
            boundary_mask: Boolean mask of valid area
            transform: Rasterio affine transform
            terrain_metrics: Optional pre-computed terrain metrics
            road_geometry: Optional road network for distance features
            asset_type: Asset type for asset-specific models (future)
            
        Returns:
            Suitability score array (H, W) with values in [0, 1]
        """
        pass
    
    def _ensure_model_loaded(self) -> None:
        """Lazy load the trained model."""
        pass
    
    def is_model_available(self) -> bool:
        """Check if a trained model exists."""
        pass


# Convenience function
def get_ml_suitability_predictor() -> MLSuitabilityPredictor:
    """Get the global ML suitability predictor instance."""
    return MLSuitabilityPredictor.get_instance()
```

**Acceptance Criteria:**
- [ ] Lazy model loading (no startup penalty if not used)
- [ ] Graceful fallback if model not trained
- [ ] Thread-safe singleton access
- [ ] Handles all terrain metric inputs

---

### Phase 2: Integration with Layout Generator (Day 2-3)

#### Task 2.1: Modify Terrain Analysis Service
**File:** `backend/app/services/terrain_analysis_service.py`

**Changes:**
1. Add method to compute ML-based suitability:

```python
def compute_ml_suitability_score(
    self,
    metrics: TerrainMetrics,
    boundary_mask: np.ndarray,
    asset_type: str = "solar_array",
    use_fallback: bool = True,
) -> np.ndarray:
    """
    Compute suitability using ML model (if available) or rule-based fallback.
    
    Args:
        metrics: Pre-computed terrain metrics
        boundary_mask: Boolean mask of valid area
        asset_type: Asset type for scoring
        use_fallback: If True, use rule-based scoring when ML unavailable
        
    Returns:
        Suitability score array (0-1)
    """
    from app.ml.suitability_predictor import get_ml_suitability_predictor
    
    predictor = get_ml_suitability_predictor()
    
    if predictor.is_model_available():
        return predictor.predict_suitability(
            dem_array=...,
            slope_array=metrics.slope_deg,
            boundary_mask=boundary_mask,
            transform=metrics.transform,
            terrain_metrics=metrics,
            asset_type=asset_type,
        )
    elif use_fallback:
        logger.warning("ML model not available, using rule-based suitability")
        return self.compute_suitability_score(metrics, boundary_mask, asset_type=asset_type)
    else:
        raise RuntimeError("ML suitability model not available")
```

**Acceptance Criteria:**
- [ ] New method returns same shape as existing `compute_suitability_score`
- [ ] Graceful fallback to rule-based scoring
- [ ] Logging when fallback is used

---

#### Task 2.2: Modify Poisson Disk Sampling
**File:** `backend/app/services/terrain_layout_generator.py`

**Changes to `_select_candidates_poisson()` method:**

```python
def _select_candidates_poisson(
    self,
    buildable_mask: np.ndarray,
    suitability_array: np.ndarray,  # NEW: ML suitability scores
    num_candidates: int,
    min_spacing_cells: int,
    transform: Affine,
    existing_positions: list[Point] = None,
) -> list[tuple[int, int, float]]:
    """
    Select candidate positions using Poisson-disk sampling weighted by suitability.
    
    MODIFICATION: Weight sampling probability by suitability score.
    
    Higher suitability → higher probability of being selected.
    """
    # Build probability distribution from suitability
    probs = suitability_array.copy()
    probs[~buildable_mask] = 0
    
    # Apply weighting power (from config)
    weighting_power = self._get_suitability_weighting_power()
    probs = np.power(probs, weighting_power)
    
    # Normalize to probability distribution
    probs = probs / probs.sum()
    
    # Sample positions weighted by probability
    # ... (use np.random.choice with weights)
```

**Acceptance Criteria:**
- [ ] Candidates weighted by suitability score
- [ ] Weighting power is configurable
- [ ] Maintains minimum spacing constraints
- [ ] Falls back to uniform sampling if all suitabilities equal

---

#### Task 2.3: Modify Grid-Based Placement
**File:** `backend/app/services/terrain_layout_generator.py`

**Changes to grid placement filtering:**

```python
def _place_assets_grid(
    self,
    ...
    suitability_array: np.ndarray,
    min_suitability_threshold: float = 0.5,  # NEW parameter
) -> list[PlacedAsset]:
    """
    Place assets in a grid pattern, filtering cells below suitability threshold.
    """
    # Filter grid cells by suitability
    valid_cells = buildable_mask & (suitability_array >= min_suitability_threshold)
    
    # Rest of grid placement logic...
```

**Acceptance Criteria:**
- [ ] Grid cells filtered by suitability threshold
- [ ] Threshold is configurable (default 0.5)
- [ ] No assets placed on cells below threshold

---

### Phase 3: Configuration & Training Pipeline (Day 3)

#### Task 3.1: Configuration File
**File:** `backend/config/suitability.yml`

```yaml
# ML Suitability Scoring Configuration
# =====================================

training:
  # Synthetic label rules
  slope_bad_threshold_deg: 15.0
  slope_marginal_threshold_deg: 10.0
  boundary_setback_m: 10.0
  max_road_distance_m: 500.0
  max_curvature: 0.2
  max_roughness: 5.0
  
  # Training data generation
  samples_per_site: 50000  # Subsample large rasters
  validation_split: 0.2

prediction:
  # Placement thresholds
  min_score_for_placement: 0.5
  weighting_power: 1.5  # Exponent for sampling probability
  
  # Fallback behavior
  use_rule_based_fallback: true

model:
  type: xgboost
  max_depth: 4
  n_estimators: 120
  learning_rate: 0.1
  min_child_weight: 5
  subsample: 0.8
  colsample_bytree: 0.8
  random_state: 42

features:
  include_elevation: true
  include_slope: true
  include_aspect: true
  include_curvature: true
  include_roughness: true
  include_distance_to_boundary: true
  include_distance_to_road: true
  normalize_features: true
  aspect_encoding: sincos
```

#### Task 3.2: Training CLI Script
**File:** `backend/scripts/train_suitability_model.py`

```python
#!/usr/bin/env python
"""
CLI script to train the suitability model.

Usage:
    python scripts/train_suitability_model.py --config config/suitability.yml
    python scripts/train_suitability_model.py --sites site1.kml site2.kml
    python scripts/train_suitability_model.py --synthetic --num-samples 100000
"""

import argparse
import yaml
from pathlib import Path

from app.ml.feature_engineering import FeatureExtractor
from app.ml.synthetic_labeler import SyntheticLabeler
from app.ml.suitability_model import SuitabilityModel


def main():
    parser = argparse.ArgumentParser(description="Train suitability model")
    parser.add_argument("--config", type=Path, default="config/suitability.yml")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic terrain")
    parser.add_argument("--num-samples", type=int, default=100000)
    parser.add_argument("--output", type=Path, help="Output model path")
    args = parser.parse_args()
    
    # Load config
    with open(args.config) as f:
        config = yaml.safe_load(f)
    
    # Generate training data
    if args.synthetic:
        features, labels, feature_names = generate_synthetic_training_data(
            num_samples=args.num_samples,
            config=config,
        )
    else:
        # Load from real sites (future enhancement)
        raise NotImplementedError("Real site training not yet implemented")
    
    # Train model
    model = SuitabilityModel()
    metrics = model.train(features, labels, feature_names)
    
    print(f"Training complete: {metrics}")
    
    # Save model
    output_path = args.output or SuitabilityModel.MODEL_DIR / SuitabilityModel.DEFAULT_MODEL_NAME
    model.save(output_path)
    print(f"Model saved to: {output_path}")


def generate_synthetic_training_data(num_samples: int, config: dict):
    """Generate synthetic terrain and labels for training."""
    # Create diverse synthetic terrains
    # ... (implement terrain generation)
    pass


if __name__ == "__main__":
    main()
```

**Acceptance Criteria:**
- [ ] Config file parsed correctly
- [ ] Synthetic data generation works
- [ ] Model trains and saves
- [ ] Training metrics reported

---

### Phase 4: API & Visualization (Day 4)

#### Task 4.1: Add ML Suitability Heatmap Endpoint
**File:** `backend/app/api/terrain.py`

```python
@router.get(
    "/{site_id}/terrain/ml-suitability",
    response_model=MLSuitabilityResponse,
    summary="Get ML-based suitability heatmap",
    description="Returns ML-predicted suitability scores as a raster or polygonized zones.",
)
async def get_ml_suitability(
    site_id: UUID,
    output_format: str = Query(
        default="zones",
        description="Output format: 'zones' (polygons) or 'grid' (point grid)",
    ),
    asset_type: str = Query(
        default="solar_array",
        description="Asset type for suitability scoring",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MLSuitabilityResponse:
    """
    Generate ML-based suitability heatmap.
    
    Returns colored zones representing suitability:
    - Red (0-0.3): Low suitability
    - Yellow (0.3-0.6): Medium suitability
    - Green (0.6-1.0): High suitability
    
    Includes feature importance breakdown.
    """
    pass
```

**Response Schema:**
```python
class MLSuitabilityResponse(BaseModel):
    """ML suitability heatmap response."""
    zones: dict  # GeoJSON FeatureCollection
    legend: list[dict]  # Color legend
    statistics: dict  # Mean, min, max, distribution
    feature_importance: dict[str, float]  # Feature weights
    model_version: str
    using_fallback: bool  # True if rule-based fallback used
```

#### Task 4.2: Frontend Suitability Layer
**File:** `frontend/src/pages/SiteDetailPage.tsx`

**Changes:**
1. Add "ML Suitability" option to terrain layer selector
2. Fetch from new endpoint
3. Render as colored polygons with opacity

```typescript
// Add to terrain layer options
const TERRAIN_LAYERS: TerrainLayerOption[] = [
  // ... existing layers
  { id: 'ml-suitability', label: 'ML Suitability', icon: '🤖' },
];

// Add fetch function
const fetchMLSuitability = async (siteId: string, assetType: string) => {
  const response = await api.get(`/api/sites/${siteId}/terrain/ml-suitability`, {
    params: { asset_type: assetType, output_format: 'zones' },
  });
  return response.data;
};

// Add GeoJSON layer with suitability coloring
const getMLSuitabilityStyle = (score: number) => ({
  fillColor: score > 0.6 ? '#22c55e' : score > 0.3 ? '#eab308' : '#ef4444',
  fillOpacity: 0.5,
  stroke: false,
});
```

**Acceptance Criteria:**
- [ ] New terrain layer option visible in UI
- [ ] Suitability zones render with correct colors
- [ ] Legend shows color mapping
- [ ] Loading/error states handled

---

### Phase 5: Unit Tests (Day 4-5)

#### Task 5.1: Feature Engineering Tests
**File:** `backend/tests/test_ml_feature_engineering.py`

```python
"""Unit tests for ML feature engineering module."""

import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import box

from app.ml.feature_engineering import FeatureExtractor, FeatureConfig


class TestFeatureExtractor:
    """Tests for FeatureExtractor class."""
    
    @pytest.fixture
    def extractor(self):
        return FeatureExtractor()
    
    @pytest.fixture
    def sample_terrain(self):
        """Create sample terrain data."""
        shape = (100, 100)
        dem = np.random.uniform(100, 200, shape)
        slope = np.random.uniform(0, 20, shape)
        boundary_mask = np.ones(shape, dtype=bool)
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        return dem, slope, boundary_mask, transform
    
    def test_extract_features_shape(self, extractor, sample_terrain):
        """Test that feature extraction produces correct shape."""
        dem, slope, mask, transform = sample_terrain
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
        )
        
        assert features.shape[0] == 100  # Height
        assert features.shape[1] == 100  # Width
        assert features.shape[2] == len(names)  # Features
        assert len(names) >= 4  # At least slope, elevation, boundary dist
    
    def test_extract_features_includes_slope(self, extractor, sample_terrain):
        """Test that slope is included in features."""
        dem, slope, mask, transform = sample_terrain
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
        )
        
        assert "slope" in names
        slope_idx = names.index("slope")
        np.testing.assert_array_almost_equal(
            features[:, :, slope_idx][mask],
            slope[mask],
            decimal=5,
        )
    
    def test_distance_to_boundary_computed(self, extractor, sample_terrain):
        """Test that distance to boundary is computed correctly."""
        dem, slope, mask, transform = sample_terrain
        
        # Create mask with interior region
        mask = np.zeros((100, 100), dtype=bool)
        mask[10:90, 10:90] = True
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
        )
        
        assert "distance_to_boundary" in names
        dist_idx = names.index("distance_to_boundary")
        
        # Center should have higher distance than edges
        center_dist = features[50, 50, dist_idx]
        edge_dist = features[10, 50, dist_idx]
        assert center_dist > edge_dist
    
    def test_aspect_encoding_sincos(self, extractor, sample_terrain):
        """Test that aspect is encoded as sin/cos components."""
        dem, slope, mask, transform = sample_terrain
        aspect = np.random.uniform(0, 360, (100, 100))
        
        config = FeatureConfig(aspect_encoding="sincos")
        extractor = FeatureExtractor(config)
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
            aspect_array=aspect,
        )
        
        assert "aspect_sin" in names
        assert "aspect_cos" in names
    
    def test_handles_nodata_values(self, extractor, sample_terrain):
        """Test that nodata values are handled gracefully."""
        dem, slope, mask, transform = sample_terrain
        
        # Add nodata values
        dem[20:30, 20:30] = -9999
        slope[20:30, 20:30] = -9999
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
        )
        
        # Should not have NaN or inf in output
        assert not np.any(np.isnan(features[mask]))
        assert not np.any(np.isinf(features[mask]))
    
    def test_normalization_applied(self):
        """Test that features are normalized when configured."""
        config = FeatureConfig(normalize_features=True)
        extractor = FeatureExtractor(config)
        
        dem = np.random.uniform(100, 200, (100, 100))
        slope = np.random.uniform(0, 20, (100, 100))
        mask = np.ones((100, 100), dtype=bool)
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        
        features, names = extractor.extract_features(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=mask,
            transform=transform,
        )
        
        # Normalized features should be in reasonable range
        for i, name in enumerate(names):
            feat = features[:, :, i][mask]
            assert feat.max() <= 10, f"Feature {name} not normalized: max={feat.max()}"
            assert feat.min() >= -10, f"Feature {name} not normalized: min={feat.min()}"
```

#### Task 5.2: Synthetic Labeler Tests
**File:** `backend/tests/test_ml_synthetic_labeler.py`

```python
"""Unit tests for synthetic label generation."""

import numpy as np
import pytest

from app.ml.synthetic_labeler import SyntheticLabeler, LabelingRules


class TestSyntheticLabeler:
    """Tests for SyntheticLabeler class."""
    
    @pytest.fixture
    def labeler(self):
        return SyntheticLabeler()
    
    @pytest.fixture
    def sample_features(self):
        """Create sample feature array with known values."""
        # (100, 100, 4) array with slope, elevation, dist_boundary, dist_road
        features = np.zeros((100, 100, 4))
        feature_names = ["slope", "elevation", "distance_to_boundary", "distance_to_road"]
        
        # Set slope values
        features[:, :, 0] = 5.0  # Default 5 degrees
        features[80:, :, 0] = 20.0  # Steep zone
        
        # Set elevation
        features[:, :, 1] = 100.0
        
        # Set distance to boundary (center is far from boundary)
        features[:, :, 2] = 50.0  # 50m from boundary
        features[:5, :, 2] = 5.0  # Close to boundary
        
        # Set distance to road
        features[:, :, 3] = 100.0  # 100m from road
        features[:, :50, 3] = 600.0  # Far from road
        
        boundary_mask = np.ones((100, 100), dtype=bool)
        
        return features, feature_names, boundary_mask
    
    def test_steep_areas_labeled_bad(self, labeler, sample_features):
        """Test that steep areas (>15°) are labeled as bad (0)."""
        features, names, mask = sample_features
        
        labels = labeler.generate_binary_labels(features, names, mask)
        
        # Steep zone (rows 80+) should be labeled 0
        assert np.all(labels[80:, :] == 0), "Steep areas should be labeled bad"
    
    def test_boundary_setback_labeled_bad(self, labeler, sample_features):
        """Test that areas within boundary setback are labeled bad."""
        features, names, mask = sample_features
        
        # Configure strict setback
        rules = LabelingRules(boundary_setback_m=10.0)
        labeler = SyntheticLabeler(rules)
        
        labels = labeler.generate_binary_labels(features, names, mask)
        
        # Areas close to boundary (rows 0-5) should be labeled 0
        assert np.all(labels[:5, :] == 0), "Boundary setback should be labeled bad"
    
    def test_far_from_road_labeled_bad(self, labeler, sample_features):
        """Test that areas far from roads are labeled bad."""
        features, names, mask = sample_features
        
        rules = LabelingRules(max_road_distance_m=500.0)
        labeler = SyntheticLabeler(rules)
        
        labels = labeler.generate_binary_labels(features, names, mask)
        
        # Areas far from road (cols 0-50 with dist 600m) should be labeled 0
        assert np.all(labels[:, :50] == 0), "Areas far from road should be labeled bad"
    
    def test_good_areas_labeled_good(self, labeler, sample_features):
        """Test that areas meeting all criteria are labeled good."""
        features, names, mask = sample_features
        
        labels = labeler.generate_binary_labels(features, names, mask)
        
        # Central area with good slope, far from boundary, close to road
        # Rows 20-70, cols 60-90 should all be good
        good_zone = labels[20:70, 60:90]
        assert np.all(good_zone == 1), "Good areas should be labeled 1"
    
    def test_soft_labels_are_continuous(self, labeler, sample_features):
        """Test that soft labels produce continuous values."""
        features, names, mask = sample_features
        
        soft_labels = labeler.generate_soft_labels(features, names, mask)
        
        # Should have values between 0 and 1
        assert soft_labels.min() >= 0
        assert soft_labels.max() <= 1
        
        # Should have intermediate values (not just 0 and 1)
        unique_values = np.unique(soft_labels[mask])
        assert len(unique_values) > 10, "Soft labels should have many distinct values"
    
    def test_soft_labels_transition_smoothly(self, labeler, sample_features):
        """Test that soft labels transition smoothly at thresholds."""
        features, names, mask = sample_features
        
        # Create slope gradient
        features[:, :, 0] = np.linspace(0, 20, 100).reshape(-1, 1)
        
        soft_labels = labeler.generate_soft_labels(features, names, mask)
        
        # Labels should decrease as slope increases
        assert soft_labels[0, 50] > soft_labels[50, 50] > soft_labels[99, 50]
    
    def test_custom_rules_applied(self):
        """Test that custom labeling rules are applied."""
        rules = LabelingRules(
            slope_bad_threshold_deg=10.0,  # Stricter slope limit
            boundary_setback_m=20.0,
        )
        labeler = SyntheticLabeler(rules)
        
        features = np.zeros((100, 100, 4))
        features[:, :, 0] = 12.0  # 12 degrees slope
        features[:, :, 2] = 50.0  # 50m from boundary
        
        feature_names = ["slope", "elevation", "distance_to_boundary", "distance_to_road"]
        mask = np.ones((100, 100), dtype=bool)
        
        labels = labeler.generate_binary_labels(features, feature_names, mask)
        
        # 12° > 10° threshold, should be bad
        assert np.all(labels == 0), "Custom slope threshold should be applied"
```

#### Task 5.3: Suitability Model Tests
**File:** `backend/tests/test_ml_suitability_model.py`

```python
"""Unit tests for ML suitability model."""

import numpy as np
import pytest
from pathlib import Path
import tempfile

from app.ml.suitability_model import SuitabilityModel, ModelConfig


class TestSuitabilityModel:
    """Tests for SuitabilityModel class."""
    
    @pytest.fixture
    def model(self):
        return SuitabilityModel()
    
    @pytest.fixture
    def training_data(self):
        """Create synthetic training data."""
        np.random.seed(42)
        n_samples = 10000
        n_features = 6
        
        # Generate features
        features = np.random.randn(n_samples, n_features)
        
        # Generate labels based on feature combination
        # Good = low slope (feature 0) and far from boundary (feature 2)
        scores = -features[:, 0] + features[:, 2]  # Higher = better
        labels = (scores > 0).astype(int)
        
        feature_names = [
            "slope", "elevation", "distance_to_boundary",
            "distance_to_road", "aspect_sin", "aspect_cos"
        ]
        
        return features, labels, feature_names
    
    def test_model_trains_successfully(self, model, training_data):
        """Test that model trains without errors."""
        features, labels, names = training_data
        
        metrics = model.train(features, labels, names)
        
        assert "accuracy" in metrics
        assert "auc" in metrics
        assert metrics["accuracy"] > 0.5  # Better than random
    
    def test_model_predicts_probabilities(self, model, training_data):
        """Test that model predicts valid probabilities."""
        features, labels, names = training_data
        model.train(features, labels, names)
        
        # Predict on subset
        test_features = features[:100]
        probs = model.predict_proba(test_features)
        
        assert probs.shape == (100,)
        assert np.all(probs >= 0)
        assert np.all(probs <= 1)
    
    def test_model_predicts_raster(self, model, training_data):
        """Test that model predicts on 2D raster input."""
        features, labels, names = training_data
        
        # Reshape some features to raster format
        raster_features = features[:10000].reshape(100, 100, -1)
        raster_labels = labels[:10000].reshape(100, 100)
        
        # Train on flat data
        model.train(features, labels, names)
        
        # Predict on raster
        boundary_mask = np.ones((100, 100), dtype=bool)
        probs = model.predict_raster(raster_features, boundary_mask)
        
        assert probs.shape == (100, 100)
        assert np.all(probs >= 0)
        assert np.all(probs <= 1)
    
    def test_model_saves_and_loads(self, model, training_data):
        """Test model persistence."""
        features, labels, names = training_data
        model.train(features, labels, names)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "test_model.pkl"
            model.save(save_path)
            
            assert save_path.exists()
            
            # Load model
            loaded_model = SuitabilityModel.load(save_path)
            
            # Predictions should match
            test_features = features[:100]
            original_probs = model.predict_proba(test_features)
            loaded_probs = loaded_model.predict_proba(test_features)
            
            np.testing.assert_array_almost_equal(original_probs, loaded_probs)
    
    def test_feature_importance_available(self, model, training_data):
        """Test that feature importance is extractable."""
        features, labels, names = training_data
        model.train(features, labels, names)
        
        importance = model.get_feature_importance()
        
        assert len(importance) == len(names)
        assert all(name in importance for name in names)
        assert sum(importance.values()) > 0
    
    def test_prediction_latency(self, model, training_data):
        """Test that prediction is fast enough."""
        import time
        
        features, labels, names = training_data
        model.train(features, labels, names)
        
        # Test on 100k samples (PRD requirement)
        large_features = np.random.randn(100000, len(names))
        
        start = time.time()
        model.predict_proba(large_features)
        elapsed = time.time() - start
        
        assert elapsed < 0.2, f"Prediction took {elapsed:.3f}s, should be <200ms"
    
    def test_untrained_model_raises_error(self, model):
        """Test that untrained model raises appropriate error."""
        test_features = np.random.randn(100, 6)
        
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict_proba(test_features)


class TestModelConfig:
    """Tests for model configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ModelConfig()
        
        assert config.model_type == "xgboost"
        assert config.max_depth == 4
        assert config.n_estimators == 120
    
    def test_custom_config_applied(self):
        """Test that custom config is applied to model."""
        config = ModelConfig(max_depth=6, n_estimators=200)
        model = SuitabilityModel(config)
        
        # Train and verify config was applied
        features = np.random.randn(1000, 4)
        labels = np.random.randint(0, 2, 1000)
        names = ["f1", "f2", "f3", "f4"]
        
        model.train(features, labels, names)
        
        # XGBoost model should have config applied
        assert model._model.max_depth == 6
        assert model._model.n_estimators == 200
```

#### Task 5.4: Integration Tests
**File:** `backend/tests/test_ml_suitability_integration.py`

```python
"""Integration tests for ML suitability with layout generator."""

import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import box

from app.ml.suitability_predictor import MLSuitabilityPredictor
from app.services.terrain_layout_generator import TerrainAwareLayoutGenerator


class TestMLSuitabilityIntegration:
    """Tests for ML suitability integration with layout generator."""
    
    @pytest.fixture
    def predictor(self):
        """Create predictor with trained model."""
        predictor = MLSuitabilityPredictor()
        # Train a simple model for testing
        predictor._train_test_model()
        return predictor
    
    @pytest.fixture
    def terrain_data(self):
        """Create test terrain data."""
        shape = (100, 100)
        dem = np.ones(shape) * 100.0
        slope = np.ones(shape) * 5.0  # 5 degrees everywhere
        slope[80:, :] = 20.0  # Steep zone
        
        transform = Affine(0.00009, 0, -0.0045, 0, -0.00009, 0.0045)
        boundary = box(-0.0045, -0.0045, 0.0045, 0.0045)
        
        return dem, slope, transform, boundary
    
    def test_ml_suitability_used_in_placement(self, predictor, terrain_data):
        """Test that ML suitability influences asset placement."""
        dem, slope, transform, boundary = terrain_data
        
        # Get ML suitability scores
        boundary_mask = np.ones((100, 100), dtype=bool)
        ml_scores = predictor.predict_suitability(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=boundary_mask,
            transform=transform,
        )
        
        # Generate layout with ML suitability
        generator = TerrainAwareLayoutGenerator(target_capacity_kw=1000.0)
        assets, _, _ = generator.generate(
            boundary=boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
            suitability_scores={"default": ml_scores},
        )
        
        # Assets should be placed in high-suitability areas
        for asset in assets:
            # Get grid position
            row, col = asset.grid_row, asset.grid_col
            if 0 <= row < 100 and 0 <= col < 100:
                score = ml_scores[row, col]
                assert score > 0.3, f"Asset placed in low-suitability area: {score}"
    
    def test_fallback_when_model_unavailable(self, terrain_data):
        """Test graceful fallback to rule-based scoring."""
        dem, slope, transform, boundary = terrain_data
        
        # Create predictor without trained model
        predictor = MLSuitabilityPredictor()
        
        # Should still work (using fallback)
        boundary_mask = np.ones((100, 100), dtype=bool)
        scores = predictor.predict_suitability(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=boundary_mask,
            transform=transform,
        )
        
        assert scores.shape == (100, 100)
        assert np.all(scores >= 0)
        assert np.all(scores <= 1)
    
    def test_ml_improves_placement_quality(self, predictor, terrain_data):
        """Test that ML suitability improves placement vs no suitability."""
        dem, slope, transform, boundary = terrain_data
        boundary_mask = np.ones((100, 100), dtype=bool)
        
        # Layout without ML
        generator_no_ml = TerrainAwareLayoutGenerator(target_capacity_kw=1000.0)
        assets_no_ml, _, _ = generator_no_ml.generate(
            boundary=boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
        )
        
        # Layout with ML
        ml_scores = predictor.predict_suitability(
            dem_array=dem,
            slope_array=slope,
            boundary_mask=boundary_mask,
            transform=transform,
        )
        
        generator_ml = TerrainAwareLayoutGenerator(target_capacity_kw=1000.0)
        assets_ml, _, _ = generator_ml.generate(
            boundary=boundary,
            dem_array=dem,
            slope_array=slope,
            transform=transform,
            num_assets=10,
            suitability_scores={"default": ml_scores},
        )
        
        # ML version should have better average suitability scores
        def avg_suitability(assets, scores):
            total = 0
            count = 0
            for asset in assets:
                row, col = asset.grid_row, asset.grid_col
                if 0 <= row < 100 and 0 <= col < 100:
                    total += scores[row, col]
                    count += 1
            return total / count if count > 0 else 0
        
        avg_no_ml = avg_suitability(assets_no_ml, ml_scores)
        avg_ml = avg_suitability(assets_ml, ml_scores)
        
        # ML placement should have equal or better suitability
        assert avg_ml >= avg_no_ml * 0.95  # Allow 5% tolerance
```

---

## 5. Dependencies

### 5.1 New Python Dependencies
Add to `requirements.txt`:

```
# ML Suitability Scoring
xgboost>=2.0.0
scikit-learn>=1.3.0
pyyaml>=6.0
```

### 5.2 Optional Dependencies
```
# For advanced training (optional)
optuna>=3.0.0  # Hyperparameter tuning
dask>=2023.0.0  # Large raster processing
```

---

## 6. Rollout Plan

### 6.1 Phase 1: Backend ML Module (Days 1-2)
- [ ] Create `app/ml/` directory structure
- [ ] Implement `feature_engineering.py`
- [ ] Implement `synthetic_labeler.py`
- [ ] Implement `suitability_model.py`
- [ ] Implement `suitability_predictor.py`
- [ ] Create `config/suitability.yml`

### 6.2 Phase 2: Integration (Days 2-3)
- [ ] Modify `terrain_analysis_service.py`
- [ ] Modify `terrain_layout_generator.py` Poisson sampling
- [ ] Modify `terrain_layout_generator.py` grid placement
- [ ] Add training CLI script

### 6.3 Phase 3: API & Frontend (Day 4)
- [ ] Add `/terrain/ml-suitability` endpoint
- [ ] Add response schemas
- [ ] Add frontend terrain layer option
- [ ] Implement visualization styling

### 6.4 Phase 4: Testing & Documentation (Day 5)
- [ ] Write all unit tests
- [ ] Write integration tests
- [ ] Update API documentation
- [ ] Pre-train default model
- [ ] Performance benchmarking

---

## 7. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Model not available at runtime | Graceful fallback to rule-based scoring |
| Slow prediction latency | Use batch prediction, optimize feature extraction |
| Poor model accuracy | Tune hyperparameters, add more features |
| Training data bias | Generate diverse synthetic terrains |
| Memory issues with large rasters | Subsample during training, tile during prediction |

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Prediction latency | <200ms for 100k cells | Time profiling |
| Model accuracy | >85% on synthetic test set | Holdout validation |
| Integration test coverage | 100% of integration points | pytest coverage |
| Layout quality improvement | >10% higher avg suitability | A/B comparison |
| Fallback availability | 100% uptime | Error rate monitoring |

---

## 9. Future Enhancements

1. **Asset-specific models** — Train separate models for each asset type
2. **Real data training** — Use actual Pacifico layout feedback as labels
3. **Deep learning** — Replace XGBoost with CNN for spatial awareness
4. **Online learning** — Update model based on user feedback
5. **Multi-objective optimization** — Incorporate earthwork costs directly

---

## 10. Appendix: Test Data Generation

### Synthetic Terrain Generator
```python
def generate_synthetic_terrain(
    shape: tuple[int, int] = (200, 200),
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate synthetic terrain for model training.
    
    Creates realistic terrain with:
    - Varying elevation profiles (flat, hilly, mountain)
    - Slope gradients
    - Aspect variations
    - Exclusion zones (simulated wetlands, steep areas)
    """
    np.random.seed(seed)
    
    # Base elevation with Perlin-like noise
    from scipy.ndimage import gaussian_filter
    noise = np.random.randn(*shape)
    dem = gaussian_filter(noise, sigma=20) * 50 + 100  # 100m base, 50m variation
    
    # Compute slope from DEM
    # ... (use existing slope computation)
    
    # Compute aspect
    # ...
    
    return dem, slope, aspect, roughness
```

---

*Document Version: 1.0*  
*Created: December 3, 2025*  
*Author: AI Implementation Assistant*


