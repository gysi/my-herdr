"""fork_request: the one-shot hand-off from the popup to fork-tab."""
import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr import fork_request
from myherdr.errors import MyHerdrError

NOW = 1000000.0


class RequestTest(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, self.state, True)
        self.path = os.path.join(self.state, fork_request.FILE_NAME)

    def write(self, content):
        with open(self.path, "w") as handle:
            handle.write(content if isinstance(content, str) else json.dumps(content))

    def test_what_is_saved_is_what_is_taken(self):
        fork_request.save(self.state, "w1:p1", "spike", now=NOW)
        self.assertEqual(fork_request.take(self.state, now=NOW + 0.1),
                         {"pane_id": "w1:p1", "name": "spike"})

    def test_a_request_is_taken_once_and_leaves_nothing_behind(self):
        fork_request.save(self.state, "w1:p1", "spike", now=NOW)
        fork_request.take(self.state, now=NOW)
        self.assertIsNone(fork_request.take(self.state, now=NOW))
        self.assertEqual(os.listdir(self.state), [])

    def test_no_request_is_none(self):
        self.assertIsNone(fork_request.take(self.state, now=NOW))
        self.assertIsNone(fork_request.take(None, now=NOW))

    def test_the_age_limit(self):
        for age, taken in ((0.0, True), (fork_request.REQUEST_TTL, True),
                           (fork_request.REQUEST_TTL + 0.1, False),
                           (-0.5, True), (-5.0, False)):
            fork_request.save(self.state, "w1:p1", "x", now=NOW - age)
            result = fork_request.take(self.state, now=NOW)
            self.assertEqual(result is not None, taken, "age %s" % age)

    def test_malformed_requests_are_ignored_and_removed(self):
        for content in ("{not json", "[]", {"pane_id": "w1:p1"},
                        {"pane_id": "", "written_at": NOW},
                        {"pane_id": 7, "written_at": NOW},
                        {"pane_id": "w1:p1", "written_at": "now"}):
            self.write(content)
            self.assertIsNone(fork_request.take(self.state, now=NOW), content)
            self.assertEqual(os.listdir(self.state), [])

    def test_a_blank_or_odd_name_is_no_name(self):
        for name in (None, "", 42):
            self.write({"pane_id": "w1:p1", "name": name, "written_at": NOW})
            self.assertIsNone(fork_request.take(self.state, now=NOW)["name"])

    def test_saving_replaces_an_earlier_request(self):
        fork_request.save(self.state, "w1:p1", "old", now=NOW)
        fork_request.save(self.state, "w1:p2", "new", now=NOW)
        self.assertEqual(fork_request.take(self.state, now=NOW)["name"], "new")

    def test_saving_without_a_state_directory_is_an_error(self):
        with self.assertRaises(MyHerdrError):
            fork_request.save(None, "w1:p1", "x")
        with self.assertRaises(MyHerdrError):
            fork_request.save(os.path.join(self.state, "missing"), "w1:p1", "x")

    def test_drop_withdraws_a_request(self):
        fork_request.save(self.state, "w1:p1", "x", now=NOW)
        fork_request.drop(self.state)
        fork_request.drop(self.state)  # twice is fine
        fork_request.drop(None)
        self.assertIsNone(fork_request.take(self.state, now=NOW))


if __name__ == "__main__":
    unittest.main()
