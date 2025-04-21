"""Mock Home Assistant classes for testing."""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MockConfig:
    """Mock Home Assistant config for testing."""
    def __init__(self, time_zone: str = "Europe/Stockholm"):
        """Initialize with specified timezone.
        
        Args:
            time_zone: The timezone to use (default: Europe/Stockholm)
        """
        self.time_zone = time_zone
        self.latitude = 59.3293
        self.longitude = 18.0686
        self.elevation = 0
        self.unit_system = {"temperature": "°C", "length": "km", "mass": "kg", "volume": "L"}
        self.location_name = "Stockholm"
        self.language = "en"


class MockHass:
    """Mock Home Assistant instance for testing."""
    def __init__(self, time_zone: str = "Europe/Stockholm"):
        """Initialize with specified timezone and empty data.
        
        Args:
            time_zone: The timezone to use (default: Europe/Stockholm)
        """
        self.config = MockConfig(time_zone)
        self.data = {}
        self.states = {}
        self.services = {}
        self.components = set()
        self.loop = asyncio.get_event_loop()
        self._callbacks = {}
        self._callback_id = 0
        
    async def async_add_executor_job(self, func: Callable, *args) -> Any:
        """Mock the async_add_executor_job method.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            
        Returns:
            Result of the function call
        """
        try:
            return func(*args)
        except Exception as e:
            logger.error(f"Error in executor job: {e}")
            raise
    
    def async_create_task(self, coroutine):
        """Mock the async_create_task method.
        
        Args:
            coroutine: Coroutine to create a task for
            
        Returns:
            Task object
        """
        return self.loop.create_task(coroutine)
    
    def async_add_job(self, target, *args):
        """Mock the async_add_job method.
        
        Args:
            target: Function or coroutine to call
            *args: Arguments to pass to the function
            
        Returns:
            Task object or None
        """
        if asyncio.iscoroutine(target) or asyncio.iscoroutinefunction(target):
            return self.async_create_task(target(*args))
        
        return self.async_add_executor_job(target, *args)
    
    def async_track_time_interval(self, action, interval):
        """Mock the async_track_time_interval method.
        
        Args:
            action: Callback function
            interval: Time interval
            
        Returns:
            Callback remove function
        """
        self._callback_id += 1
        callback_id = self._callback_id
        self._callbacks[callback_id] = (action, interval)
        
        def remove_callback():
            if callback_id in self._callbacks:
                del self._callbacks[callback_id]
        
        return remove_callback
    
    def state_attributes_mock(self, entity_id: str) -> Dict[str, Any]:
        """Mock the state_attributes property.
        
        Args:
            entity_id: Entity ID to get attributes for
            
        Returns:
            Dictionary of attributes
        """
        if entity_id in self.states:
            return self.states[entity_id].get("attributes", {})
        return {}
    
    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get the state of an entity.
        
        Args:
            entity_id: Entity ID to get state for
            
        Returns:
            State dictionary or None if entity doesn't exist
        """
        return self.states.get(entity_id)
    
    def set_state(self, entity_id: str, state: str, attributes: Dict[str, Any] = None):
        """Set the state of an entity.
        
        Args:
            entity_id: Entity ID to set state for
            state: State value
            attributes: Optional attributes dictionary
        """
        self.states[entity_id] = {
            "state": state,
            "attributes": attributes or {},
            "last_changed": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        }
    
    def register_service(self, domain: str, service: str, service_func: Callable):
        """Register a service.
        
        Args:
            domain: Service domain
            service: Service name
            service_func: Service function
        """
        if domain not in self.services:
            self.services[domain] = {}
        
        self.services[domain][service] = service_func
    
    def call_service(self, domain: str, service: str, service_data: Dict[str, Any] = None):
        """Call a service.
        
        Args:
            domain: Service domain
            service: Service name
            service_data: Service data
            
        Returns:
            Result of service call
        """
        if domain in self.services and service in self.services[domain]:
            return self.services[domain][service](service_data or {})
        
        logger.warning(f"Service {domain}.{service} not found")
        return None
