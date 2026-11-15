"""Regression cases reproduced during the independent installer review."""
from pathlib import Path
import shutil
import subprocess
from unittest import mock

from support import CliCase, FixtureCase, REPO, STATE, put, snapshot


class ReviewedSourceExclusions(FixtureCase):
    def test_private_and_generated_directory_contents_are_pruned(self):
        ignored = [
            'bash/.config/bash/local.sh.d/private.sh',
            'tmux/.config/tmux/plugins/vendor/runtime',
            'tmux/.config/tmux/runtime.sock',
            'nvim/.config/nvim/spell/en.utf-8.add',
            'nvim/.config/nvim/.luarc.json',
            'nvim/.config/nvim/tags',
            'nvim/.config/nvim/test.sh',
            'nvim/.config/nvim/nvim/generated',
            'nvim/.config/nvim/.pytest_cache/v/cache/nodeids',
            'nvim/.config/nvim/tools/generated.pyc',
            'nvim/.config/nvim/tools/generated.pyo',
            'nvim/.config/nvim/tools/generated.pyd',
            'nvim/.config/nvim/.coverage',
            'nvim/.config/nvim/.DS_Store',
            'nvim/.config/nvim/.setup-state/backups/private',
        ]
        for name in ignored:
            put(self.repo / name, b'fixture private or generated data\n')
        put(self.repo / 'nvim/.config/nvim/lazy-lock.json', b'{}\n')
        before = snapshot(self.home)
        actions = self.engine.plan(self.home, 'generic', False)
        sources = {item.get('source') for item in actions}
        for name in ignored:
            self.assertNotIn(str(self.repo / name), sources)
        self.assertIn(str(self.repo / 'nvim/.config/nvim/lazy-lock.json'), sources)
        self.assertEqual(snapshot(self.home), before)

    def test_ignored_directory_symlinks_are_pruned_before_validation(self):
        outside = self.base / 'private source outside repo'
        put(outside / 'private.sh', b'fixture private data\n')
        names = [
            'bash/.config/bash/local.sh.d',
            'tmux/.config/tmux/plugins',
            'nvim/.config/nvim/spell',
            'nvim/.config/nvim/.pytest_cache',
            'nvim/.config/nvim/.setup-state',
        ]
        for name in names:
            (self.repo / name).symlink_to(outside, target_is_directory=True)
        actions = self.engine.plan(self.home, 'generic', False)
        self.assertFalse(any('private.sh' in item.get('source', '') for item in actions))
        self.assertEqual((outside / 'private.sh').read_bytes(), b'fixture private data\n')

    def test_nonignored_source_directory_symlink_is_refused(self):
        outside = self.base / 'outside source'
        put(outside / 'config.lua', b'fixture\n')
        (self.repo / 'nvim/.config/nvim/lua').symlink_to(outside, target_is_directory=True)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.engine.plan(self.home, 'generic', True)
        self.assertEqual(snapshot(self.home), before)


class ReviewedPlanningRaces(FixtureCase):
    def assert_edit_during_plan_is_protected(self, relative, original=None):
        target = self.home / relative
        if original is not None:
            put(target, original)
        edited = b'# newly saved user edit, must remain active\n'
        original_items = self.engine.config_items
        expected = {}

        def edit_after_snapshot(*args, **kwargs):
            items = original_items(*args, **kwargs)
            put(target, edited)
            expected.update(snapshot(self.home))
            return items

        with mock.patch.object(self.engine, 'config_items', side_effect=edit_after_snapshot):
            with self.assertRaises(self.engine.SetupError):
                self.engine.plan(self.home, 'generic', True)
        self.assertEqual(target.read_bytes(), edited)
        self.assertEqual(snapshot(self.home), expected)
        self.assertFalse((self.home / STATE).exists())

    def test_bashrc_newer_edit_is_not_accepted_as_stale_content_baseline(self):
        self.assert_edit_during_plan_is_protected('.bashrc', b'# prior shell config\n')

    def test_bashrc_created_after_content_selection_is_not_replaced(self):
        self.assert_edit_during_plan_is_protected('.bashrc')

    def test_monitor_override_created_during_planning_stays_unmanaged(self):
        self.assert_edit_during_plan_is_protected('.config/hypr/monitors.local.conf')


class TpmAnnotatedTagRegression(CliCase):
    def test_install_checks_peeled_commit_not_annotated_tag_object(self):
        # Upstream's published v3.1.0 tag object is c628645d..., but HEAD after
        # checkout is its peeled 7bdb7ca3... commit. Git here is entirely inert.
        for name in ('mkdir', 'chmod', 'mktemp', 'mv', 'rm'):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (self.commands / name).symlink_to(executable)
        put(self.commands / 'git', b'''#!/bin/bash
set -euo pipefail
commit=7bdb7ca33c9cc6440a600202b50142f401b6fe21
if [[ $1 == clone ]]; then
  dest=${!#}
  mkdir -p "$dest/.git"
  printf '#!/bin/bash\\nexit 0\\n' > "$dest/tpm"
  chmod +x "$dest/tpm"
  exit 0
fi
[[ $1 == -C ]] || exit 90
dir=$2
shift 2
case "$1" in
  rev-parse)
    if [[ $2 == --show-toplevel ]]; then printf '%s\\n' "$dir"; else printf '%s\\n' "$commit"; fi ;;
  status) ;;
  -c) [[ $3 == checkout ]] || exit 91 ;;
  *) exit 92 ;;
esac
''', 0o755)
        result = subprocess.run([str(REPO / 'setup_tmux.sh'), '--install'],
                                cwd=self.base, env=self.env, capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / '.tmux/plugins/tpm/tpm').is_file())
        self.assertFalse(self.command_log.exists())
