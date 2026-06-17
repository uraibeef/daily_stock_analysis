# -*- coding: utf-8 -*-
"""API contract tests for intelligence source endpoints."""

from __future__ import annotations

import os
import tempfile
import unittest
import socket
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager

RSS_FIXTURE = b'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><item><title>Market event</title><link>https://news.example.com/market-event</link><description>Evidence summary</description></item></channel></rss>'


class IntelligenceApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = os.path.join(self._temp_dir.name, "api_intel.db")
        Config._instance = None
        DatabaseManager.reset_instance()
        self._dns_patcher = patch(
            "src.services.intelligence_service.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
        )
        self._dns_patcher.start()
        self.addCleanup(self._dns_patcher.stop)
        self.client = TestClient(create_app(static_dir=Path(self._temp_dir.name)))

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _mock_response(self):
        response = Mock()
        response.status_code = 200
        response.url = "https://feeds.example.com/rss.xml"
        response.headers = {}
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [RSS_FIXTURE]
        return response

    def test_create_fetch_and_query_items(self) -> None:
        create_resp = self.client.post("/api/v1/intelligence/sources", json={"name": "api-feed", "url": "https://feeds.example.com/rss.xml", "source_type": "rss", "scope_type": "market", "market": "cn"})
        self.assertEqual(create_resp.status_code, 200)
        source_id = create_resp.json()["id"]
        with patch("src.services.intelligence_service.requests.get", return_value=self._mock_response()):
            fetch_resp = self.client.post(f"/api/v1/intelligence/sources/{source_id}/fetch")
        self.assertEqual(fetch_resp.status_code, 200)
        self.assertEqual(fetch_resp.json()["saved_count"], 1)
        list_resp = self.client.get("/api/v1/intelligence/items", params={"scope_type": "market", "market": "cn"})
        self.assertEqual(list_resp.status_code, 200)
        body = list_resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["url"], "https://news.example.com/market-event")

    def test_rejects_private_source_url(self) -> None:
        resp = self.client.post("/api/v1/intelligence/sources", json={"name": "bad", "url": "http://localhost/rss.xml", "scope_type": "market"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "validation_error")

    def test_fetch_source_internal_error_is_sanitized(self) -> None:
        create_resp = self.client.post("/api/v1/intelligence/sources", json={"name": "api-feed", "url": "https://feeds.example.com/rss.xml", "source_type": "rss", "scope_type": "market", "market": "cn"})
        self.assertEqual(create_resp.status_code, 200)
        source_id = create_resp.json()["id"]
        with patch("src.services.intelligence_service.IntelligenceService.fetch_source", side_effect=RuntimeError("token=secret api_key=abc12345")):
            fetch_resp = self.client.post(f"/api/v1/intelligence/sources/{source_id}/fetch")

        self.assertEqual(fetch_resp.status_code, 500)
        body = fetch_resp.json()
        self.assertEqual(body["error"], "internal_error")
        self.assertTrue(body["message"].startswith("Fetch intelligence source failed"))
        self.assertNotIn("token=secret", body["message"])
        self.assertNotIn("abc12345", body["message"])


if __name__ == "__main__":
    unittest.main()
