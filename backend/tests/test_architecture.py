"""Dependency rules that keep the backend package boundaries explicit."""

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

LEGACY_APP_NAMESPACES = (
    "app.errors",
    "app.routes",
    "app.schemas",
    "app.services",
    "app.settings",
)


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return tuple(imports)


def test_removed_app_namespaces_are_not_imported() -> None:
    offenders: list[str] = []
    roots = (APP_ROOT, BACKEND_ROOT / "evals", BACKEND_ROOT / "scripts", BACKEND_ROOT / "tests")

    for root in roots:
        for path in _python_files(root):
            imported_modules = _imported_modules(path)
            imports_legacy_namespace = any(
                module == namespace or module.startswith(f"{namespace}.")
                for module in imported_modules
                for namespace in LEGACY_APP_NAMESPACES
            )
            if imports_legacy_namespace:
                offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []


def test_runtime_app_does_not_import_evaluation_code() -> None:
    offenders: list[str] = []

    for path in _python_files(APP_ROOT):
        imports_evals = any(
            module == "evals" or module.startswith("evals.") for module in _imported_modules(path)
        )
        if imports_evals:
            offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []


def test_rag_does_not_import_business_modules() -> None:
    offenders: list[str] = []

    for path in _python_files(APP_ROOT / "rag"):
        imports_module = any(
            module == "app.modules" or module.startswith("app.modules.")
            for module in _imported_modules(path)
        )
        if imports_module:
            offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []


def test_rag_evaluators_live_outside_runtime_package() -> None:
    runtime_eval_files = [
        path
        for path in _python_files(APP_ROOT / "rag")
        if "evaluation" in path.parts or "evals" in path.parts
    ]

    assert runtime_eval_files == []
