"""Main setup's explicit Pi opt-in. All child commands are inert mocks."""
import os
import subprocess
from types import SimpleNamespace
from unittest import mock

from support import FixtureCase, put, snapshot


class PiEntrypointTests(FixtureCase):
    def setUp(self):
        super().setUp()
        (self.home / '.local/share/omarchy/default/hypr').mkdir(parents=True)
        self.helper = put(self.repo / 'setup_pi.sh', b'#!/bin/bash\nexit 0\n', 0o755)
        for name, data in [('desktop', b'git\n'), ('development', b'python\n'),
                           ('apps', b'example-app\n'), ('pi', b'nodejs\nnpm\nrust\n')]:
            put(self.repo / 'packages' / (name + '.txt'), data)

    def invoke(self, argv, fail_mode=None):
        calls = []

        def run(command, **kwargs):
            calls.append(list(command))
            if command[0] == str(self.helper):
                self.assertFalse((self.home / '.bashrc').exists())
                if command[-1] == fail_mode:
                    raise subprocess.CalledProcessError(7, command)
            return SimpleNamespace(returncode=0)

        with mock.patch.dict(os.environ, {'HOME': str(self.home)}, clear=True), \
                mock.patch.object(self.engine.subprocess, 'run', side_effect=run), \
                mock.patch.object(self.engine.shutil, 'which', side_effect=lambda name: '/fake/' + name):
            result = self.engine.main(argv)
        return result, calls

    def test_pi_is_not_installed_without_opt_in(self):
        result, calls = self.invoke([])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [])
        self.assertTrue((self.home / '.bashrc').is_file())

    def test_pi_preview_invokes_only_helper_preview_and_writes_nothing(self):
        before = snapshot(self.home)
        result, calls = self.invoke(['--pi', '--dry-run'])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [[str(self.helper), '--dry-run']])
        self.assertEqual(snapshot(self.home), before)

    def test_pi_prerequisites_and_preflight_precede_bootstrap_and_config_changes(self):
        result, calls = self.invoke(['--pi', '--packages'])
        self.assertEqual(result, 0)
        self.assertEqual(calls[0], ['sudo', 'pacman', '-S', '--needed',
                                    'git', 'python', 'nodejs', 'npm', 'rust'])
        self.assertEqual(calls[1:], [[str(self.helper), '--preflight'],
                                     [str(self.helper), '--install']])
        self.assertTrue((self.home / '.bashrc').is_file())

    def test_pi_package_manifest_is_explicit(self):
        self.assertEqual(self.engine.package_names(), ['git', 'python'])
        self.assertEqual(self.engine.package_names(include_pi=True),
                         ['git', 'python', 'nodejs', 'npm', 'rust'])
        self.assertEqual(self.engine.package_names(include_apps=True, include_pi=True),
                         ['git', 'python', 'example-app', 'nodejs', 'npm', 'rust'])

    def test_failed_pi_preflight_does_not_install_dotfiles(self):
        before = snapshot(self.home)
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(['--pi'], fail_mode='--preflight')
        self.assertEqual(snapshot(self.home), before)

    def test_failed_pi_bootstrap_does_not_install_dotfiles(self):
        before = snapshot(self.home)
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(['--pi'], fail_mode='--install')
        self.assertEqual(snapshot(self.home), before)

    def test_pi_rejects_offline_home_staging(self):
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--pi', '--home', str(self.home)])
        self.assertEqual(snapshot(self.home), before)

    def test_pi_rejects_restore_mode(self):
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--pi', '--restore', str(self.home / 'not-an-install')])
        self.assertEqual(snapshot(self.home), before)

    def test_pi_refuses_a_symlink_helper(self):
        self.helper.unlink()
        outside = put(self.base / 'outside-helper', b'not executable\n')
        self.helper.symlink_to(outside)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--pi'])
        self.assertEqual(snapshot(self.home), before)
