\
# filepath: /workspaces/ge-spot/custom_components/ge_spot/api/registry.py
import yaml
from pathlib import Path
from typing import Type, List, Dict, Any

from .base_adapter import BaseAPIAdapter

# Global mapping: adapter_name -> Adapter class
ADAPTER_REGISTRY: Dict[str, Type[BaseAPIAdapter]] = {}


def register_adapter(
    name: str,
    regions: List[str],
    default_priority: int = 0
):
    """
    Decorator to register an adapter class under a given name,
    and annotate which regions it supports.
    """
    def decorator(cls: Type[BaseAPIAdapter]) -> Type[BaseAPIAdapter]:
        cls.adapter_name = name
        cls.supported_regions = regions
        cls.default_priority = default_priority
        ADAPTER_REGISTRY[name] = cls
        return cls
    return decorator


def get_chain_for_region(region: str) -> List[str]:
    """
    Load the fallback_chain for a region from
    custom_components/ge_spot/config/regions/{region}.yaml
    """
    # Simplified path for now, assuming config is within the integration's root
    # TODO: Adjust path if config/regions is outside custom_components/ge_spot
    try:
        cfg_path = Path(__file__).parent.parent / "config" / "regions" / f"{region}.yaml"
        if not cfg_path.exists():
            # Fallback to a default or empty chain if specific region config not found
            # This part might need adjustment based on desired behavior for missing configs
            cfg_path = Path(__file__).parent.parent / "config" / "regions" / "_default.yaml" # Example default
            if not cfg_path.exists():
                return [] # Or raise an error

        data = yaml.safe_load(cfg_path.read_text())
        return data.get("fallback_chain", [])
    except Exception:
        # Log error or handle appropriately
        return []


def create_adapters_for_region(
    region: str,
    config: Dict[str, Any], # General config for the integration
    session: Any, # HTTP session
) -> List[BaseAPIAdapter]:
    """
    Instantiates adapters in the order defined by the region's YAML.
    Unrecognized adapter names are skipped.
    Passes relevant parts of the config to each adapter.
    """
    chain = get_chain_for_region(region)
    instances: List[BaseAPIAdapter] = []
    for name in chain:
        AdapterCls = ADAPTER_REGISTRY.get(name)
        if AdapterCls:
            # Pass the main config and session to the adapter's constructor
            # The adapter can then pick what it needs.
            instances.append(AdapterCls(config=config, session=session))
    return instances

def get_adapter_class(name: str) -> Type[BaseAPIAdapter] | None:
    """Retrieve an adapter class by its registered name."""
    return ADAPTER_REGISTRY.get(name)

def get_all_registered_adapters() -> Dict[str, Type[BaseAPIAdapter]]:
    """Retrieve all registered adapter classes."""
    return ADAPTER_REGISTRY.copy()

