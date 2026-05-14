"""
Config-driven threshold constraints for verification routing.
"""

from typing import Dict

# Baseline mapping of Sensitivity Levels to exact expected confidence minimums
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "PUBLIC": 0.70,
    "INTERNAL": 0.78,
    "CONFIDENTIAL": 0.85,
    "SECRET": 0.93,
}

# Domains with unusually high reliability limits mapped by tag
DOMAIN_OVERRIDES: Dict[str, float] = {
    "procurement": 0.90,
    "failure_analysis": 0.88,
    "telemetry": 0.86,
    "admin": 0.75,
}

# The absolute floor below which a single metric ruins answer validity regardless of mathematical averages
METRIC_FLOORS: Dict[str, float] = {
    "consistency": 0.60,
    "citation_integrity": 0.50,
}
