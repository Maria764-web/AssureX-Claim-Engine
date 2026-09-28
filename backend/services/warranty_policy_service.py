"""
AssureX Warranty Policy Service
Loads and queries category-based warranty policies from JSON configuration.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_POLICY_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "warranty_policies.json"
_policy_cache: Optional[Dict[str, Any]] = None


def _load_policies() -> Dict[str, Any]:
    """Load policies from JSON config, with simple in-process caching."""
    global _policy_cache
    if _policy_cache is not None:
        return _policy_cache
    try:
        with open(_POLICY_FILE, "r", encoding="utf-8") as f:
            _policy_cache = json.load(f)
        logger.info("Warranty policies loaded from %s", _POLICY_FILE)
    except FileNotFoundError:
        logger.warning("warranty_policies.json not found at %s — using empty policy.", _POLICY_FILE)
        _policy_cache = {"default_policy": {}, "categories": {}}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in warranty_policies.json: %s", e)
        _policy_cache = {"default_policy": {}, "categories": {}}
    return _policy_cache


def get_all_policies() -> Dict[str, Any]:
    """Return the full policy configuration dict."""
    return _load_policies()


def get_policy_for_category(category: str) -> Dict[str, Any]:
    """
    Return the policy for a specific product category.
    Falls back to default_policy if the category is not found.
    """
    policies = _load_policies()
    categories = policies.get("categories", {})

    # Case-insensitive match
    for key, pol in categories.items():
        if key.lower() == (category or "").lower():
            merged = {**policies.get("default_policy", {}), **pol}
            merged["category_key"] = key
            return merged

    # Fall back to default
    default = dict(policies.get("default_policy", {}))
    default["category_key"] = "default"
    return default


def get_covered_damage_types(category: str) -> list:
    """Return covered damage types for a category."""
    policy = get_policy_for_category(category)
    return policy.get("covered_damage_types", [])


def is_damage_covered(category: str, damage_type: str) -> bool:
    """Check if a specific damage type is covered under a category's policy."""
    policy = get_policy_for_category(category)
    excluded = [d.lower() for d in policy.get("excluded_damage_types", [])]
    covered = [d.lower() for d in policy.get("covered_damage_types", [])]

    if damage_type.lower() in excluded:
        return False
    if covered and damage_type.lower() not in covered:
        return False
    return True


def get_max_claim_age(category: str) -> int:
    """Return the maximum product age in months allowed for claims in this category."""
    policy = get_policy_for_category(category)
    return policy.get("max_claim_age_months", 36)


def reload_policies() -> None:
    """Force a reload of the policy file (clears cache)."""
    global _policy_cache
    _policy_cache = None
    _load_policies()
