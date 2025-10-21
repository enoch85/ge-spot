"""Schema definition for data validation."""

from typing import Dict, Any, List, Union, Optional


class Schema:
    """Schema definition for data validation."""

    def __init__(self, schema_def: Dict[str, Any]):
        """Initialize the schema.

        Args:
            schema_def: Schema definition
        """
        self.schema_def = schema_def

    def get_type(self) -> str:
        """Get the schema type.

        Returns:
            Schema type
        """
        return self.schema_def.get("type", "any")

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        """Get the schema properties.

        Returns:
            Schema properties
        """
        return self.schema_def.get("properties", {})

    def get_items(self) -> Optional[Dict[str, Any]]:
        """Get the schema items.

        Returns:
            Schema items
        """
        return self.schema_def.get("items")

    def get_required(self) -> List[str]:
        """Get the required properties.

        Returns:
            Required properties
        """
        return self.schema_def.get("required", [])

    def get_enum(self) -> Optional[List[Any]]:
        """Get the enum values.

        Returns:
            Enum values
        """
        return self.schema_def.get("enum")

    def get_minimum(self) -> Optional[Union[int, float]]:
        """Get the minimum value.

        Returns:
            Minimum value
        """
        return self.schema_def.get("minimum")

    def get_maximum(self) -> Optional[Union[int, float]]:
        """Get the maximum value.

        Returns:
            Maximum value
        """
        return self.schema_def.get("maximum")

    def get_min_length(self) -> Optional[int]:
        """Get the minimum length.

        Returns:
            Minimum length
        """
        return self.schema_def.get("minLength")

    def get_max_length(self) -> Optional[int]:
        """Get the maximum length.

        Returns:
            Maximum length
        """
        return self.schema_def.get("maxLength")

    def get_pattern(self) -> Optional[str]:
        """Get the pattern.

        Returns:
            Pattern
        """
        return self.schema_def.get("pattern")

    def get_format(self) -> Optional[str]:
        """Get the format.

        Returns:
            Format
        """
        return self.schema_def.get("format")

    def is_optional(self, property_name: str) -> bool:
        """Check if a property is optional.

        Args:
            property_name: Property name

        Returns:
            True if optional, False otherwise
        """
        properties = self.get_properties()
        if property_name in properties:
            return properties[property_name].get("optional", False)

        return False

    def is_nullable(self, property_name: str) -> bool:
        """Check if a property is nullable.

        Args:
            property_name: Property name

        Returns:
            True if nullable, False otherwise
        """
        properties = self.get_properties()
        if property_name in properties:
            return properties[property_name].get("nullable", False)

        return False

    def get_property_schema(self, property_name: str) -> Optional["Schema"]:
        """Get the schema for a property.

        Args:
            property_name: Property name

        Returns:
            Property schema
        """
        properties = self.get_properties()
        if property_name in properties:
            return Schema(properties[property_name])

        return None

    def get_items_schema(self) -> Optional["Schema"]:
        """Get the schema for array items.

        Returns:
            Items schema
        """
        items = self.get_items()
        if items:
            return Schema(items)

        return None
