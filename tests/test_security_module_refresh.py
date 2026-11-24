"""suite_security_module_refresh: after an in-place pull, a pre-fix auth module must not stay loaded."""

import os
import sys
import tempfile
import types
import unittest

import suite_security_module_refresh as refresh


class SecurityModuleRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = {n: sys.modules.get(n) for n in ("suite_auth_browser", "_qa_app_mod", "_qa_outside_mod")}

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def _fake(self, name, directory, **attrs):
        module = types.ModuleType(name)
        module.__file__ = os.path.join(directory, name + ".py")
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        return module

    def test_pre_fix_auth_module_drops_app_modules_only(self):
        self._fake("suite_auth_browser", self.tmp)  # pre-fix: no url_auth_restore_enabled
        self._fake("_qa_app_mod", self.tmp)
        self._fake("_qa_outside_mod", tempfile.mkdtemp())
        dropped = refresh.refresh_pre_fix_modules(self.tmp)
        self.assertIn("suite_auth_browser", dropped)
        self.assertIn("_qa_app_mod", dropped)
        self.assertNotIn("suite_auth_browser", sys.modules)
        self.assertNotIn("_qa_app_mod", sys.modules)
        self.assertIn("_qa_outside_mod", sys.modules)

    def test_fixed_auth_module_is_left_alone(self):
        self._fake("suite_auth_browser", self.tmp, url_auth_restore_enabled=lambda: False)
        self._fake("_qa_app_mod", self.tmp)
        self.assertEqual(refresh.refresh_pre_fix_modules(self.tmp), [])
        self.assertIn("_qa_app_mod", sys.modules)

    def test_reimport_after_refresh_is_the_fixed_module(self):
        self._fake("suite_auth_browser", os.path.dirname(os.path.abspath(refresh.__file__)))
        refresh.refresh_pre_fix_modules()
        import suite_auth_browser  # noqa: PLC0415  (loads the file on disk)

        self.assertTrue(hasattr(suite_auth_browser, "url_auth_restore_enabled"))
        self.assertFalse(suite_auth_browser.url_auth_restore_enabled())


if __name__ == "__main__":
    unittest.main()
