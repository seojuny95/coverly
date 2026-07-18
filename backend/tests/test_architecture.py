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

FORBIDDEN_FEATURE_IMPORTS: dict[str, tuple[str, ...]] = {
    "consultation": (
        "app.modules.analysis",
        "app.modules.coverage",
        "app.modules.evidence",
        "app.modules.policy",
        "app.modules.portfolio",
        "app.modules.qa",
        "app.modules.reference_data",
        "app.modules.upload",
    ),
    "coverage": (
        "app.modules.analysis",
        "app.modules.evidence",
        "app.modules.policy",
        "app.modules.portfolio",
        "app.modules.qa",
    ),
    "evidence": ("app.modules.qa",),
    "reference_data": (
        "app.modules.analysis",
        "app.modules.evidence",
        "app.modules.policy",
        "app.modules.portfolio",
        "app.modules.qa",
    ),
}

VENDOR_CLIENT_NAMESPACES = ("openai", "psycopg")


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


def _imports_namespace(module: str, namespace: str) -> bool:
    return module == namespace or module.startswith(f"{namespace}.")


def _feature_import_graph() -> dict[str, set[str]]:
    modules_root = APP_ROOT / "modules"
    features = {
        path.name for path in modules_root.iterdir() if path.is_dir() and _python_files(path)
    }
    graph: dict[str, set[str]] = {feature: set() for feature in features}
    for feature in features:
        for path in _python_files(modules_root / feature):
            for module in _imported_modules(path):
                parts = module.split(".")
                if len(parts) < 3 or parts[:2] != ["app", "modules"]:
                    continue
                dependency = parts[2]
                if dependency in features and dependency != feature:
                    graph[feature].add(dependency)
    return graph


def test_removed_app_namespaces_are_not_imported() -> None:
    offenders: list[str] = []
    roots = (APP_ROOT, BACKEND_ROOT / "evals", BACKEND_ROOT / "tests")

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


def test_core_does_not_import_business_modules() -> None:
    offenders = [
        str(path.relative_to(BACKEND_ROOT))
        for path in _python_files(APP_ROOT / "core")
        if any(_imports_namespace(module, "app.modules") for module in _imported_modules(path))
    ]

    assert offenders == []


def test_low_level_features_do_not_depend_on_higher_level_features() -> None:
    offenders: list[str] = []
    for feature, forbidden_namespaces in FORBIDDEN_FEATURE_IMPORTS.items():
        for path in _python_files(APP_ROOT / "modules" / feature):
            imported_modules = _imported_modules(path)
            if any(
                _imports_namespace(module, namespace)
                for module in imported_modules
                for namespace in forbidden_namespaces
            ):
                offenders.append(str(path.relative_to(BACKEND_ROOT)))

    assert offenders == []


def test_feature_import_graph_is_acyclic() -> None:
    remaining = _feature_import_graph()
    while independent := {
        feature for feature, dependencies in remaining.items() if not dependencies
    }:
        remaining = {
            feature: dependencies - independent
            for feature, dependencies in remaining.items()
            if feature not in independent
        }

    cycle_edges = {
        feature: sorted(dependency for dependency in dependencies if dependency in remaining)
        for feature, dependencies in remaining.items()
    }
    assert cycle_edges == {}


def test_business_modules_do_not_import_vendor_clients_directly() -> None:
    offenders = [
        str(path.relative_to(BACKEND_ROOT))
        for path in _python_files(APP_ROOT / "modules")
        if any(
            _imports_namespace(module, namespace)
            for module in _imported_modules(path)
            for namespace in VENDOR_CLIENT_NAMESPACES
        )
    ]

    assert offenders == []
