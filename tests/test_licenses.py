"""Check the licensing declarations and notices actually shipped by this package."""

import importlib.metadata
import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LicenseTests(unittest.TestCase):
    def test_project_declares_apache_and_packages_notices(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["license"], "Apache-2.0")
        self.assertEqual(set(project["license-files"]), {"LICENSE", "NOTICE"})
        license_text = (ROOT / "LICENSE").read_text()
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        notice = (ROOT / "NOTICE").read_text()
        self.assertIn("The HuggingFace Inc. team", notice)
        self.assertIn("7e241bd630a3719a56157a497ce5d08f244784f1", notice)
        self.assertIn("Changes:", notice)

    def test_vendored_files_keep_original_copyright_license_and_change_notice(self):
        manifest = json.loads((ROOT / "upstream.lock.json").read_text())
        for path in manifest["files"]:
            with self.subTest(path=path):
                source = (ROOT / "src/lerobot_lite/_vendor" / path).read_text()
                header = "\n".join(source.splitlines()[:25])
                self.assertIn("Copyright", header)
                self.assertIn("The HuggingFace Inc. team", header)
                self.assertIn("Apache License, Version 2.0", header)
                self.assertIn("modified", header.lower())

    def test_reviewed_dependency_versions_have_expected_declarations(self):
        sdk = importlib.metadata.distribution("feetech-servo-sdk")
        self.assertEqual(sdk.version, "1.0.0")
        self.assertEqual(sdk.metadata["License"], "UNLICENSE")
        # A dependency upgrade is not a claim that the newer release was audited.
        serial = importlib.metadata.distribution("pyserial")
        if serial.version == "3.5":
            header = serial.locate_file("serial/__init__.py").read_text()
            self.assertIn("BSD-3-Clause", header)
        progress = importlib.metadata.distribution("tqdm")
        if progress.version == "4.70.1":
            self.assertEqual(progress.metadata["License"], "MPL-2.0 AND MIT")
