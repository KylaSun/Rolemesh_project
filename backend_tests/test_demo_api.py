import contextlib
import io
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import uvicorn
from fastapi import HTTPException, Response
import database
import main
from seed_demo import seed_demo
from seed_projects import seed_projects


class DemoApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db_patch = patch.object(database, "DB_PATH", Path(cls.temp.name) / "test.db")
        cls.db_patch.start()
        database.init_db()
        cls.sock = socket.socket()
        cls.sock.bind(("127.0.0.1", 0))
        cls.base = f"http://127.0.0.1:{cls.sock.getsockname()[1]}"
        cls.server = uvicorn.Server(uvicorn.Config(main.app, log_level="critical", access_log=False))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [cls.sock]}, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started:
            if not cls.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Test server failed to start")
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.sock.close()
        cls.db_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("DELETE FROM project_roles")
                c.execute("DELETE FROM projects")
                c.execute("DELETE FROM talent_profiles")
                c.execute("DELETE FROM users")
        finally:
            c.close()
        with contextlib.redirect_stdout(io.StringIO()):
            seed_demo()
            seed_projects()

    def request(self, path, body=None):
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"}, method="GET" if body is None else "PATCH")
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_success_uses_database_profile_and_roles(self):
        code, body, headers = self.request("/demo/matches")
        self.assertEqual(code, 200)
        self.assertEqual(body["meta"]["profile_source"], "sqlite")
        self.assertEqual(body["meta"]["roles_source"], "sqlite")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(body["data"]["contract_version"], "0.1.0")
        self.assertEqual(len(body["data"]["comparisons"]), 4)
        self.assertTrue(body["data"]["projects"])
        self.assertTrue(all(x["profile_version"] == 1 for x in body["data"]["comparisons"]))
        self.assertNotIn("experience_summary", json.dumps(body["data"]))

    def test_hours_update_changes_matching_and_persists_version(self):
        self.assertTrue(self.request("/demo/matches")[1]["data"]["projects"])
        code, body, _ = self.request("/demo/profile/hours", {"availability_hours_per_week": 2})
        self.assertEqual(code, 200)
        self.assertEqual(body["data"]["profile_version"], 2)
        code, result, _ = self.request("/demo/matches")
        self.assertEqual(result["meta"]["profile_version"], 2)
        self.assertEqual(result["data"]["projects"], [])
        self.assertTrue(all(x["eligibility"] == "ineligible" for x in result["data"]["comparisons"]))
        self.assertEqual(self.request("/demo/profile")[1]["data"]["availability_hours_per_week"], 2)

    def test_invalid_update_does_not_change_saved_data(self):
        before = self.request("/demo/profile")[1]
        for value in [200, -1, True, "8"]:
            self.assertEqual(self.request("/demo/profile/hours", {"availability_hours_per_week": value})[0], 422)
        self.assertEqual(self.request("/demo/profile")[1], before)

    def test_missing_profile_is_404(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("DELETE FROM talent_profiles")
        finally:
            c.close()
        self.assertEqual(self.request("/demo/matches")[0], 404)

    def test_bad_stored_contract_is_server_error(self):
        c = database.get_connection()
        try:
            with c:
                row = c.execute("SELECT profile_json FROM talent_profiles").fetchone()
                profile = json.loads(row[0])
                profile["availability_hours_per_week"] = 999
                c.execute("UPDATE talent_profiles SET profile_json = ?", (json.dumps(profile),))
        finally:
            c.close()
        code, body, _ = self.request("/demo/matches")
        self.assertEqual(code, 500)
        self.assertNotIn("999", json.dumps(body))
        self.assertNotIn("data", body)

    def test_unavailable_roles_is_server_error_not_empty_recommendations(self):
        with patch.object(main, "load_demo_roles", side_effect=RuntimeError("database unavailable")):
            self.assertEqual(self.request("/demo/matches")[0], 500)


    def test_project_list_detail_and_pagination(self):
        code, body, _ = self.request("/demo/projects?limit=1&offset=1")
        self.assertEqual(code, 200)
        self.assertEqual(body["data"]["total"], 3)
        self.assertEqual(len(body["data"]["items"]), 1)
        code, body, _ = self.request("/demo/projects/project.education")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["data"]["roles"]), 2)
        self.assertNotIn("owner_user_id", body["data"])
        self.assertEqual(self.request("/demo/projects/nonexistent")[0], 404)
        self.assertEqual(self.request("/demo/projects?limit=0")[0], 422)

    def test_full_roles_are_not_recommended(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("UPDATE project_roles SET filled_count = required_count, role_version = role_version + 1")
        finally:
            c.close()
        _, body, _ = self.request("/demo/matches")
        self.assertEqual(body["data"]["projects"], [])
        self.assertTrue(all(r["role_version"] == 2 for r in body["data"]["comparisons"]))

    def test_empty_database_candidates_returns_empty_success(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("DELETE FROM project_roles")
        finally:
            c.close()
        code, body, _ = self.request("/demo/matches")
        self.assertEqual(code, 200)
        self.assertEqual(body["data"]["comparisons"], [])

    def test_demo_endpoints_do_not_return_non_demo_projects(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("UPDATE projects SET is_demo = 0 WHERE project_id = ?", ("project.education",))
        finally:
            c.close()
        self.assertEqual(self.request("/demo/projects/project.education")[0], 404)
        self.assertEqual(self.request("/demo/projects")[1]["data"]["total"], 2)
        comparisons = self.request("/demo/matches")[1]["data"]["comparisons"]
        self.assertFalse(any(x["project_id"] == "project.education" for x in comparisons))

    def test_seed_and_migration_are_repeatable_without_overwriting(self):
        c = database.get_connection()
        try:
            with c:
                c.execute("UPDATE project_roles SET recruitment_status = ? WHERE role_id = ?", ("paused", "role.education.frontend"))
        finally:
            c.close()
        seed_projects()
        database.init_db()
        self.assertEqual(self.request("/demo/projects")[1]["data"]["total"], 3)
        body = self.request("/demo/projects/project.education")[1]
        role = next(r for r in body["data"]["roles"] if r["role_id"] == "role.education.frontend")
        self.assertEqual(role["recruitment_status"], "paused")

    def test_openapi_exposes_demo_endpoint(self):
        code, body, _ = self.request("/openapi.json")
        self.assertEqual(code, 200)
        self.assertIn("/demo/matches", body["paths"])


if __name__ == "__main__":
    unittest.main()
