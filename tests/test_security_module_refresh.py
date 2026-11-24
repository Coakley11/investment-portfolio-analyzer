"""suite_security_module_refresh: after an in-place pull, a pre-fix auth module must not stay loaded."""

import os
import subprocess
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
        # In a child process: dropping every app module here would disturb the other tests' imports.
        app_dir = os.path.dirname(os.path.abspath(refresh.__file__))
        code = (
            "import os, sys, types\n"
            "sys.path.insert(0, os.getcwd())\n"
            "import suite_security_module_refresh as r\n"
            "old = types.ModuleType('suite_auth_browser')\n"
            "old.__file__ = os.path.join(os.getcwd(), 'suite_auth_browser.py')\n"
            "sys.modules['suite_auth_browser'] = old\n"
            "assert 'suite_auth_browser' in r.refresh_pre_fix_modules()\n"
            "import suite_auth_browser as m\n"
            "print(hasattr(m, 'url_auth_restore_enabled') and m.url_auth_restore_enabled() is False)\n"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=app_dir, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.strip().splitlines()[-1:], ["True"], out.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
