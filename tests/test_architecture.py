"""Feature isolation, lazy loading, and registry entrypoint contracts."""
import ast
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tests import support
from myherdr.entrypoints import ENTRYPOINTS

FEATURES = {"attention", "forking", "pane_to_tab", "diagnostics"}


def imported_modules(path):
    """Resolve ordinary import statements in one runtime source file.

    Args:
        path (Path): Python source file below the checkout's myherdr directory.

    Returns:
        set[str]: Absolute module names, including possible modules imported
            through from-import aliases. External packages are included.

    Raises:
        OSError: The source cannot be read.
        SyntaxError: The source cannot be parsed.
    """
    package = ".".join(path.parent.relative_to(support.ROOT).parts)
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            names.add(base)
            names.update(base + "." + alias.name for alias in node.names)
    return names


class ArchitectureTest(unittest.TestCase):
    def test_feature_and_shared_dependencies_respect_package_boundaries(self):
        root = Path(support.ROOT, "myherdr")
        for owner in FEATURES | {"shared"}:
            for path in (root / owner).glob("*.py"):
                for name in imported_modules(path):
                    if name.startswith("myherdr."):
                        with self.subTest(source=str(path.relative_to(root)), imported=name):
                            self.assertIn(name.split(".")[1], {owner, "shared"})

    def test_registry_targets_have_callable_main_accepting_arguments(self):
        for routes in ENTRYPOINTS.values():
            for public_id, target in routes.items():
                with self.subTest(public_id=public_id):
                    module = importlib.import_module(target)
                    self.assertTrue(callable(module.main))
                    inspect.signature(module.main).bind([])

    def test_help_and_dispatch_import_only_needed_features(self):
        # Fresh interpreters keep previous test imports from hiding eager loads.
        # Replace the selected main after import so no real action can run.
        script = """
import contextlib
import importlib
import io
import json
import sys
from myherdr import cli
original = importlib.import_module

def load(name):
    module = original(name)
    module.main = lambda args: 0
    return module

cli.importlib.import_module = load
with contextlib.redirect_stdout(io.StringIO()):
    cli.main([sys.argv[1]])
print(json.dumps(sorted(sys.modules)))
"""
        for action, expected in (("--help", set()), ("attention-next", {"attention"}),
                                 ("fork-tab", {"forking"}), ("ping", {"diagnostics"})):
            with self.subTest(action=action):
                result = subprocess.run([sys.executable, "-B", "-c", script, action],
                                        cwd=support.ROOT, capture_output=True, text=True,
                                        timeout=30, check=True)
                names = json.loads(result.stdout)
                loaded = {name.split(".")[1] for name in names
                          if name.startswith("myherdr.") and name.split(".")[1] in FEATURES}
                self.assertEqual(loaded, expected)
