"""Cleanup opt-in orchestration. Child processes are inert, never real removals."""
import os
import subprocess
from types import SimpleNamespace
from unittest import mock

from support import FixtureCase, REPO, put, snapshot


class CleanupEntrypointTests(FixtureCase):
    def setUp(self):
        super().setUp()
        (self.home / '.local/share/omarchy/default/hypr').mkdir(parents=True)
        self.helper = put(self.repo / 'setup_cleanup.sh', b'#!/bin/bash\nexit 0\n', 0o755)
        self.pi_helper = put(self.repo / 'setup_pi.sh', b'#!/bin/bash\nexit 0\n', 0o755)
        for name, data in [('desktop', b'git\n'), ('development', b'python\n'),
                           ('apps', b'example-app\n'), ('pi', b'mise\nrust\n')]:
            put(self.repo / 'packages' / (name + '.txt'), data)

    def invoke(self, argv, fail_mode=None, fail_pi_mode=None):
        calls = []

        def run(command, **kwargs):
            calls.append(list(command))
            if command[0] == str(self.helper):
                if command[-1] == '--dry-run':
                    self.assertFalse((self.home / '.bashrc').exists())
                elif command[-1] == '--apply':
                    self.assertTrue((self.home / '.bashrc').is_file())
                if command[-1] == fail_mode:
                    raise subprocess.CalledProcessError(7, command)
            elif command[0] == str(self.pi_helper):
                self.assertFalse((self.home / '.bashrc').exists())
                if command[-1] == fail_pi_mode:
                    raise subprocess.CalledProcessError(8, command)
            return SimpleNamespace(returncode=0)

        with mock.patch.dict(os.environ, {'HOME': str(self.home)}, clear=True), \
                mock.patch.object(self.engine.subprocess, 'run', side_effect=run), \
                mock.patch.object(self.engine.shutil, 'which', side_effect=lambda name: '/fake/' + name):
            result = self.engine.main(argv)
        return result, calls

    def test_cleanup_requires_explicit_flag(self):
        result, calls = self.invoke([])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [])

    def test_preview_only_calls_cleanup_preview_and_writes_nothing(self):
        before = snapshot(self.home)
        result, calls = self.invoke(['--cleanup', '--dry-run'])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [[str(self.helper), '--dry-run']])
        self.assertEqual(snapshot(self.home), before)

    def test_apply_is_after_file_transaction_and_has_prior_preview(self):
        result, calls = self.invoke(['--cleanup', '--packages'])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [[str(self.helper), '--dry-run'],
                                 ['sudo', 'pacman', '-S', '--needed', 'git', 'python'],
                                 [str(self.helper), '--apply']])

    def test_combined_pi_flow_finishes_before_cleanup_apply(self):
        result, calls = self.invoke(['--cleanup', '--packages', '--pi'])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [[str(self.helper), '--dry-run'],
                                 ['sudo', 'pacman', '-S', '--needed', 'git', 'python', 'mise', 'rust'],
                                 [str(self.pi_helper), '--preflight'],
                                 [str(self.pi_helper), '--install'],
                                 [str(self.helper), '--apply']])

    def test_failed_pi_bootstrap_does_not_run_cleanup_apply(self):
        before = snapshot(self.home)
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(['--cleanup', '--pi'], fail_pi_mode='--install')
        self.assertEqual(snapshot(self.home), before)

    def test_preview_failure_prevents_packages_and_file_changes(self):
        before = snapshot(self.home)
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(['--cleanup', '--packages'], fail_mode='--dry-run')
        self.assertEqual(snapshot(self.home), before)

    def test_cleanup_failure_retains_installed_config_and_propagates_failure(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(['--cleanup'], fail_mode='--apply')
        self.assertTrue((self.home / '.bashrc').is_file())
        self.assertEqual(self.read_journal()['status'], 'complete')

    def test_cleanup_rejects_home_staging(self):
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--cleanup', '--home', str(self.home)])
        self.assertEqual(snapshot(self.home), before)

    def test_cleanup_rejects_restore_mode(self):
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--cleanup', '--restore', str(self.home / 'not-a-record')])
        self.assertEqual(snapshot(self.home), before)

    def test_unsafe_cleanup_helper_is_refused_before_packages(self):
        self.helper.unlink()
        outside = put(self.base / 'outside-helper', b'not a trusted entrypoint\n')
        self.helper.symlink_to(outside)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.invoke(['--cleanup', '--packages'])
        self.assertEqual(snapshot(self.home), before)

    def test_conflicting_install_policy_refuses_before_install(self):
        for package in ('alacritty', 'signal-desktop', 'blueberry', 'spotify'):
            with self.subTest(package=package):
                put(self.repo / 'packages/apps.txt', (package + '\n').encode())
                before = snapshot(self.home)
                with self.assertRaises(self.engine.SetupError):
                    self.invoke(['--packages', '--apps', '--cleanup'])
                self.assertEqual(snapshot(self.home), before)

    def test_actual_install_manifests_do_not_reintroduce_selected_apps(self):
        names = set()
        for file in (REPO / 'packages').glob('*.txt'):
            names.update(line.split('#', 1)[0].strip() for line in file.read_text().splitlines())
        self.assertFalse(names & {'alacritty', 'signal-desktop', 'blueberry', 'spotify'})
