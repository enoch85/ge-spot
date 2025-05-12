# filepath: /workspaces/ge-spot/custom_components/ge_spot/api/registry.py
import yaml
from pathlib import Path
from typing import Type, List, Dict, Any

from .base_api import BaseAPI # Changed from BaseAPIAdapter

# Global mapping: api_name -> API class
API_REGISTRY: Dict[str, Type[BaseAPI]] = {} # Changed from ADAPTER_REGISTRY and BaseAPIAdapter


def register_api( # Changed from register_adapter
    name: str,
    regions: List[str],
    default_priority: int = 0
):
    """
    Decorator to register an API class under a given name,
    and annotate which regions it supports.
    """
    def decorator(cls: Type[BaseAPI]) -> Type[BaseAPI]: # Changed from BaseAPIAdapter
        cls.api_name = name # Changed from adapter_name
        cls.supported_regions = regions
        cls.default_priority = default_priority
        API_REGISTRY[name] = cls # Changed from ADAPTER_REGISTRY
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


def create_apis_for_region( # Changed from create_adapters_for_region
    region: str,
    config: Dict[str, Any], # General config for the integration
    session: Any, # HTTP session
) -> List[BaseAPI]: # Changed from BaseAPIAdapter
    """
    Instantiates APIs in the order defined by the region's YAML.
    Unrecognized API names are skipped.
    Passes relevant parts of the config to each API.
    """
    chain = get_chain_for_region(region)
    instances: List[BaseAPI] = [] # Changed from BaseAPIAdapter
    for name in chain:
        ApiCls = API_REGISTRY.get(name) # Changed from AdapterCls and ADAPTER_REGISTRY
        if ApiCls:
            # Pass the main config and session to the API's constructor
            # The API can then pick what it needs.
            instances.append(ApiCls(config=config, session=session)) # Changed from AdapterCls
    return instances

def get_api_class(name: str) -> Type[BaseAPI] | None: # Changed from get_adapter_class and BaseAPIAdapter
    """Retrieve an API class by its registered name."""
    return API_REGISTRY.get(name) # Changed from ADAPTER_REGISTRY

def get_all_registered_apis() -> Dict[str, Type[BaseAPI]]: # Changed from get_all_registered_adapters and BaseAPIAdapter
    """Retrieve all registered API classes."""
    return API_REGISTRY.copy() # Changed from ADAPTER_REGISTRY

