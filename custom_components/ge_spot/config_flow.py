"""Config flow for GE-Spot integration.

This module is intentionally a thin re-export shim. At runtime the
``config_flow/`` package shadows this file (Python resolves a package over a
same-named module), so the actual flow lives in
``config_flow/implementation.py`` and ``config_flow/options.py``.

Do NOT delete this file. Home Assistant's ``hassfest`` validation requires a
``config_flow.py`` file to exist whenever ``manifest.json`` declares
``config_flow: true`` -- it performs a ``Path.is_file()`` check and never
imports the module. Without this file the ``Hassfest Validation`` / ``validate``
CI jobs fail with: "Config flows need to be defined in the file config_flow.py".
"""

from .config_flow.implementation import GSpotConfigFlow
from .config_flow.options import GSpotOptionsFlow

__all__ = ["GSpotConfigFlow", "GSpotOptionsFlow"]
