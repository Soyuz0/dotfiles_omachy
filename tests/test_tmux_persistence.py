"""Persistence checks use temporary Git checkouts and private tmux with inert plugins."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'setup_tmux_persistence.sh'
CONFIG = ROOT / 'tmux/.config/tmux/tmux.conf'
GUARD = CONFIG.with_name('prepare-persistence-state.py')
PINS = {
    'tmux-resurrect': ('v4.0.0', 'e87d7d592cac97fa38c12395ebec042c154a1844'),
    'tmux-continuum': ('v3.1.0', '46e0e0023476018ddb4cc0d44783eede27e5a8ec'),
}

# No network and no remote code. Each simulated Git call is logged for assertions.
FAKE_GIT = r'''#!/usr/bin/python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
assert 'core.hooksPath=/dev/null' in args
assert 'core.fsmonitor=false' in args
assert 'submodule.recurse=false' in args
index = args.index('-C')
directory = pathlib.Path(args[index + 1])
args = args[index + 2:]
if args[0] == 'clone':
    assert '--no-checkout' in args and '--no-recurse-submodules' in args
    assert '--single-branch' in args and '--depth' in args
    name = args[-2].rsplit('/', 1)[1].removesuffix('.git')
    directory = pathlib.Path(args[-1])
    (directory / '.git').mkdir()
    rev = {'tmux-resurrect': 'e87d7d592cac97fa38c12395ebec042c154a1844',
           'tmux-continuum': '46e0e0023476018ddb4cc0d44783eede27e5a8ec'}[name]
    if os.environ.get('BAD_PIN') == name:
        rev = '0' * 40
    (directory / '.git/revision').write_text(rev)
    (directory / '.git/name').write_text(name)
    entry = directory / ('resurrect.tmux' if name == 'tmux-resurrect' else 'continuum.tmux')
    entry.write_text('#!/bin/sh\necho forbidden-runtime >> "$RUNTIME_LOG"\nexit 91\n')
    entry.chmod(0o755)
    sys.exit(0)
name = (directory / '.git/name').read_text()
if args[0] == 'config':
    if '--name-only' in args:
        print('core.bare\nremote.origin.url')
        if os.environ.get('UNSAFE_CONFIG'):
            print('filter.evil.clean')
    elif args[-1] == 'remote.origin.url':
        print('https://github.com/tmux-plugins/' + name + '.git')
    elif args[-1] == 'core.bare':
        print('false')
elif args[0] == 'rev-parse':
    if args[-1] == '--show-toplevel':
        print(directory)
    else:
        print((directory / '.git/revision').read_text())
elif args[0] == 'status':
    if (directory / 'dirty').exists():
        print('?? dirty')
elif args[0] == 'fsck' and os.environ.get('RACE_DEST') == name and directory.name.startswith('.'):
    destination = directory.parent / name
    destination.mkdir()
    (destination / 'sentinel').write_text('concurrent owner')
elif args[0] not in ('checkout', 'ls-tree', 'ls-files', 'fsck'):
    raise SystemExit('Unexpected fake Git call: ' + repr(args))
'''


class PersistenceFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tmux-persistence-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir(mode=0o700)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.git_log = self.base / 'git.log'
        self.runtime_log = self.base / 'runtime.log'
        self.env = dict(os.environ, HOME=str(self.home),
                        PATH=str(self.bin) + ':/usr/bin:/bin',
                        CALL_LOG=str(self.git_log), RUNTIME_LOG=str(self.runtime_log))
        self.env.pop('TMUX', None)
        self.env.pop('TMUX_TMPDIR', None)
        self.env.pop('XDG_CONFIG_HOME', None)
        self.put(self.bin / 'git', FAKE_GIT)
        self.put(self.bin / 'tmux', '#!/bin/sh\necho tmux-forbidden >> "$RUNTIME_LOG"\nexit 92\n')

    def put(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def helper(self, *args, success=True, env=None):
        result = subprocess.run(['/bin/bash', str(HELPER), *args],
                                env=env or self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertFalse(self.runtime_log.exists(), 'tmux or a plugin runtime was invoked')
        return result


class PersistenceTests(PersistenceFixture, unittest.TestCase):
    def test_preview_and_help_are_inert(self):
        for args in ((), ('--dry-run',), ('--help',)):
            result = self.helper(*args)
            self.assertFalse(self.git_log.exists())
            self.assertEqual(list(self.home.iterdir()), [])
            self.assertIn('No activation.' if args == ('--help',) else 'Plan only.', result.stdout)

    def test_bad_arguments_fail_without_actions(self):
        for args in (('--wat',), ('--dry-run', '--install'), ('--install', '--install')):
            self.helper(*args, success=False)
        self.assertFalse(self.git_log.exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_install_is_pinned_idempotent_and_does_not_touch_tpm(self):
        tpm = self.home / '.tmux/plugins/tpm/sentinel'
        self.put(tpm, 'existing TPM is not owned by this helper\n')
        self.helper('--install')
        before = self.git_log.read_text().count('"clone"')
        self.helper('--install')
        self.assertEqual(before, 2)
        self.assertEqual(self.git_log.read_text().count('"clone"'), 2)
        for name, (ref, rev) in PINS.items():
            dest = self.home / '.tmux/plugins' / name
            self.assertEqual((dest / '.git/revision').read_text(), rev)
            self.assertIn(ref, self.git_log.read_text())
        self.assertEqual((self.home / '.local/state/tmux-resurrect').stat().st_mode & 0o7777, 0o700)
        self.assertEqual(tpm.read_text(), 'existing TPM is not owned by this helper\n')
        self.assertEqual(sorted(p.name for p in tpm.parent.parent.iterdir()),
                         ['tmux-continuum', 'tmux-resurrect', 'tpm'])

    def test_existing_dirty_checkout_is_never_replaced_or_updated(self):
        self.helper('--install')
        destination = self.home / '.tmux/plugins/tmux-resurrect'
        (destination / 'dirty').write_text('preserve me')
        self.git_log.write_text('')
        self.helper('--install', success=False)
        self.assertEqual((destination / 'dirty').read_text(), 'preserve me')
        self.assertNotIn('"clone"', self.git_log.read_text())

    def test_wrong_head_and_unsafe_local_config_fail_closed(self):
        self.helper('--install')
        revfile = self.home / '.tmux/plugins/tmux-resurrect/.git/revision'
        revfile.write_text('0' * 40)
        self.helper('--install', success=False)
        self.assertEqual(revfile.read_text(), '0' * 40)
        revfile.write_text(PINS['tmux-resurrect'][1])
        self.git_log.write_text('')
        self.helper('--install', success=False, env=dict(self.env, UNSAFE_CONFIG='1'))
        self.assertNotIn('"status"', self.git_log.read_text())

    def test_wrong_fetched_pin_removes_only_its_staging(self):
        self.helper('--install', success=False, env=dict(self.env, BAD_PIN='tmux-resurrect'))
        self.assertEqual(list((self.home / '.tmux/plugins').iterdir()), [])

    def test_concurrent_destination_is_not_overwritten_or_merged(self):
        self.helper('--install', success=False, env=dict(self.env, RACE_DEST='tmux-resurrect'))
        plugins = self.home / '.tmux/plugins'
        self.assertEqual([p.name for p in plugins.iterdir()], ['tmux-resurrect'])
        destination = plugins / 'tmux-resurrect'
        self.assertEqual([p.name for p in destination.iterdir()], ['sentinel'])
        self.assertEqual((destination / 'sentinel').read_text(), 'concurrent owner')

    def test_symlink_destination_and_components_are_rejected(self):
        for relative in ('.tmux', '.tmux/plugins', '.tmux/plugins/tmux-resurrect'):
            with self.subTest(path=relative):
                path = self.home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                target = self.base / 'protected'
                target.mkdir(exist_ok=True)
                path.symlink_to(target, target_is_directory=True)
                self.helper('--install', success=False)
                self.assertEqual(list(target.iterdir()), [])
                self.assertTrue(path.is_symlink())
                path.unlink()
        self.assertFalse(self.git_log.exists())

    def test_writable_directory_and_git_metadata_symlinks_are_rejected(self):
        plugins = self.home / '.tmux/plugins'
        plugins.mkdir(parents=True)
        plugins.chmod(0o777)
        self.helper('--install', success=False)
        self.assertFalse(self.git_log.exists())
        plugins.chmod(0o700)
        self.helper('--install')
        directory = plugins / 'tmux-resurrect/.git'
        moved = self.base / 'moved-metadata'
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        self.helper('--install', success=False)
        self.assertTrue(directory.is_symlink())

    def test_config_declares_pinned_continuum_last_and_keeps_pi_includes_last(self):
        text = CONFIG.read_text()
        declarations = [line for line in text.splitlines() if line.startswith('set -g @plugin ')]
        self.assertEqual(declarations[-1], "set -g @plugin 'tmux-plugins/tmux-continuum#v3.1.0'")
        for name, (ref, rev) in PINS.items():
            self.assertIn(f"set -g @plugin 'tmux-plugins/{name}#{ref}'", declarations)
            self.assertIn(rev, text)
            self.assertIn(rev, HELPER.read_text())
        active = [line for line in text.splitlines() if line.strip() and not line.startswith('#')]
        self.assertEqual(active[-2:], ['source-file -q ~/.pi/scripts/tmux-pi-keys.conf',
                                      'source-file -q ~/.pi/scripts/tmux-pi-window-name.conf'])


class StateGuardTests(PersistenceFixture, unittest.TestCase):
    def guard(self, success=True, env=None):
        # Explicitly exercise the reported server umask without changing ours.
        result = subprocess.run(['/bin/sh', '-c', 'umask 022; exec "$1"', 'guard', str(GUARD)],
                                env=env or self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertFalse(self.git_log.exists())
        self.assertFalse(self.runtime_log.exists())
        return result

    def test_guard_creates_private_state_even_with_umask_022(self):
        self.guard()
        leaf = self.home / '.local/state/tmux-resurrect'
        self.assertEqual(leaf.stat().st_mode & 0o7777, 0o700)
        self.assertEqual(leaf.stat().st_uid, os.getuid())
        self.assertFalse((self.home / '.tmux').exists())
        self.guard()

    def test_guard_tightens_owned_leaf_only_and_does_not_migrate_snapshots(self):
        leaf = self.home / '.local/state/tmux-resurrect'
        leaf.mkdir(parents=True)
        leaf.chmod(0o777)
        old = self.home / '.tmux/resurrect/old-test-snapshot'
        self.put(old, 'old test data stays where it is')
        old.chmod(0o644)
        for path in (self.home / '.local', self.home / '.local/state', self.home / '.tmux'):
            path.chmod(0o755)
        self.guard()
        self.assertEqual(leaf.stat().st_mode & 0o7777, 0o700)
        self.assertEqual(list(leaf.iterdir()), [])
        self.assertEqual(old.read_text(), 'old test data stays where it is')
        self.assertEqual(old.stat().st_mode & 0o7777, 0o644)
        for path in (self.home / '.local', self.home / '.local/state', self.home / '.tmux'):
            self.assertEqual(path.stat().st_mode & 0o7777, 0o755)

    def test_guard_rejects_symlink_components_without_following_them(self):
        target = self.base / 'protected-state'
        target.mkdir()
        for relative in ('.local', '.local/state', '.local/state/tmux-resurrect'):
            with self.subTest(path=relative):
                path = self.home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(target, target_is_directory=True)
                self.guard(success=False)
                self.assertTrue(path.is_symlink())
                self.assertEqual(list(target.iterdir()), [])
                path.unlink()

    def test_guard_rejects_unsafe_parents_without_chmod(self):
        for relative in ('.', '.local', '.local/state'):
            with self.subTest(path=relative):
                parent = self.home / relative
                parent.mkdir(parents=True, exist_ok=True)
                parent.chmod(0o777)
                self.guard(success=False)
                self.assertEqual(parent.stat().st_mode & 0o7777, 0o777)
                self.assertFalse((self.home / '.local/state/tmux-resurrect').exists())
                parent.chmod(0o700)

    def test_guard_rejects_nonowner_parent_and_leaf(self):
        namespace = {'__name__': 'state_guard_test'}
        exec(compile(GUARD.read_text(), str(GUARD), 'exec'), namespace)
        leaf = self.home / '.local/state/tmux-resurrect'
        leaf.mkdir(parents=True)
        leaf.chmod(0o755)
        original_fstat = os.fstat
        for target in (self.home / '.local/state', leaf):
            inode = target.stat().st_ino

            def foreign_owner(fd):
                info = original_fstat(fd)
                values = list(info)
                if info.st_ino == inode:
                    values[4] = os.getuid() + 1
                return os.stat_result(values)

            with self.subTest(path=target), mock.patch.dict(os.environ, HOME=str(self.home)), \
                    mock.patch.object(namespace['os'], 'fstat', side_effect=foreign_owner):
                with self.assertRaisesRegex(RuntimeError, 'owned'):
                    namespace['prepare']()
            self.assertEqual(leaf.stat().st_mode & 0o7777, 0o755)

    def test_guard_does_not_enumerate_or_read_existing_snapshots(self):
        namespace = {'__name__': 'state_guard_test'}
        exec(compile(GUARD.read_text(), str(GUARD), 'exec'), namespace)
        leaf = self.home / '.local/state/tmux-resurrect'
        leaf.mkdir(parents=True)
        with mock.patch.dict(os.environ, HOME=str(self.home)), \
                mock.patch('os.listdir', side_effect=AssertionError('must not list snapshots')), \
                mock.patch('os.scandir', side_effect=AssertionError('must not scan snapshots')):
            namespace['prepare']()
        self.assertEqual(leaf.stat().st_mode & 0o7777, 0o700)

    def test_install_fails_before_git_when_state_guard_fails(self):
        (self.home / '.local').symlink_to(self.base, target_is_directory=True)
        self.helper('--install', success=False)
        self.assertFalse(self.git_log.exists())
        self.assertFalse((self.home / '.tmux').exists())


@unittest.skipUnless(shutil.which('git', path='/usr/bin:/bin'), 'git is not installed')
class RealGitIndexTests(PersistenceFixture, unittest.TestCase):
    def assert_hidden_change_rejected(self, flag, expected_tag):
        # Execute the real verifier functions, not a duplicate implementation.
        # Only main is skipped. This fixture has its own real Git index/objects.
        body = HELPER.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        namespace = {'__name__': 'persistence_verifier_test'}
        exec(compile(body, str(HELPER), 'exec'), namespace)
        real_git = shutil.which('git', path='/usr/bin:/bin')
        environment = {k: v for k, v in self.env.items() if not k.startswith('GIT_')}
        environment.update(PATH='/usr/bin:/bin', GIT_CONFIG_NOSYSTEM='1',
                           GIT_CONFIG_SYSTEM='/dev/null', GIT_CONFIG_GLOBAL='/dev/null')
        namespace['env'] = environment
        directory = self.base / 'real-checkout'
        directory.mkdir()

        def git(*args):
            command = [real_git, '-c', 'core.hooksPath=/dev/null', '-c', 'init.templateDir=',
                       '-c', 'user.name=Persistence test', '-c', 'user.email=test@example.invalid',
                       '-C', str(directory), *args]
            return subprocess.run(command, env=environment, capture_output=True, text=True,
                                  check=True, timeout=10).stdout.strip()

        git('init')
        entry = directory / 'resurrect.tmux'
        self.put(entry, '#!/bin/sh\nexit 91\n')
        git('add', 'resurrect.tmux')
        git('commit', '-m', 'inert local fixture')
        git('remote', 'add', 'origin', 'https://github.com/tmux-plugins/tmux-resurrect.git')
        git('tag', '-a', 'vfixture', '-m', 'fixture tag')
        revision = git('rev-parse', 'HEAD')
        git('checkout', '--detach', revision)
        namespace['verify'](directory, 'tmux-resurrect', 'vfixture', revision)
        git('update-index', flag, '--', 'resurrect.tmux')
        modified = '#!/bin/sh\n# modified bytes hidden from status\nexit 92\n'
        entry.write_text(modified)
        self.assertEqual(git('status', '--porcelain'), '')
        with self.assertRaisesRegex(RuntimeError, 'index flags can hide tracked changes'):
            namespace['verify'](directory, 'tmux-resurrect', 'vfixture', revision)
        self.assertTrue(git('ls-files', '-v').startswith(expected_tag + ' '))
        self.assertEqual(entry.read_text(), modified)
        self.assertFalse(self.runtime_log.exists())

    def test_real_assume_unchanged_hidden_modification_is_rejected(self):
        self.assert_hidden_change_rejected('--assume-unchanged', 'h')

    def test_real_skip_worktree_hidden_modification_is_rejected(self):
        self.assert_hidden_change_rejected('--skip-worktree', 'S')


@unittest.skipUnless(shutil.which('tmux', path='/usr/bin:/bin'), 'tmux is not installed')
class PrivateTmuxTests(PersistenceFixture, unittest.TestCase):
    def test_private_config_with_no_plugins_fallback_or_tpm(self):
        tmux = shutil.which('tmux', path='/usr/bin:/bin')
        config_root = self.home / '.config/tmux'
        config_root.mkdir(parents=True)
        shutil.copy2(GUARD, config_root / GUARD.name)
        socket = self.base / 'private.sock'
        command = [tmux, '-S', str(socket)]

        def run(*args, check=True):
            return subprocess.run(command + list(args), env=self.env, capture_output=True,
                                  text=True, check=check, timeout=10)

        try:
            run('-f', '/dev/null', 'new-session', '-d', '-s', 'inert-test', '/bin/sleep 120')
            for mode in ('missing', 'fallback', 'tpm'):
                with self.subTest(mode=mode):
                    if mode != 'missing':
                        plugins = self.home / '.tmux/plugins'
                        # These are authored stubs, NOT the upstream plugin scripts.
                        self.put(plugins / 'tmux-resurrect/resurrect.tmux',
                                 '#!/bin/sh\necho resurrect >> "$RUNTIME_LOG"\n'
                                 f'{tmux} bind-key S display-message inert-save\n'
                                 f'{tmux} bind-key U display-message inert-restore\n')
                        self.put(plugins / 'tmux-continuum/continuum.tmux',
                                 '#!/bin/sh\necho continuum >> "$RUNTIME_LOG"\n')
                    if mode == 'tpm':
                        self.put(plugins / 'tpm/tpm', '#!/bin/sh\necho tpm >> "$RUNTIME_LOG"\n'
                                 '"$HOME/.tmux/plugins/tmux-resurrect/resurrect.tmux"\n'
                                 '"$HOME/.tmux/plugins/tmux-continuum/continuum.tmux"\n')
                    run('source-file', str(CONFIG))
                    options = {'prefix': 'C-m', 'prefix2': 'C-a',
                               '@resurrect-dir': str(self.home / '.local/state/tmux-resurrect'),
                               '@resurrect-save': 'S',
                               '@resurrect-restore': 'U', '@resurrect-processes': 'false',
                               '@resurrect-never-overwrite': 'on',
                               '@resurrect-capture-pane-contents': 'off',
                               '@resurrect-save-shell-history': 'off',
                               '@resurrect-save-bash-history': 'off',
                               '@continuum-save-interval': '60', '@continuum-restore': 'off',
                               '@continuum-boot': 'off'}
                    self.assertEqual((self.home / '.local/state/tmux-resurrect').stat().st_mode & 0o7777, 0o700)
                    for option, expected in options.items():
                        self.assertEqual(run('show-option', '-gqv', option).stdout.strip(), expected)
                    for key, direction in (('h', '-L'), ('j', '-D'), ('k', '-U'), ('l', '-R')):
                        self.assertIn('select-pane ' + direction,
                                      run('list-keys', '-T', 'prefix', key).stdout)
                    if mode == 'missing':
                        self.assertFalse(self.runtime_log.exists())
                    else:
                        self.assertEqual(self.runtime_log.read_text().splitlines(),
                                         ['resurrect', 'continuum'] if mode == 'fallback' else
                                         ['tpm', 'resurrect', 'continuum'])
                        self.runtime_log.unlink()
                        self.assertIn('inert-save', run('list-keys', '-T', 'prefix', 'S').stdout)
                        self.assertIn('inert-restore', run('list-keys', '-T', 'prefix', 'U').stdout)
        finally:
            run('kill-server', check=False)

    def test_config_refuses_all_plugins_when_private_state_guard_fails(self):
        tmux = shutil.which('tmux', path='/usr/bin:/bin')
        config_root = self.home / '.config/tmux'
        config_root.mkdir(parents=True)
        installed_guard = config_root / GUARD.name
        plugins = self.home / '.tmux/plugins'
        self.put(plugins / 'tmux-resurrect/resurrect.tmux',
                 '#!/bin/sh\necho forbidden-resurrect >> "$RUNTIME_LOG"\n')
        self.put(plugins / 'tmux-continuum/continuum.tmux',
                 '#!/bin/sh\necho forbidden-continuum >> "$RUNTIME_LOG"\n')
        parent = self.home / '.local/state'
        parent.mkdir(parents=True)
        leaf = parent / 'tmux-resurrect'
        protected = self.base / 'protected-state'
        protected.mkdir()
        command = [tmux, '-S', str(self.base / 'failure.sock')]

        def run(*args):
            return subprocess.run(command + list(args), env=self.env, capture_output=True,
                                  text=True, timeout=10)

        try:
            started = run('-f', '/dev/null', 'new-session', '-d', '-s', 'guard-test', '/bin/sleep 120')
            self.assertEqual(started.returncode, 0, started.stderr)
            for loader in ('fallback', 'tpm'):
                if loader == 'tpm':
                    self.put(plugins / 'tpm/tpm', '#!/bin/sh\necho forbidden-tpm >> "$RUNTIME_LOG"\n')
                for failure in ('missing-guard', 'nonexecutable-guard', 'symlink-leaf', 'unsafe-parent'):
                    with self.subTest(loader=loader, failure=failure):
                        shutil.copy2(GUARD, installed_guard)
                        if failure == 'missing-guard':
                            installed_guard.unlink()
                        elif failure == 'nonexecutable-guard':
                            installed_guard.chmod(0o644)
                        elif failure == 'symlink-leaf':
                            leaf.symlink_to(protected, target_is_directory=True)
                        else:
                            parent.chmod(0o777)
                        run('source-file', str(CONFIG))
                        self.assertFalse(self.runtime_log.exists(), 'plugin loaded despite guard failure')
                        self.assertFalse((self.home / '.tmux/resurrect').exists())
                        self.assertEqual(run('show-option', '-gqv', '@resurrect-dir').stdout.strip(), str(leaf))
                        self.assertEqual(list(protected.iterdir()), [])
                        if leaf.is_symlink():
                            leaf.unlink()
                        parent.chmod(0o700)
                        if installed_guard.exists():
                            installed_guard.chmod(0o755)
        finally:
            run('kill-server')


if __name__ == '__main__':
    unittest.main()
