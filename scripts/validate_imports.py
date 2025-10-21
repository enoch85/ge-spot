#!/usr/bin/env python3
"""Validate all imports in the codebase.

This script:
1. Lists all imports in all Python files
2. Lists all available modules in the codebase
3. Cross-checks for incorrect imports
4. Reports missing modules or wrong import paths
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class ImportValidator:
    """Validates imports across the codebase."""

    def __init__(self, base_path: str):
        """Initialize validator.
        
        Args:
            base_path: Root path of the project
        """
        self.base_path = Path(base_path)
        self.component_path = self.base_path / "custom_components" / "ge_spot"
        self.available_modules: Set[str] = set()
        self.imports_by_file: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def scan_available_modules(self) -> None:
        """Scan and register all available modules in the codebase."""
        print("📦 Scanning available modules...")
        
        for py_file in self.component_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                # Package module
                rel_path = py_file.parent.relative_to(self.component_path)
                if str(rel_path) == ".":
                    module = "custom_components.ge_spot"
                else:
                    module = f"custom_components.ge_spot.{str(rel_path).replace(os.sep, '.')}"
            else:
                # File module
                rel_path = py_file.relative_to(self.component_path)
                module_parts = list(rel_path.parts[:-1]) + [py_file.stem]
                module = f"custom_components.ge_spot.{'.'.join(module_parts)}"
            
            self.available_modules.add(module)
        
        print(f"   Found {len(self.available_modules)} modules")

    def extract_imports(self, file_path: Path) -> List[Tuple[str, str]]:
        """Extract all imports from a Python file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            List of (import_type, module_name) tuples
        """
        imports = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(("import", alias.name))
                
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    level = node.level
                    
                    # Resolve relative imports
                    if level > 0:
                        # Calculate the absolute module path
                        rel_path = file_path.relative_to(self.component_path)
                        current_package_parts = list(rel_path.parts[:-1])
                        
                        # Go up 'level' directories
                        base_parts = current_package_parts[:-level] if level <= len(current_package_parts) else []
                        
                        if module:
                            full_module = f"custom_components.ge_spot.{'.'.join(base_parts + [module])}" if base_parts else f"custom_components.ge_spot.{module}"
                        else:
                            full_module = f"custom_components.ge_spot.{'.'.join(base_parts)}" if base_parts else "custom_components.ge_spot"
                    else:
                        full_module = module
                    
                    for alias in node.names:
                        imports.append(("from", f"{full_module}.{alias.name}"))
        
        except SyntaxError as e:
            self.warnings.append(f"⚠️  Syntax error in {file_path}: {e}")
        except Exception as e:
            self.warnings.append(f"⚠️  Error parsing {file_path}: {e}")
        
        return imports

    def scan_all_imports(self) -> None:
        """Scan all Python files and extract their imports."""
        print("\n🔍 Scanning imports in all files...")
        
        py_files = list(self.component_path.rglob("*.py"))
        for py_file in py_files:
            rel_path = py_file.relative_to(self.base_path)
            imports = self.extract_imports(py_file)
            self.imports_by_file[str(rel_path)] = imports
        
        print(f"   Scanned {len(py_files)} Python files")

    def validate_imports(self) -> None:
        """Validate all imports against available modules."""
        print("\n✅ Validating imports...")
        
        for file_path, imports in self.imports_by_file.items():
            for import_type, imported_name in imports:
                # Skip standard library and third-party imports
                if not imported_name.startswith("custom_components.ge_spot"):
                    continue
                
                # Extract the base module (without the final attribute/class)
                if import_type == "from":
                    # For "from X import Y", check if X exists
                    parts = imported_name.rsplit(".", 1)
                    if len(parts) == 2:
                        module_path, item_name = parts
                    else:
                        module_path = imported_name
                        item_name = None
                else:
                    # For "import X", check if X exists
                    module_path = imported_name
                    item_name = None
                
                # Check if the module exists
                if module_path not in self.available_modules:
                    # Try to find similar modules (for better error messages)
                    similar = self._find_similar_modules(module_path)
                    
                    error_msg = f"❌ {file_path}: Cannot import from '{module_path}'"
                    if item_name:
                        error_msg += f" (importing '{item_name}')"
                    
                    if similar:
                        error_msg += f"\n   💡 Did you mean: {', '.join(similar[:3])}?"
                    
                    self.errors.append(error_msg)

    def _find_similar_modules(self, target: str) -> List[str]:
        """Find similar module names.
        
        Args:
            target: Target module name
            
        Returns:
            List of similar module names
        """
        target_parts = target.split(".")
        similar = []
        
        for module in self.available_modules:
            module_parts = module.split(".")
            
            # Check if the last part matches
            if target_parts[-1] == module_parts[-1]:
                similar.append(module)
            # Check if it's a substring match
            elif target_parts[-1] in module:
                similar.append(module)
        
        return sorted(similar)

    def print_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "=" * 70)
        print("📊 IMPORT VALIDATION SUMMARY")
        print("=" * 70)
        
        print(f"\n📦 Available modules: {len(self.available_modules)}")
        print(f"📄 Scanned files: {len(self.imports_by_file)}")
        
        # Count internal imports
        internal_import_count = 0
        for imports in self.imports_by_file.values():
            internal_import_count += sum(1 for _, name in imports if name.startswith("custom_components.ge_spot"))
        print(f"🔗 Internal imports: {internal_import_count}")
        
        if self.warnings:
            print(f"\n⚠️  Warnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"   {warning}")
        
        if self.errors:
            print(f"\n❌ Errors found: {len(self.errors)}")
            print()
            for error in self.errors:
                print(error)
            print()
        else:
            print("\n✅ All imports are valid!")
        
        print("=" * 70)

    def list_all_modules(self) -> None:
        """List all available modules."""
        print("\n📋 Available Modules:")
        print("-" * 70)
        
        sorted_modules = sorted(self.available_modules)
        for module in sorted_modules:
            short_name = module.replace("custom_components.ge_spot.", "")
            print(f"   • {short_name}")

    def run(self, verbose: bool = False) -> int:
        """Run the validation.
        
        Args:
            verbose: If True, print detailed information
            
        Returns:
            Exit code (0 = success, 1 = errors found)
        """
        print("🔧 Import Validator")
        print("=" * 70)
        
        self.scan_available_modules()
        self.scan_all_imports()
        self.validate_imports()
        
        if verbose:
            self.list_all_modules()
        
        self.print_summary()
        
        return 0 if not self.errors else 1


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate imports in the GE-Spot codebase"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed information"
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Path to the project root (default: current directory)"
    )
    
    args = parser.parse_args()
    
    validator = ImportValidator(args.path)
    exit_code = validator.run(verbose=args.verbose)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
