"""
Compliance Rules Engine for Phase 5 compliance modeling.

Provides a flexible rules engine for expressing and evaluating constraints such as:
- Maximum slopes by road class and asset type
- Minimum distances to boundary or sensitive zones
- Basic code-like rules (e.g., min pad size for substations)
- Jurisdiction-specific constraint overrides

Rules can initially mirror existing parameters (slope limits, MAX_ROAD_GRADE_PCT) with 
explicit configuration, then be extended per jurisdiction.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class RuleType(str, Enum):
    """Types of compliance rules."""
    MAX_SLOPE = "max_slope"
    MIN_SPACING = "min_spacing"
    MIN_DISTANCE_TO_BOUNDARY = "min_distance_to_boundary"
    MIN_PAD_SIZE = "min_pad_size"
    MAX_ROAD_GRADE = "max_road_grade"
    CLEARANCE_FROM_UTILITIES = "clearance_from_utilities"
    WETLAND_BUFFER = "wetland_buffer"
    SETBACK_DISTANCE = "setback_distance"
    CUSTOM = "custom"


class Jurisdiction(str, Enum):
    """Jurisdiction codes for compliance."""
    CALIFORNIA = "ca"
    TEXAS = "tx"
    COLORADO = "co"
    UTAH = "ut"
    ARIZONA = "az"
    DEFAULT = "default"


@dataclass
class ComplianceRule:
    """
    Represents a single compliance rule.
    
    Rules are evaluated during layout generation and validation to ensure
    generated layouts meet jurisdiction-specific and project constraints.
    """
    rule_id: str
    rule_type: RuleType
    jurisdiction: Jurisdiction
    asset_type: Optional[str] = None  # None applies to all asset types
    value: float = 0.0
    unit: str = ""  # e.g., "degrees", "meters", "percent"
    description: str = ""
    enabled: bool = True
    override_reason: Optional[str] = None
    
    def __hash__(self):
        return hash(self.rule_id)
    
    def __eq__(self, other):
        if not isinstance(other, ComplianceRule):
            return False
        return self.rule_id == other.rule_id


@dataclass
class RuleViolation:
    """Represents a single rule violation."""
    rule_id: str
    rule_type: RuleType
    asset_type: Optional[str]
    message: str
    severity: str  # "error" or "warning"
    actual_value: float
    limit_value: float
    violating_asset_id: Optional[str] = None


@dataclass
class ComplianceCheckResult:
    """Result of compliance check."""
    is_compliant: bool
    violations: List[RuleViolation] = field(default_factory=list)
    warnings: List[RuleViolation] = field(default_factory=list)
    checked_rules_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "is_compliant": self.is_compliant,
            "violations_count": len(self.violations),
            "warnings_count": len(self.warnings),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_type": v.rule_type.value,
                    "asset_type": v.asset_type,
                    "message": v.message,
                    "severity": v.severity,
                    "actual_value": v.actual_value,
                    "limit_value": v.limit_value,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "rule_id": w.rule_id,
                    "rule_type": w.rule_type.value,
                    "asset_type": w.asset_type,
                    "message": w.message,
                    "severity": w.severity,
                    "actual_value": w.actual_value,
                    "limit_value": w.limit_value,
                }
                for w in self.warnings
            ],
            "checked_rules_count": self.checked_rules_count,
        }


class ComplianceRulesEngine:
    """
    Rules engine for evaluating compliance constraints on layouts.
    
    This engine evaluates generated layouts against a set of jurisdiction-specific
    and project-specific compliance rules. Rules can be added, removed, and customized
    per site or project.
    """
    
    # Default rules by jurisdiction
    DEFAULT_RULES = {
        Jurisdiction.DEFAULT: [
            ComplianceRule(
                rule_id="max_slope_solar",
                rule_type=RuleType.MAX_SLOPE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="solar_array",
                value=10.0,
                unit="degrees",
                description="Maximum slope for solar array placement",
            ),
            ComplianceRule(
                rule_id="max_slope_battery",
                rule_type=RuleType.MAX_SLOPE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="battery",
                value=4.0,
                unit="degrees",
                description="Maximum slope for battery placement",
            ),
            ComplianceRule(
                rule_id="max_slope_generator",
                rule_type=RuleType.MAX_SLOPE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="generator",
                value=5.0,
                unit="degrees",
                description="Maximum slope for generator placement",
            ),
            ComplianceRule(
                rule_id="max_slope_substation",
                rule_type=RuleType.MAX_SLOPE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="substation",
                value=3.0,
                unit="degrees",
                description="Maximum slope for substation placement",
            ),
            ComplianceRule(
                rule_id="max_slope_wind_turbine",
                rule_type=RuleType.MAX_SLOPE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="wind_turbine",
                value=15.0,
                unit="degrees",
                description="Maximum slope for wind turbine placement (more tolerant)",
            ),
            ComplianceRule(
                rule_id="max_road_grade",
                rule_type=RuleType.MAX_ROAD_GRADE,
                jurisdiction=Jurisdiction.DEFAULT,
                value=10.0,
                unit="percent",
                description="Maximum road grade for all roads",
            ),
            ComplianceRule(
                rule_id="min_spacing_default",
                rule_type=RuleType.MIN_SPACING,
                jurisdiction=Jurisdiction.DEFAULT,
                value=15.0,
                unit="meters",
                description="Minimum spacing between assets",
            ),
            ComplianceRule(
                rule_id="min_distance_boundary",
                rule_type=RuleType.MIN_DISTANCE_TO_BOUNDARY,
                jurisdiction=Jurisdiction.DEFAULT,
                value=5.0,
                unit="meters",
                description="Minimum setback from site boundary",
            ),
            ComplianceRule(
                rule_id="min_pad_size_substation",
                rule_type=RuleType.MIN_PAD_SIZE,
                jurisdiction=Jurisdiction.DEFAULT,
                asset_type="substation",
                value=25.0,
                unit="meters",
                description="Minimum pad size for substation (diagonal)",
            ),
        ],
        Jurisdiction.CALIFORNIA: [
            # California-specific overrides - more restrictive environmental rules
            ComplianceRule(
                rule_id="min_distance_boundary_ca",
                rule_type=RuleType.MIN_DISTANCE_TO_BOUNDARY,
                jurisdiction=Jurisdiction.CALIFORNIA,
                value=10.0,
                unit="meters",
                description="CA: More restrictive boundary setback",
            ),
            ComplianceRule(
                rule_id="wetland_buffer_ca",
                rule_type=RuleType.WETLAND_BUFFER,
                jurisdiction=Jurisdiction.CALIFORNIA,
                value=30.0,
                unit="meters",
                description="CA: Minimum wetland buffer per code",
            ),
        ],
        Jurisdiction.TEXAS: [
            # Texas-specific rules
            ComplianceRule(
                rule_id="setback_distance_tx",
                rule_type=RuleType.SETBACK_DISTANCE,
                jurisdiction=Jurisdiction.TEXAS,
                value=25.0,
                unit="meters",
                description="TX: Property line setback",
            ),
        ],
    }
    
    def __init__(self, jurisdiction: Jurisdiction = Jurisdiction.DEFAULT):
        """Initialize rules engine with jurisdiction defaults."""
        self.jurisdiction = jurisdiction
        self.custom_rules: Dict[str, ComplianceRule] = {}
        self.overrides: Dict[str, ComplianceRule] = {}
        
        # Load default rules for this jurisdiction + defaults
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default rules for jurisdiction and parent (DEFAULT)."""
        # Load DEFAULT rules first
        for rule in self.DEFAULT_RULES.get(Jurisdiction.DEFAULT, []):
            self.custom_rules[rule.rule_id] = rule
        
        # Override with jurisdiction-specific rules
        if self.jurisdiction != Jurisdiction.DEFAULT:
            for rule in self.DEFAULT_RULES.get(self.jurisdiction, []):
                self.custom_rules[rule.rule_id] = rule
    
    def add_rule(self, rule: ComplianceRule) -> None:
        """Add or override a compliance rule."""
        self.custom_rules[rule.rule_id] = rule
        logger.info(f"Added rule: {rule.rule_id} ({rule.rule_type.value})")
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a custom rule. Returns True if removed, False if not found."""
        if rule_id in self.custom_rules:
            del self.custom_rules[rule_id]
            logger.info(f"Removed rule: {rule_id}")
            return True
        return False
    
    def get_rules_for_asset(self, asset_type: str) -> List[ComplianceRule]:
        """Get all applicable rules for a specific asset type."""
        rules = []
        for rule in self.custom_rules.values():
            if rule.enabled and (rule.asset_type is None or rule.asset_type == asset_type):
                rules.append(rule)
        return rules
    
    def get_all_rules(self, enabled_only: bool = True) -> List[ComplianceRule]:
        """Get all rules, optionally filtering by enabled status."""
        rules = list(self.custom_rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return sorted(rules, key=lambda r: (r.rule_type.value, r.asset_type or ""))
    
    def check_max_slope(
        self,
        asset_type: str,
        actual_slope_deg: float,
        violations: List[RuleViolation],
    ) -> bool:
        """Check if asset slope complies with max slope rule."""
        compliant = True
        for rule in self.custom_rules.values():
            if (
                rule.enabled
                and rule.rule_type == RuleType.MAX_SLOPE
                and (rule.asset_type is None or rule.asset_type == asset_type)
            ):
                if actual_slope_deg > rule.value:
                    violations.append(
                        RuleViolation(
                            rule_id=rule.rule_id,
                            rule_type=rule.rule_type,
                            asset_type=asset_type,
                            message=f"{asset_type} slope {actual_slope_deg:.1f}° exceeds max {rule.value:.1f}°",
                            severity="error",
                            actual_value=actual_slope_deg,
                            limit_value=rule.value,
                        )
                    )
                    compliant = False
        return compliant
    
    def check_road_grade(
        self,
        actual_grade_pct: float,
        violations: List[RuleViolation],
    ) -> bool:
        """Check if road grade complies with max grade rule."""
        compliant = True
        for rule in self.custom_rules.values():
            if rule.enabled and rule.rule_type == RuleType.MAX_ROAD_GRADE:
                if actual_grade_pct > rule.value:
                    violations.append(
                        RuleViolation(
                            rule_id=rule.rule_id,
                            rule_type=rule.rule_type,
                            asset_type=None,
                            message=f"Road grade {actual_grade_pct:.1f}% exceeds max {rule.value:.1f}%",
                            severity="error",
                            actual_value=actual_grade_pct,
                            limit_value=rule.value,
                        )
                    )
                    compliant = False
        return compliant
    
    def check_minimum_spacing(
        self,
        actual_spacing_m: float,
        asset_type: str,
        violations: List[RuleViolation],
    ) -> bool:
        """Check if asset spacing complies with minimum spacing rule."""
        compliant = True
        for rule in self.custom_rules.values():
            if rule.enabled and rule.rule_type == RuleType.MIN_SPACING:
                if actual_spacing_m < rule.value:
                    violations.append(
                        RuleViolation(
                            rule_id=rule.rule_id,
                            rule_type=rule.rule_type,
                            asset_type=asset_type,
                            message=f"Spacing {actual_spacing_m:.1f}m is less than minimum {rule.value:.1f}m",
                            severity="warning",
                            actual_value=actual_spacing_m,
                            limit_value=rule.value,
                        )
                    )
                    compliant = False
        return compliant
    
    def check_boundary_setback(
        self,
        actual_distance_m: float,
        violations: List[RuleViolation],
    ) -> bool:
        """Check if asset setback from boundary complies with rule."""
        compliant = True
        for rule in self.custom_rules.values():
            if rule.enabled and rule.rule_type == RuleType.MIN_DISTANCE_TO_BOUNDARY:
                if actual_distance_m < rule.value:
                    violations.append(
                        RuleViolation(
                            rule_id=rule.rule_id,
                            rule_type=rule.rule_type,
                            asset_type=None,
                            message=f"Distance to boundary {actual_distance_m:.1f}m is less than minimum {rule.value:.1f}m",
                            severity="error",
                            actual_value=actual_distance_m,
                            limit_value=rule.value,
                        )
                    )
                    compliant = False
        return compliant
    
    def check_wetland_buffer(
        self,
        actual_distance_m: float,
        violations: List[RuleViolation],
    ) -> bool:
        """Check if wetland buffer complies with rule."""
        compliant = True
        for rule in self.custom_rules.values():
            if rule.enabled and rule.rule_type == RuleType.WETLAND_BUFFER:
                if actual_distance_m < rule.value:
                    violations.append(
                        RuleViolation(
                            rule_id=rule.rule_id,
                            rule_type=rule.rule_type,
                            asset_type=None,
                            message=f"Wetland buffer {actual_distance_m:.1f}m is less than required {rule.value:.1f}m",
                            severity="error",
                            actual_value=actual_distance_m,
                            limit_value=rule.value,
                        )
                    )
                    compliant = False
        return compliant
    
    def validate_layout(
        self,
        assets: List[Dict[str, Any]],
        roads: List[Dict[str, Any]] = None,
    ) -> ComplianceCheckResult:
        """
        Validate a complete layout against all compliance rules.
        
        Args:
            assets: List of asset dicts with keys: type, slope_deg, distance_to_boundary_m
            roads: List of road dicts with keys: grade_pct
        
        Returns:
            ComplianceCheckResult with violations and warnings
        """
        violations = []
        warnings = []
        checked_count = 0
        
        # Check asset constraints
        if assets:
            for asset in assets:
                asset_type = asset.get("type", "unknown")
                
                # Check max slope
                if "slope_deg" in asset:
                    self.check_max_slope(asset_type, asset["slope_deg"], violations)
                    checked_count += 1
                
                # Check boundary setback
                if "distance_to_boundary_m" in asset:
                    self.check_boundary_setback(asset["distance_to_boundary_m"], violations)
                    checked_count += 1
                
                # Check minimum spacing (warning only)
                if "min_spacing_m" in asset:
                    spacing_violations = []
                    self.check_minimum_spacing(asset["min_spacing_m"], asset_type, spacing_violations)
                    warnings.extend(spacing_violations)
                    checked_count += 1
        
        # Check road constraints
        if roads:
            for road in roads:
                if "grade_pct" in road:
                    self.check_road_grade(road["grade_pct"], violations)
                    checked_count += 1
        
        is_compliant = len(violations) == 0
        
        return ComplianceCheckResult(
            is_compliant=is_compliant,
            violations=violations,
            warnings=warnings,
            checked_rules_count=checked_count,
        )


def get_compliance_rules_engine(
    jurisdiction: str = "default",
) -> ComplianceRulesEngine:
    """
    Factory function to get a compliance rules engine for a jurisdiction.
    
    Args:
        jurisdiction: Jurisdiction code (e.g., 'ca', 'tx', 'default')
    
    Returns:
        ComplianceRulesEngine instance
    """
    try:
        juris = Jurisdiction(jurisdiction.lower())
    except ValueError:
        logger.warning(f"Unknown jurisdiction '{jurisdiction}', using DEFAULT")
        juris = Jurisdiction.DEFAULT
    
    return ComplianceRulesEngine(jurisdiction=juris)

