"""Schema validator for data validation."""
import logging
import re
from typing import Any

from .schema import Schema
from .validation_error import ValidationError

_LOGGER = logging.getLogger(__name__)

class SchemaValidator:
    """Schema validator for data validation."""

    def __init__(self, schema: Schema):
        """Initialize the validator.

        Args:
            schema: Schema to validate against
        """
        self.schema = schema

    def validate(self, data: Any, path: str = "") -> None:
        """Validate data against the schema.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        schema_type = self.schema.get_type()

        # Validate type
        if schema_type == "object":
            self._validate_object(data, path)
        elif schema_type == "array":
            self._validate_array(data, path)
        elif schema_type == "string":
            self._validate_string(data, path)
        elif schema_type == "number":
            self._validate_number(data, path)
        elif schema_type == "integer":
            self._validate_integer(data, path)
        elif schema_type == "boolean":
            self._validate_boolean(data, path)
        elif schema_type == "null":
            self._validate_null(data, path)
        elif schema_type == "any":
            # Any type is valid
            pass
        else:
            raise ValidationError(f"Unknown schema type: {schema_type}", path)

    def _validate_object(self, data: Any, path: str) -> None:
        """Validate an object.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, dict):
            raise ValidationError(f"Expected object, got {type(data).__name__}", path)

        # Get properties
        properties = self.schema.get_properties()

        # Check required properties
        required = self.schema.get_required()
        for prop in required:
            if prop not in data:
                raise ValidationError(f"Missing required property: {prop}", path)

        # Validate properties
        for prop, value in data.items():
            prop_path = f"{path}.{prop}" if path else prop

            if prop in properties:
                # Get property schema
                prop_schema = self.schema.get_property_schema(prop)
                if prop_schema:
                    # Create validator for property
                    validator = SchemaValidator(prop_schema)

                    # Validate property
                    try:
                        validator.validate(value, prop_path)
                    except ValidationError as e:
                        # Check if property is nullable
                        if value is None and self.schema.is_nullable(prop):
                            continue

                        # Re-raise error
                        raise

    def _validate_array(self, data: Any, path: str) -> None:
        """Validate an array.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, list):
            raise ValidationError(f"Expected array, got {type(data).__name__}", path)

        # Get items schema
        items_schema = self.schema.get_items_schema()
        if items_schema:
            # Create validator for items
            validator = SchemaValidator(items_schema)

            # Validate items
            for i, item in enumerate(data):
                item_path = f"{path}[{i}]"
                validator.validate(item, item_path)

    def _validate_string(self, data: Any, path: str) -> None:
        """Validate a string.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, str):
            raise ValidationError(f"Expected string, got {type(data).__name__}", path)

        # Check min length
        min_length = self.schema.get_min_length()
        if min_length is not None and len(data) < min_length:
            raise ValidationError(f"String too short, minimum length is {min_length}", path)

        # Check max length
        max_length = self.schema.get_max_length()
        if max_length is not None and len(data) > max_length:
            raise ValidationError(f"String too long, maximum length is {max_length}", path)

        # Check pattern
        pattern = self.schema.get_pattern()
        if pattern is not None and not re.match(pattern, data):
            raise ValidationError(f"String does not match pattern: {pattern}", path)

        # Check enum
        enum = self.schema.get_enum()
        if enum is not None and data not in enum:
            raise ValidationError(f"String not in enum: {enum}", path)

    def _validate_number(self, data: Any, path: str) -> None:
        """Validate a number.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, (int, float)):
            raise ValidationError(f"Expected number, got {type(data).__name__}", path)

        # Check minimum
        minimum = self.schema.get_minimum()
        if minimum is not None and data < minimum:
            raise ValidationError(f"Number too small, minimum is {minimum}", path)

        # Check maximum
        maximum = self.schema.get_maximum()
        if maximum is not None and data > maximum:
            raise ValidationError(f"Number too large, maximum is {maximum}", path)

        # Check enum
        enum = self.schema.get_enum()
        if enum is not None and data not in enum:
            raise ValidationError(f"Number not in enum: {enum}", path)

    def _validate_integer(self, data: Any, path: str) -> None:
        """Validate an integer.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, int) or isinstance(data, bool):
            raise ValidationError(f"Expected integer, got {type(data).__name__}", path)

        # Check minimum
        minimum = self.schema.get_minimum()
        if minimum is not None and data < minimum:
            raise ValidationError(f"Integer too small, minimum is {minimum}", path)

        # Check maximum
        maximum = self.schema.get_maximum()
        if maximum is not None and data > maximum:
            raise ValidationError(f"Integer too large, maximum is {maximum}", path)

        # Check enum
        enum = self.schema.get_enum()
        if enum is not None and data not in enum:
            raise ValidationError(f"Integer not in enum: {enum}", path)

    def _validate_boolean(self, data: Any, path: str) -> None:
        """Validate a boolean.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(data, bool):
            raise ValidationError(f"Expected boolean, got {type(data).__name__}", path)

    def _validate_null(self, data: Any, path: str) -> None:
        """Validate a null value.

        Args:
            data: Data to validate
            path: Current path in the data

        Raises:
            ValidationError: If validation fails
        """
        if data is not None:
            raise ValidationError(f"Expected null, got {type(data).__name__}", path)
