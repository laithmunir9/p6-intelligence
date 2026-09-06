from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient

from p6intel.report import ComparisonReport, compare_files


FIXTURES = Path(__file__).parent / "fixtures"


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from p6intel.api.app import app
        cls.client = TestClient(app)
        cls.before = FIXTURES / "reconcile_before.xer"
        cls.after = FIXTURES / "reconcile_after.xer"

    def files(self, before: bytes | None = None, after: bytes | None = None):
        return {
            "before": (self.before.name, self.before.read_bytes() if before is None else before, "application/octet-stream"),
            "after": (self.after.name, self.after.read_bytes() if after is None else after, "application/octet-stream"),
        }

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "p6-intelligence", "report_schema_version": "1.0"})

    def test_valid_compare_returns_canonical_report(self):
        response = self.client.post("/v1/compare", files=self.files())
        self.assertEqual(response.status_code, 200)
        report = ComparisonReport.model_validate(response.json())
        self.assertEqual(report.schema_version, "1.0")
        expected = compare_files(self.before, self.after).model_dump(mode="json")
        self.assertEqual(response.json(), expected)

    def test_repeated_requests_are_deterministic(self):
        first = self.client.post("/v1/compare", files=self.files())
        second = self.client.post("/v1/compare", files=self.files())
        self.assertEqual(first.status_code, second.status_code, 200)
        self.assertEqual(first.json(), second.json())

    def test_missing_and_empty_uploads(self):
        missing = self.client.post("/v1/compare", files={"before": self.files()["before"]})
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()["error"]["code"], "MISSING_UPLOAD")
        missing_before = self.client.post("/v1/compare", files={"after": self.files()["after"]})
        self.assertEqual(missing_before.status_code, 422)
        self.assertEqual(missing_before.json()["error"]["code"], "MISSING_UPLOAD")
        empty = self.client.post("/v1/compare", files=self.files(before=b""))
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.json()["error"]["code"], "EMPTY_UPLOAD")

    def test_malformed_and_oversized_uploads(self):
        malformed = self.client.post("/v1/compare", files=self.files(before=b"not an XER export"))
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"]["code"], "INVALID_XER")
        with patch.dict(os.environ, {"P6INTEL_MAX_UPLOAD_MB": "0.000001"}):
            oversized = self.client.post("/v1/compare", files=self.files(before=b"x" * 100))
            oversized_after = self.client.post("/v1/compare", files=self.files(after=b"x" * 100))
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"]["code"], "UPLOAD_TOO_LARGE")
        self.assertEqual(oversized_after.status_code, 413)
        self.assertEqual(oversized_after.json()["error"]["code"], "UPLOAD_TOO_LARGE")

    def test_errors_do_not_leak_paths_stack_traces_or_input(self):
        raw = b"/Users/private/project-secret.xer\npassword=hidden"
        response = self.client.post("/v1/compare", files=self.files(before=raw))
        body = response.text
        self.assertNotIn("/Users/private", body)
        self.assertNotIn("password=hidden", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("project-secret", body)

    def test_cors_is_not_wildcard_by_default(self):
        from p6intel.api.app import app
        cors = [middleware for middleware in app.user_middleware if middleware.cls.__name__ == "CORSMiddleware"]
        self.assertFalse(cors)


if __name__ == "__main__":
    unittest.main()
