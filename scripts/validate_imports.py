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
        self.usage_by_file: Dict[str, Set[str]] = defaultdict(set)  # Track name usage
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
            with open(file_path, "r", encoding="utf-8") as f:
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
                        # If this is an __init__.py, the package is the parent directory
                        if file_path.name == "__init__.py":
                            current_package_parts = list(rel_path.parts[:-1])
                        else:
                            # For regular files, the package is the directory chain
                            current_package_parts = list(rel_path.parts[:-1])

                        # Go up 'level-1' directories (level=1 means current package)
                        # level=1: same package, level=2: parent package, etc.
                        levels_to_go_up = level - 1
                        base_parts = (
                            current_package_parts[:-levels_to_go_up]
                            if levels_to_go_up > 0
                            and levels_to_go_up <= len(current_package_parts)
                            else current_package_parts
                        )

                        if module:
                            # Add the module path to the base
                            module_parts = base_parts + module.split(".")
                            full_module = (
                                f"custom_components.ge_spot.{'.'.join(module_parts)}"
                            )
                        else:
                            # Just the base package
                            full_module = (
                                f"custom_components.ge_spot.{'.'.join(base_parts)}"
                                if base_parts
                                else "custom_components.ge_spot"
                            )
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

    def extract_name_usage(self, file_path: Path) -> Set[str]:
        """Extract all names used in a Python file.

        Args:
            file_path: Path to Python file

        Returns:
            Set of name strings used in the file
        """
        used_names = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            for node in ast.walk(tree):
                # Track all Name nodes (variable/function/class references)
                if isinstance(node, ast.Name):
                    used_names.add(node.id)
                # Track Attribute access (e.g., module.function)
                elif isinstance(node, ast.Attribute):
                    # Get the base name
                    if isinstance(node.value, ast.Name):
                        used_names.add(node.value.id)
                # Track function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        used_names.add(node.func.id)

        except Exception as e:
            pass  # Silently skip files we can't parse

        return used_names

    def scan_name_usage(self) -> None:
        """Scan all files for name usage."""
        print("\n🔎 Scanning name usage in all files...")

        py_files = list(self.component_path.rglob("*.py"))
        for py_file in py_files:
            rel_path = py_file.relative_to(self.base_path)
            used_names = self.extract_name_usage(py_file)
            self.usage_by_file[str(rel_path)] = used_names

        print(f"   Scanned {len(py_files)} Python files for usage")

    def check_unused_imports(self) -> List[Tuple[str, str]]:
        """Check for unused imports.

        Returns:
            List of (file_path, import_name) tuples for unused imports
        """
        unused = []

        for file_path, imports in self.imports_by_file.items():
            used_names = self.usage_by_file.get(file_path, set())

            for import_type, imported_name in imports:
                # Extract the name that would be used in code
                if import_type == "import":
                    # For "import foo.bar", the used name is "foo"
                    used_name = imported_name.split(".")[0]
                else:
                    # For "from foo import bar", the used name is "bar"
                    used_name = imported_name.split(".")[-1]

                # Special cases to skip
                if used_name in ["__all__", "__version__", "TYPE_CHECKING"]:
                    continue

                # Check if this is an __init__.py that re-exports (has __all__)
                if file_path.endswith("__init__.py") and "__all__" in used_names:
                    # Skip checking unused imports in __init__.py with __all__
                    # These are intentional re-exports
                    continue

                # Check if the name is used
                if used_name not in used_names:
                    unused.append((file_path, used_name, imported_name))

        return unused

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
            internal_import_count += sum(
                1 for _, name in imports if name.startswith("custom_components.ge_spot")
            )
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

        # Check for unused imports
        unused_imports = self.check_unused_imports()
        if unused_imports:
            print(f"\n⚠️  Unused imports found: {len(unused_imports)}")
            print()
            # Group by file
            by_file = defaultdict(list)
            for file_path, used_name, imported_name in unused_imports:
                by_file[file_path].append((used_name, imported_name))

            for file_path in sorted(by_file.keys()):
                print(f"📄 {file_path}:")
                for used_name, imported_name in by_file[file_path]:
                    print(f"   • {used_name} (from {imported_name})")
            print()
        else:
            print("\n✨ No unused imports found!")

        print("=" * 70)

    def list_all_modules(self) -> None:
        """List all available modules."""
        print("\n📋 Available Modules:")
        print("-" * 70)

        sorted_modules = sorted(self.available_modules)
        for module in sorted_modules:
            short_name = module.replace("custom_components.ge_spot.", "")
            print(f"   • {short_name}")

    def check_any_usage(self) -> List[Tuple[str, int, str]]:
        """Check for usage of 'Any' type hint.

        Returns:
            List of (file_path, line_number, line_content) tuples
        """
        any_usages = []

        for py_file in self.component_path.rglob("*.py"):
            rel_path = py_file.relative_to(self.base_path)
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        # Check for Any type hint usage (but not in comments)
                        stripped = line.split("#")[0]  # Remove comments
                        if "Any" in stripped and (
                            "typing.Any" in line
                            or "from typing import" in line
                            or ": Any" in stripped
                            or "[Any" in stripped
                            or ", Any" in stripped
                        ):
                            any_usages.append((str(rel_path), line_num, line.strip()))
            except Exception:
                pass

        return any_usages

    def run(self, verbose: bool = False, check_any: bool = False) -> int:
        """Run the validation.

        Args:
            verbose: If True, print detailed information
            check_any: If True, check for 'Any' type hint usage

        Returns:
            Exit code (0 = success, 1 = errors found)
        """
        print("🔧 Import Validator")
        print("=" * 70)

        self.scan_available_modules()
        self.scan_all_imports()
        self.validate_imports()
        self.scan_name_usage()

        if verbose:
            self.list_all_modules()

        self.print_summary()

        if check_any:
            any_usages = self.check_any_usage()
            if any_usages:
                print("\n" + "=" * 70)
                print("🔍 'Any' TYPE HINT USAGE")
                print("=" * 70)
                print(f"\n⚠️  Found {len(any_usages)} usages of 'Any' type hint:\n")

                current_file = None
                for file_path, line_num, line_content in any_usages:
                    if file_path != current_file:
                        print(f"\n📄 {file_path}:")
                        current_file = file_path
                    print(f"   Line {line_num}: {line_content}")

                print(
                    "\n💡 Consider replacing 'Any' with specific types for better type safety."
                )
                print("=" * 70)

        return 0 if not self.errors else 1


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate imports in the GE-Spot codebase"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed information"
    )
    parser.add_argument(
        "--check-any", action="store_true", help="Check for usage of 'Any' type hint"
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Path to the project root (default: current directory)",
    )

    args = parser.parse_args()

    validator = ImportValidator(args.path)
    exit_code = validator.run(verbose=args.verbose, check_any=args.check_any)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
