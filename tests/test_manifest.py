"""The manifest check, against the real manifest and against deliberate breakage."""
import os
import shutil
import tempfile
import unittest

import support

import check_manifest

HAS_TOMLLIB = check_manifest.tomllib is not None


def manifest(**overrides):
    base = {
        "id": "my-herdr",
        "name": "my-herdr",
        "version": "0.1.0",
        "min_herdr_version": "0.9.1",
        "platforms": ["linux", "macos"],
        "actions": [{
            "id": "ping",
            "title": "my-herdr: ping",
            "command": ["python3", "bin/my-herdr", "ping"],
        }],
    }
    base.update(overrides)
    return base


class RealManifestTest(unittest.TestCase):
    @unittest.skipUnless(HAS_TOMLLIB, "tomllib needs Python 3.11+")
    def test_the_shipped_manifest_is_valid(self):
        self.assertEqual(
            check_manifest.main([os.path.join(support.ROOT, "herdr-plugin.toml")]), 0)


class RequiredKeysTest(unittest.TestCase):
    def test_a_good_manifest_has_no_problems(self):
        self.assertEqual(check_manifest.check(manifest()), [])

    def test_every_required_key_is_enforced(self):
        for key in check_manifest.REQUIRED:
            broken = manifest()
            del broken[key]
            problems = check_manifest.check(broken)
            self.assertTrue(any(key in p for p in problems), "%s not reported" % key)

    def test_empty_values_count_as_missing(self):
        self.assertTrue(check_manifest.check(manifest(name="   ")))

    def test_min_herdr_version_must_be_semver(self):
        # herdr refuses to link when this is not a semantic version.
        problems = check_manifest.check(manifest(min_herdr_version="latest"))
        self.assertTrue(any("semantic version" in p for p in problems))

    def test_uppercase_id_is_rejected(self):
        problems = check_manifest.check(manifest(id="My-Herdr"))
        self.assertTrue(any("lowercase" in p for p in problems))

    def test_missing_platforms_is_reported(self):
        problems = check_manifest.check(manifest(platforms=None))
        self.assertTrue(any("platforms" in p for p in problems))

    def test_unknown_platform_is_rejected(self):
        self.assertTrue(check_manifest.check(manifest(platforms=["linux", "bsd"])))


class ActionTest(unittest.TestCase):
    def test_dotted_action_id_is_rejected(self):
        # Dots would make the qualified id `my-herdr.a.b` ambiguous.
        problems = check_manifest.check(manifest(actions=[
            {"id": "fork.tab", "title": "t", "command": ["python3", "bin/my-herdr", "fork.tab"]}]))
        self.assertTrue(any("no dots" in p for p in problems))

    def test_duplicate_ids_are_rejected(self):
        action = {"id": "ping", "title": "t", "command": ["python3", "bin/my-herdr", "ping"]}
        problems = check_manifest.check(manifest(actions=[action, dict(action)]))
        self.assertTrue(any("duplicate" in p for p in problems))

    def test_command_must_be_an_argv_array(self):
        problems = check_manifest.check(manifest(actions=[
            {"id": "ping", "title": "t", "command": "python3 bin/my-herdr ping"}]))
        self.assertTrue(any("argv array" in p for p in problems))

    def test_empty_command_element_is_rejected(self):
        problems = check_manifest.check(manifest(actions=[
            {"id": "ping", "title": "t", "command": ["python3", "", "ping"]}]))
        self.assertTrue(any("non-empty string" in p for p in problems))

    def test_title_is_required(self):
        problems = check_manifest.check(manifest(actions=[
            {"id": "ping", "command": ["python3", "bin/my-herdr", "ping"]}]))
        self.assertTrue(any("title" in p for p in problems))

    def test_action_without_a_module_is_reported(self):
        # The manifest would link fine and then fail at keypress time.
        problems = check_manifest.check(manifest(actions=[
            {"id": "not-built-yet", "title": "t",
             "command": ["python3", "bin/my-herdr", "not-built-yet"]}]))
        self.assertTrue(any("myherdr/actions/not_built_yet.py" in p for p in problems))

    def test_command_that_routes_elsewhere_is_reported(self):
        # Copy-pasting a block and forgetting to change the argument would
        # silently run the wrong action.
        problems = check_manifest.check(manifest(actions=[
            {"id": "ping", "title": "t", "command": ["python3", "bin/my-herdr", "pong"]}]))
        self.assertTrue(any("never mentions the id" in p for p in problems))


class PaneTest(unittest.TestCase):
    """Pane rules, against a throwaway plugin root that has the modules."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="my-herdr-manifest-")
        self.addCleanup(shutil.rmtree, self.root, True)
        for package in ("actions", "panes"):
            directory = os.path.join(self.root, "myherdr", package)
            os.makedirs(directory)
            open(os.path.join(directory, "ping.py"), "w").close()

    def check(self, entry_overrides):
        entry = {"id": "ping", "title": "t", "command": ["python3", "bin/my-herdr", "pane", "ping"]}
        entry.update(entry_overrides)
        return check_manifest.check(manifest(panes=[entry]), root=self.root)

    def test_size_without_popup_is_rejected(self):
        # herdr fails the link with invalid_plugin_pane_size.
        problems = self.check({"placement": "split", "width": "70%"})
        self.assertTrue(any("popup" in p for p in problems))

    def test_size_with_popup_is_fine(self):
        self.assertEqual(self.check({"placement": "popup", "width": "70%", "height": 12}), [])

    def test_default_placement_is_fine(self):
        # placement is optional and defaults to overlay.
        self.assertEqual(self.check({}), [])

    def test_unknown_placement_is_rejected(self):
        self.assertTrue(self.check({"placement": "floating"}))

    def test_panes_resolve_against_the_panes_package(self):
        problems = check_manifest.check(manifest(panes=[
            {"id": "fork-prompt", "title": "t",
             "command": ["python3", "bin/my-herdr", "pane", "fork-prompt"]}]))
        self.assertTrue(any("myherdr/panes/fork_prompt.py" in p for p in problems))


class LinkHandlerTest(unittest.TestCase):
    def test_handler_must_point_at_a_declared_action(self):
        problems = check_manifest.check(manifest(link_handlers=[
            {"id": "h", "title": "t", "pattern": "^https://example\\.com/", "action": "nope"}]))
        self.assertTrue(any("not declared" in p for p in problems))

    def test_valid_handler_passes(self):
        self.assertEqual(check_manifest.check(manifest(link_handlers=[
            {"id": "h", "title": "t", "pattern": "^https://example\\.com/", "action": "ping"}])), [])


if __name__ == "__main__":
    unittest.main()
