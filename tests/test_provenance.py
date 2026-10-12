import ast
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProvenanceTests(unittest.TestCase):
    def test_vendored_hashes_and_preserved_function_bodies(self):
        manifest = json.loads((ROOT / "upstream.lock.json").read_text())
        verified = 0
        for path, record in manifest["files"].items():
            source = (ROOT / "src/lerobot_lite/_vendor" / path).read_text()
            self.assertEqual(
                hashlib.sha256(source.encode()).hexdigest(), record["generated_sha256"], path
            )
            functions = {}
            for node in ast.parse(source).body:
                if isinstance(node, ast.FunctionDef):
                    functions[node.name] = node
                elif isinstance(node, ast.ClassDef):
                    functions.update(
                        {
                            f"{node.name}.{n.name}": n
                            for n in node.body
                            if isinstance(n, ast.FunctionDef)
                        }
                    )
            for name, expected in record["preserved_functions"].items():
                self.assertEqual(
                    hashlib.sha256(ast.dump(functions[name]).encode()).hexdigest(),
                    expected,
                    f"{path}:{name}",
                )
                verified += 1
        self.assertGreater(verified, 70)

    def test_installed_distribution_has_no_heavy_runtime_dependencies(self):
        requirements = importlib.metadata.requires("lerobot-lite")
        forbidden = ("lerobot[", "torch", "numpy", "datasets", "opencv", "transformers", "deepdiff")
        for requirement in requirements:
            self.assertFalse(any(name in requirement.lower() for name in forbidden), requirement)

    def test_fresh_process_imports_no_ml_or_camera_packages(self):
        code = (
            "import sys, lerobot_lite; "
            "forbidden = ('lerobot', 'torch', 'numpy', 'cv2', 'datasets', 'transformers'); "
            "assert not any(name.split('.')[0] in forbidden for name in sys.modules)"
        )
        completed = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
