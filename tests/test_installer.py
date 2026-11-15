"""Focused engine tests using synthetic sources, never live dotfiles."""
import copy
import os
from pathlib import Path
import stat
from unittest import mock

from support import FixtureCase, HOOK, ROOT_FILES, STATE, put, snapshot


class PackagePlanTests(FixtureCase):
    def test_package_names_defaults_exclude_apps_and_opt_in_adds_them_once(self):
        put(self.repo / 'packages/desktop.txt', b'desktop-fixture\nshared-fixture # comment\n')
        put(self.repo / 'packages/development.txt', b'development-fixture\nshared-fixture\n')
        put(self.repo / 'packages/apps.txt', b'optional-fixture\nshared-fixture\n')
        before_home, before_repo = snapshot(self.home), snapshot(self.repo)
        default = ['desktop-fixture', 'shared-fixture', 'development-fixture']
        self.assertEqual(self.engine.package_names(), default)
        self.assertEqual(self.engine.package_names(include_apps=False), default)
        self.assertEqual(self.engine.package_names(include_apps=True), default + ['optional-fixture'])
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(self.repo), before_repo)


class PlanningTests(FixtureCase):
    def test_explicit_source_allowlist_and_generic_profile(self):
        put(self.repo / 'scripts/.local/bin/installed-vendor-tool', b'never install\n')
        put(self.repo / 'unlisted/.config/unlisted/config', b'not a managed root\n')
        put(self.repo / 'profiles/macmini-t2/udev/device.rules.example', b'not installed\n')
        before = snapshot(self.home)
        actions = self.engine.plan(self.home, 'generic', False)
        expected = set(ROOT_FILES.values()) | {
            '.config/hypr/monitors.conf', '.config/hypr/monitors.local.conf',
            '.local/bin/smart-close.sh', '.bashrc',
        }
        self.assertEqual({item['path'] for item in actions}, expected)
        mapping = {item['path']: item for item in actions}
        self.assertEqual(mapping['.config/hypr/monitors.conf']['source'],
                         str(self.repo / 'profiles/generic/monitors.conf'))
        self.assertEqual(mapping['.local/bin/smart-close.sh']['source'],
                         str(self.repo / 'bin/smart-close.sh'))
        self.assertEqual(snapshot(self.home), before)

    def test_backup_and_private_source_artifacts_are_excluded(self):
        ignored = [
            '.gitignore', 'config.bak', 'config.bak-20261112', 'config.bak.20261112',
            'config~', '__pycache__/cached.pyc', 'local.sh', 'local.conf',
            'auth.json', '.env', '.env.private', 'credentials', 'credentials.json',
            'token.json', 'config.local.toml', 'local.private.sh',
        ]
        for name in ignored:
            put(self.repo / 'bash/.config/bash' / name, b'synthetic private fixture\n')
        actions = self.engine.plan(self.home, 'generic', False)
        bash_paths = [a['path'] for a in actions if a['path'].startswith('.config/bash/')]
        self.assertEqual(bash_paths, ['.config/bash/custom.sh'])
        self.apply()
        for name in ignored:
            self.assertFalse(os.path.lexists(self.home / '.config/bash' / name), name)
        self.assertFalse((self.home / '.local/bin/installed-vendor-tool').exists())

    def test_private_cspell_config_and_local_dictionaries_are_excluded(self):
        private = ['cspell.local.json', 'cspell-dicts/local.txt',
                   'cspell-dicts/local-default.txt', 'cspell-dicts/local-project.txt']
        nvim_source = self.repo / 'nvim/.config/nvim'
        nvim_home = self.home / '.config/nvim'
        for relative in private:
            put(nvim_source / relative, b'synthetic source-only private words\n', 0o600)
            put(nvim_home / relative, b'synthetic home-only private words\r\n', 0o600)
        put(nvim_source / 'cspell.json', b'{"version": "0.2"}\n')
        shared = put(nvim_source / 'cspell-dicts/development.txt', b'public-fixture-word\n')
        before_private = {relative: snapshot(nvim_home / relative) for relative in private}

        actions = self.engine.plan(self.home, 'generic', True)
        destinations = {action['path'] for action in actions}
        for relative in private:
            self.assertNotIn(str(Path('.config/nvim') / relative), destinations)
        self.assertIn('.config/nvim/cspell.json', destinations)
        self.assertIn('.config/nvim/cspell-dicts/development.txt', destinations)
        folder = self.engine.install(self.home, actions)
        self.assert_link(nvim_home / 'cspell-dicts/development.txt', shared)
        for relative in private:
            self.assertEqual(snapshot(nvim_home / relative), before_private[relative])

        self.engine.restore(self.home, folder)
        for relative in private:
            self.assertEqual(snapshot(nvim_home / relative), before_private[relative])
        self.assertFalse(os.path.lexists(nvim_home / 'cspell-dicts/development.txt'))
        self.assertFalse(os.path.lexists(nvim_home / 'cspell.json'))

    def test_missing_required_source_prevents_all_writes(self):
        (self.repo / 'bin/smart-close.sh').unlink()
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.apply()
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())

    def test_source_symlink_is_rejected_without_writes(self):
        outside = put(self.base / 'outside-source', b'outside\n')
        source = self.repo / 'ghostty/.config/ghostty/config'
        source.unlink()
        source.symlink_to(outside)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.apply(backup=True)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(outside.read_bytes(), b'outside\n')

    def test_source_replaced_by_outside_symlink_after_plan_is_refused(self):
        original = put(self.home / '.config/ghostty/config', b'protected terminal\n', 0o600)
        actions = self.engine.plan(self.home, 'generic', True)
        # Corrupt a late source so preflight must validate all sources before apply.
        source = self.repo / 'bin/smart-close.sh'
        outside = put(self.base / 'outside source', b'never link outside fixture\n', 0o700)
        source.unlink()
        source.symlink_to(outside)
        before_config = snapshot(self.home / '.config')
        before_source, before_outside = snapshot(self.repo), snapshot(outside)

        with self.assertRaisesRegex(self.engine.SetupError, 'unsafe source'):
            self.engine.install(self.home, actions)
        self.assertEqual(snapshot(self.home / '.config'), before_config)
        self.assertEqual(snapshot(self.repo), before_source)
        self.assertEqual(snapshot(outside), before_outside)
        self.assertEqual(original.read_bytes(), b'protected terminal\n')
        self.assertFalse((self.home / '.bashrc').exists())
        for action in actions:
            self.assertFalse((self.home / action['path']).is_symlink(), action['path'])
        # The installer may create its lock, but must not start an install record.
        self.assertFalse(list((self.home / STATE).glob('*/manifest.json')))

    def test_source_root_directory_symlink_is_rejected(self):
        source = self.repo / 'ghostty/.config/ghostty'
        outside = self.base / 'source-directory'
        source.rename(outside)
        source.symlink_to(outside, target_is_directory=True)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.apply()
        self.assertEqual(snapshot(self.home), before)

    def test_matching_legacy_directory_symlink_is_left_untouched(self):
        legacy = self.home / '.config/ghostty'
        legacy.parent.mkdir()
        source = self.repo / 'ghostty/.config/ghostty'
        legacy.symlink_to(source, target_is_directory=True)
        original = legacy.lstat()
        before_source = snapshot(self.repo)
        actions = self.engine.plan(self.home, 'generic', False)
        self.assertNotIn('.config/ghostty/config', [a['path'] for a in actions])
        self.engine.install(self.home, actions)
        self.assertTrue(legacy.is_symlink())
        self.assertEqual(legacy.lstat().st_ino, original.st_ino)
        self.assertEqual(os.readlink(legacy), str(source))
        self.assertEqual(snapshot(self.repo), before_source)

    def test_legacy_directory_symlink_requiring_profile_write_is_refused(self):
        legacy = self.home / '.config/hypr'
        legacy.parent.mkdir()
        legacy.symlink_to(self.repo / 'hypr/.config/hypr', target_is_directory=True)
        before_home, before_source = snapshot(self.home), snapshot(self.repo)
        with self.assertRaises(self.engine.SetupError):
            self.apply(backup=True)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(self.repo), before_source)
        self.assertTrue(legacy.is_symlink())
        self.assertFalse((self.home / STATE).exists())

    def test_fully_matching_config_ancestor_symlink_requires_no_write(self):
        self.apply()
        outside = self.base / 'already installed config'
        (self.home / '.config').rename(outside)
        (self.home / '.config').symlink_to(outside, target_is_directory=True)
        before_home, before_outside = snapshot(self.home), snapshot(outside)
        self.assertEqual(self.engine.plan(self.home, 'generic', False), [])
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(outside), before_outside)

    def test_dangling_parent_directory_symlink_is_refused(self):
        (self.home / '.config').symlink_to(self.base / 'missing directory', target_is_directory=True)
        before = snapshot(self.home)
        with self.assertRaises(self.engine.SetupError):
            self.apply(backup=True)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.base / 'missing directory').exists())

    def test_invalid_utf8_bashrc_bytes_are_preserved_on_append_and_restore(self):
        original = b'# byte-preserving shell file\r\n# \xff\xfe\x80\nexport FIXTURE=1'
        bashrc = put(self.home / '.bashrc', original, 0o640)
        folder = self.apply(backup=True)
        self.assertTrue(bashrc.read_bytes().startswith(original))
        self.assertEqual(bashrc.read_bytes().splitlines().count(HOOK), 1)
        self.assertEqual(stat.S_IMODE(bashrc.stat().st_mode), 0o640)
        self.engine.restore(self.home, folder)
        self.assertEqual(bashrc.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(bashrc.stat().st_mode), 0o640)

    def test_parent_change_between_plan_and_install_does_not_follow_symlink(self):
        actions = self.engine.plan(self.home, 'generic', False)
        outside = self.base / 'outside-target'
        outside.mkdir()
        (self.home / '.config').symlink_to(outside, target_is_directory=True)
        before_outside = snapshot(outside)
        with self.assertRaises(self.engine.SetupError):
            self.engine.install(self.home, actions)
        self.assertEqual(snapshot(outside), before_outside)
        self.assertTrue((self.home / '.config').is_symlink())

    def test_existing_unmanaged_file_created_after_plan_is_not_overwritten(self):
        actions = self.engine.plan(self.home, 'generic', False)
        path = put(self.home / '.config/ghostty/config', b'created after plan\n', 0o600)
        with self.assertRaises(self.engine.SetupError):
            self.engine.install(self.home, actions)
        self.assertEqual(path.read_bytes(), b'created after plan\n')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse((self.home / '.bashrc').exists())


class ManifestSafetyTests(FixtureCase):
    def assert_restore_refused_without_writes(self, folder):
        before = snapshot(self.home)
        with self.assertRaises((self.engine.SetupError, ValueError, KeyError, TypeError)):
            self.engine.restore(self.home, folder)
        self.assertEqual(snapshot(self.home), before)

    def test_action_path_traversal_absolute_and_state_paths_are_refused(self):
        folder = self.apply()
        original = self.read_journal(folder)
        outside = put(self.base / 'must-not-be-touched', b'outside original\n')
        for path in ['../must-not-be-touched', str(outside),
                     '.config/../../must-not-be-touched', str(STATE / 'forged'), str(STATE)]:
            with self.subTest(path=path):
                journal = copy.deepcopy(original)
                # Corrupt a late action to check that earlier actions are not undone first.
                journal['actions'][-1]['path'] = path
                self.write_journal(journal, folder)
                self.assert_restore_refused_without_writes(folder)
                self.assertEqual(outside.read_bytes(), b'outside original\n')

    def test_corrupt_json_and_wrong_version_or_home_are_refused(self):
        folder = self.apply()
        original = self.read_journal(folder)
        (folder / 'manifest.json').write_text('{broken json')
        self.assert_restore_refused_without_writes(folder)
        for key, value in [('version', 999), ('home', str(self.base / 'foreign home'))]:
            with self.subTest(field=key):
                journal = copy.deepcopy(original)
                journal[key] = value
                self.write_journal(journal, folder)
                self.assert_restore_refused_without_writes(folder)

    def test_unsafe_created_directory_record_is_validated_before_restore(self):
        folder = self.apply()
        journal = self.read_journal(folder)
        journal['created_dirs'].append('../outside-directory')
        outside = self.base / 'outside-directory'
        outside.mkdir()
        self.write_journal(journal, folder)
        self.assert_restore_refused_without_writes(folder)
        self.assertTrue(outside.is_dir())

    def test_duplicate_action_in_corrupt_manifest_is_refused(self):
        folder = self.apply()
        journal = self.read_journal(folder)
        journal['actions'].append(copy.deepcopy(journal['actions'][0]))
        self.write_journal(journal, folder)
        self.assert_restore_refused_without_writes(folder)

    def test_symlinked_manifest_is_refused(self):
        folder = self.apply()
        outside = self.base / 'outside-manifest.json'
        (folder / 'manifest.json').rename(outside)
        (folder / 'manifest.json').symlink_to(outside)
        before_outside = outside.read_bytes()
        self.assert_restore_refused_without_writes(folder)
        self.assertEqual(outside.read_bytes(), before_outside)

    def test_symlinked_install_directory_is_refused(self):
        folder = self.apply()
        outside = self.base / 'moved-install'
        folder.rename(outside)
        folder.symlink_to(outside, target_is_directory=True)
        before_outside = snapshot(outside)
        self.assert_restore_refused_without_writes(folder)
        self.assertEqual(snapshot(outside), before_outside)

    def test_restore_directory_outside_state_is_refused(self):
        folder = self.apply()
        outside = self.base / 'not-a-state-install'
        outside.mkdir()
        put(outside / 'manifest.json', (folder / 'manifest.json').read_bytes())
        before = snapshot(outside)
        self.assert_restore_refused_without_writes(outside)
        self.assertEqual(snapshot(outside), before)

    def test_symlinked_backup_directory_is_refused(self):
        put(self.home / '.config/ghostty/config', b'protected original\n')
        folder = self.apply(backup=True)
        outside = self.base / 'moved-backups'
        (folder / 'backups').rename(outside)
        (folder / 'backups').symlink_to(outside, target_is_directory=True)
        before_outside = snapshot(outside)
        self.assert_restore_refused_without_writes(folder)
        self.assertEqual(snapshot(outside), before_outside)

    def test_missing_protected_backup_is_refused(self):
        put(self.home / '.config/ghostty/config', b'protected original\n')
        folder = self.apply(backup=True)
        journal = self.read_journal(folder)
        index = next(i for i, a in enumerate(journal['actions']) if a['path'] == '.config/ghostty/config')
        (folder / 'backups' / str(index)).unlink()
        self.assert_restore_refused_without_writes(folder)

    def test_modified_protected_backup_is_refused(self):
        put(self.home / '.config/ghostty/config', b'protected original\n', 0o600)
        folder = self.apply(backup=True)
        journal = self.read_journal(folder)
        index = next(i for i, a in enumerate(journal['actions']) if a['path'] == '.config/ghostty/config')
        (folder / 'backups' / str(index)).write_bytes(b'corrupt backup\n')
        self.assert_restore_refused_without_writes(folder)

    def test_state_directory_symlink_is_refused_before_installation(self):
        outside = self.base / 'outside-state'
        outside.mkdir()
        state = self.home / STATE
        state.parent.mkdir(parents=True)
        state.symlink_to(outside, target_is_directory=True)
        before_home, before_outside = snapshot(self.home), snapshot(outside)
        with self.assertRaises(self.engine.SetupError):
            self.apply()
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(outside), before_outside)


class RestoreRecoveryTests(FixtureCase):
    def assert_interrupted_restore_reconciles(self, dangling=False):
        original = self.home / '.config/ghostty/config'
        if dangling:
            original.parent.mkdir(parents=True)
            original.symlink_to('../missing original fixture')
        else:
            put(original, b'original terminal\x00\r\n', 0o640)
        before_original = snapshot(original)
        folder = self.apply(backup=True)
        journal = self.read_journal(folder)
        index, action = next((i, action) for i, action in enumerate(journal['actions'])
                             if action['path'] == '.config/ghostty/config')
        backup = folder / 'backups' / str(index)
        self.assertTrue(action['installed'])
        self.assertFalse(action['restored'])

        # Simulate interruption after the durable intent and backup rename, before
        # the final restored flag is saved. The original now occupies its old path.
        action['restore_started'] = True
        self.write_journal(journal, folder)
        original.unlink()
        os.replace(backup, original)
        self.assertFalse(os.path.lexists(backup))
        self.assertEqual(snapshot(original), before_original)
        self.assertEqual(self.engine.fingerprint(original), action['before'])

        before_preview = snapshot(self.home)
        self.engine.restore(self.home, folder, dry_run=True)
        self.assertEqual(snapshot(self.home), before_preview)
        self.assertFalse(self.read_journal(folder)['actions'][index]['restored'])

        self.engine.restore(self.home, folder)
        self.assertEqual(snapshot(original), before_original)
        restored = self.read_journal(folder)
        self.assertEqual(restored['status'], 'restored')
        self.assertTrue(restored['actions'][index]['restored'])
        self.assertTrue(all(action['restored'] for action in restored['actions']))
        self.assertFalse(os.path.lexists(self.home / '.config/hypr/hyprland.conf'))
        self.assertFalse((self.home / '.bashrc').exists())
        before_repeat = snapshot(self.home)
        self.engine.restore(self.home, folder)
        self.assertEqual(snapshot(self.home), before_repeat)

    def test_interrupted_restore_reconciles_original_file_already_moved_back(self):
        self.assert_interrupted_restore_reconciles()

    def test_interrupted_restore_reconciles_dangling_symlink_already_moved_back(self):
        self.assert_interrupted_restore_reconciles(dangling=True)


class AutomaticRollbackTests(FixtureCase):
    def test_failure_after_backup_rename_restores_original_file_and_modes(self):
        original = put(self.home / '.config/ghostty/config', b'original terminal\x00\n', 0o640)
        dangling = self.home / '.config/git/config'
        dangling.parent.mkdir(parents=True)
        dangling.symlink_to('../nonexistent-config')
        real_symlink_to = Path.symlink_to
        failed = False

        def fail_one_link(path, target, *args, **kwargs):
            nonlocal failed
            if path == original and not failed:
                failed = True
                raise OSError('synthetic failure after backup rename')
            return real_symlink_to(path, target, *args, **kwargs)

        with mock.patch.object(Path, 'symlink_to', autospec=True, side_effect=fail_one_link):
            with self.assertRaisesRegex(OSError, 'synthetic failure'):
                self.apply(backup=True)
        self.assertTrue(failed)
        self.assertTrue(original.exists(), self.output.getvalue())
        self.assertFalse(original.is_symlink())
        self.assertEqual(original.read_bytes(), b'original terminal\x00\n')
        self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o640)
        self.assertTrue(dangling.is_symlink())
        self.assertEqual(os.readlink(dangling), '../nonexistent-config')
        self.assertFalse((self.home / '.bashrc').exists())
        self.assertFalse(os.path.lexists(self.home / '.config/hypr/hyprland.conf'))
        self.assertEqual(self.read_journal()['status'], 'restored')

    def test_failure_before_hook_write_rolls_back_all_new_links_and_original_hook(self):
        original = put(self.home / '.bashrc', b'# shell original\r\nexport FIXTURE=1', 0o640)
        real_atomic_bytes = self.engine.atomic_bytes
        failed = False

        def fail_hook(path, data, *args, **kwargs):
            nonlocal failed
            if path == original and not failed:
                failed = True
                raise OSError('synthetic hook write failure')
            return real_atomic_bytes(path, data, *args, **kwargs)

        with mock.patch.object(self.engine, 'atomic_bytes', side_effect=fail_hook):
            with self.assertRaisesRegex(OSError, 'synthetic hook write failure'):
                self.apply(backup=True)
        self.assertTrue(failed)
        self.assertEqual(original.read_bytes(), b'# shell original\r\nexport FIXTURE=1')
        self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o640)
        for relative in ROOT_FILES.values():
            self.assertFalse(os.path.lexists(self.home / relative), relative)
        self.assertFalse(os.path.lexists(self.home / '.local/bin/smart-close.sh'))
        self.assertEqual(self.read_journal()['status'], 'restored')


if __name__ == '__main__':
    import unittest
    unittest.main()
