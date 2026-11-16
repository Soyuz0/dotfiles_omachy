"""Offline Pi restore tests. All provider executables and homes are synthetic."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pi_setup_under_test', REPO / 'lib/pi_setup.py')
pi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pi)

# One inert executable supplies the entire command boundary. It never delegates
# to real Git/npm/mise/cargo/Node/Pi and never uses the invoking user's home.
STUB = r'''
import hashlib, json, os, pathlib, shutil, subprocess, sys
P = pathlib.Path
name, args = P(sys.argv[0]).name, sys.argv[1:]
if name == 'mise':
    assert args[0] == '--cd'
    os.chdir(args[1])  # Model mise's actual cwd behavior, not subprocess cwd alone.
record = {'tool': name, 'args': args, 'cwd': os.getcwd(),
          'home': os.environ.get('HOME'), 'offline': os.environ.get('PI_OFFLINE'),
          'prefix': os.environ.get('NPM_CONFIG_PREFIX'),
          'prompt': os.environ.get('GIT_TERMINAL_PROMPT'),
          'ignore_scripts': os.environ.get('NPM_CONFIG_IGNORE_SCRIPTS'),
          'credential_env': any(k in os.environ for k in ('OPENAI_API_KEY', 'PI_GATEWAY_CODEX_HOME', 'NODE_OPTIONS'))}
with open(os.environ['PI_TEST_LOG'], 'a') as f: f.write(json.dumps(record) + '\n')
fail = os.environ.get('PI_TEST_FAIL', '')
if fail == name or (fail == 'clone' and name == 'git' and 'clone' in args):
    print('withheld synthetic diagnostic')
    sys.exit(81)
if name == 'mise':
    prefix = P(os.environ['HOME']) / '.local/share/mise/installs/node/26.12.1'
    if args[2] == 'install':
        (prefix / 'bin').mkdir(parents=True)
        shutil.copyfile(os.environ['PI_TEST_STUB'], prefix / 'bin/node')
        (prefix / 'bin/node').chmod(0o755)
        cli = prefix / 'lib/node_modules/npm/bin/npm-cli.js'
        cli.parent.mkdir(parents=True)
        cli.write_text('// inert fixture npm CLI\n')
        sys.exit(0)
    if args[2] == 'where': print(prefix); sys.exit(0)
    assert 'exec' in args and '--' in args
    command = args[args.index('--') + 1:]
    sys.exit(subprocess.run(command, env=os.environ).returncode)
if name == 'git':
    if args[:1] == ['-c']: args = args[2:]
    cwd = P.cwd()
    if args[:1] == ['-C']:
        cwd, args = P(args[1]), args[2:]
    if args[0] == 'clone':
        url, target = args[-2], P(args[-1])
        source = P(os.environ['PI_TEST_PRIVATE']) if 'pi-config' in url else P(os.environ['PI_TEST_SOURCES']) / target.name
        shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
        files = [str(p.relative_to(target)) for p in target.rglob('*') if p.is_file() or p.is_symlink()]
        (target / '.git').mkdir()
        (target / '.git/files.json').write_text(json.dumps(files))
        tree = {}
        for name in files:
            path = target / name
            data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
            mode = '120000' if path.is_symlink() else '100755' if path.stat().st_mode & 0o100 else '100644'
            oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            tree[name] = [mode, oid]
        (target / '.git/tree.json').write_text(json.dumps(tree))
        (target / '.git/head').write_text('a' * 40)
    elif args[0] == 'rev-parse': print((cwd / '.git/head').read_text())
    elif args[0] == 'checkout':
        (cwd / '.git/head').write_text(args[-1])
        if os.environ.get('PI_TEST_MUTATE') == cwd.name:
            # Simulate a smudge filter / concurrent edit with an unchanged HEAD.
            path = cwd / os.environ.get('PI_TEST_MUTATE_FILE', 'README.md')
            kind = os.environ.get('PI_TEST_MUTATION_KIND', 'bytes')
            if kind == 'mode': path.chmod(path.stat().st_mode ^ 0o100)
            elif kind == 'symlink': path.unlink(); path.symlink_to('different-target')
            else: path.write_bytes(path.read_bytes() + b'\nchanged after checkout\n')
            (cwd / '.git/index-flags').write_text('assume-unchanged skip-worktree')
    elif args[0] in ('ls-tree', 'ls-files'):
        if args[0] == 'ls-tree' and '--name-only' not in args:
            tree = json.loads((cwd / '.git/tree.json').read_text())
            print(''.join(mode + ' blob ' + oid + '\t' + name + '\0' for name, (mode, oid) in tree.items()), end='')
        else:
            print('\0'.join(json.loads((cwd / '.git/files.json').read_text())) + '\0', end='')
    elif args[0] == 'status': pass  # Index-hidden edits would falsely look clean.
    elif args[0] == 'config': pass
    else: raise AssertionError('Unexpected Git operation: ' + str(args))
    sys.exit(0)
if name == 'npm':
    if args[0] == 'install':
        assert '--global' in args and '--prefix' in args and '--ignore-scripts' in args
        prefix = P(args[args.index('--prefix') + 1])
        (prefix / 'bin').mkdir(parents=True)
        shutil.copyfile(os.environ['PI_TEST_STUB'], prefix / 'bin/pi')
        (prefix / 'bin/pi').chmod(0o755)
    elif args[0] == 'ci':
        assert '--ignore-scripts' in args
        assert (P.cwd() / 'package.json').is_file(), 'npm ci must run in the package directory'
        assert (P.cwd() / 'package-lock.json').is_file()
        (P.cwd() / 'node_modules').mkdir()
    elif args == ['run', 'check']:
        package = json.loads((P.cwd() / 'package.json').read_text())
        assert package['scripts']['check'], 'npm check must run in the Davis directory'
    else: raise AssertionError('Unexpected npm operation')
    sys.exit(0)
if name == 'pi':
    if args == ['--version']: print('1.5.2')
    else:
        assert args[0] == '--report-cwd'
        print(json.dumps({'cwd': os.getcwd(), 'args': args, 'path': os.environ['PATH']}))
    sys.exit(0)
if name == 'cargo':
    assert args == ['build', '--release', '--locked']
    assert (P.cwd() / 'Cargo.lock').is_file()
    path = P.cwd() / 'target/release/rtk'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'fixture RTK executable\n')
    path.chmod(0o755)
    sys.exit(0)
if name == 'node':
    if args == ['--version']: print('v26.12.1'); sys.exit(0)
    if P(args[0]).name == 'npm-cli.js':
        sys.exit(subprocess.run(['npm', *args[1:]], env=os.environ).returncode)
    if P(args[0]).name == 'pi':
        sys.exit(subprocess.run(args, env=os.environ).returncode)
    assert P(args[0]).name == 'offline-startup.mjs'
    assert P.cwd() == P(os.environ['HOME']) / 'empty-project'
    assert os.environ['PI_OFFLINE'] == '1'
    assert not record['credential_env']
    agent = P(os.environ['PI_CODING_AGENT_DIR'])
    assert str(agent).startswith(os.environ['HOME'] + '/')
    assert 'validation-' in str(agent) and not (agent / 'auth.json').exists()
    assert (agent / 'npm/node_modules').is_symlink()
    assert (agent / 'local-packages/davis/node_modules').is_symlink()
    settings = json.loads((agent / 'settings.json').read_text())
    for package in settings['packages']:
        if isinstance(package, dict) and 'dashboard' in package['source']:
            assert package['extensions'] == []
    assert '.prompt(' not in P(args[0]).read_text()
    assert 'session.bindExtensions' in P(args[0]).read_text()
    if fail != 'smoke-marker': print('PI_RESTORE_OFFLINE_OK')
    sys.exit(0)
raise AssertionError('Forbidden provider invocation: ' + name)
'''


def put(path, content='{}\n', mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)
    return path


def snapshot(root):
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        value = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
        result[str(path.relative_to(root))] = (info.st_mode, info.st_mtime_ns, info.st_ino, value)
    return result


class PiSetupCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pi-restore-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home with spaces'
        self.home.mkdir()
        self.commands = self.base / 'commands'
        self.commands.mkdir()
        self.log = self.base / 'commands.jsonl'
        self.private = self.base / 'synthetic-private'
        self.external = self.base / 'synthetic-sources'
        self.stub = put(self.base / 'stub', '#!' + sys.executable + '\n' + STUB, 0o755)
        for name in (*pi.TOOLS, 'node', 'npm', 'pi-forbidden', 'sudo', 'curl', 'systemctl', 'gh'):
            (self.commands / name).symlink_to(self.stub)
        for name in ('bash', 'dirname'):
            executable = shutil.which(name)
            self.assertTrue(executable)
            (self.commands / name).symlink_to(executable)
        (self.commands / 'python3').symlink_to(sys.executable)
        self.env = {
            'HOME': str(self.home), 'PATH': str(self.commands), 'LANG': 'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(self.base),
            'PI_TEST_PRIVATE': str(self.private), 'PI_TEST_SOURCES': str(self.external),
            'PI_TEST_LOG': str(self.log), 'PI_TEST_STUB': str(self.stub),
        }
        self.metadata = {
            'pi': '1.5.2', 'node': 'v26.12.1', 'sources': {
                name: {'url': url, 'path': '~/Projects/' + name, 'commit': hex(index + 11)[2:] * 40}
                for index, (name, url) in enumerate(pi.SOURCES.items())
            },
        }
        self.make_fixture()

    def make_fixture(self):
        self.save_metadata()
        put(self.private / 'README.md', 'Synthetic private fixture\n')
        settings = {
            'theme': 'tokyo-night', 'defaultProvider': 'openai', 'defaultModel': 'fixture-sol',
            'defaultThinkingLevel': 'high', 'packages': [
                '../../Projects/sol-pi', 'npm:@example/pi-tool@1.0.0',
                {'source': 'local-packages/davis', 'extensions': ['!extensions/summaries/index.ts', '!extensions/git-info/index.ts']},
                'local-packages/todo', 'npm:@blackbelt-technology/pi-agent-dashboard@0.11.0',
                '/home/fixture-original/.pi/agent/npm/node_modules/@blackbelt-technology/pi-dashboard-extension',
            ],
        }
        put(self.private / 'agent/settings.json', json.dumps(settings))
        put(self.private / 'agent/keybindings.json', '{"editor.newLine":["shift+enter"]}\n')
        put(self.private / 'agent/extensions/inert.ts', 'export default function () {}\n')
        put(self.private / 'agent/local-packages/todo/package.json')
        put(self.private / 'scripts/check-backup.py', 'print("Synthetic backup fixture passed")\n')
        for folder in pi.DEPENDENCIES:
            package = {'dependencies': {}}
            if folder == 'agent/npm':
                package['dependencies'] = {'@example/pi-tool': '1.0.0', '@blackbelt-technology/pi-agent-dashboard': '0.11.0'}
            if folder == 'agent/local-packages/davis':
                package['scripts'] = {'check': 'inert fixture check'}
            put(self.private / folder / 'package.json', json.dumps(package))
            put(self.private / folder / 'package-lock.json')
        for name in ('INTEGRATION.md', 'UPSTREAM.json'):
            put(self.private / 'agent/local-packages/davis' / name)
        link = self.private / 'agent/skills/omarchy'
        link.parent.mkdir(parents=True)
        link.symlink_to('/home/fixture-original/.local/share/omarchy/default/omarchy-skill')
        for name in pi.SOURCES:
            put(self.external / name / 'README.md', 'Synthetic external fixture\n')
        put(self.external / 'sol-pi/package.json')
        put(self.external / 'sol-pi/package-lock.json')
        put(self.external / 'rtk/Cargo.lock', '# fixture\n')

    def save_metadata(self):
        put(self.private / 'installed-versions.json', json.dumps(self.metadata))

    def records(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def install(self, fail=None, credentials=False, mutation=None, mutation_kind='bytes', mutation_file=None):
        env = dict(self.env)
        if fail:
            env['PI_TEST_FAIL'] = fail
        if mutation:
            env.update(PI_TEST_MUTATE=mutation, PI_TEST_MUTATION_KIND=mutation_kind)
            if mutation_file:
                env['PI_TEST_MUTATE_FILE'] = mutation_file
        if credentials:
            env.update(OPENAI_API_KEY='synthetic-do-not-propagate',
                       PI_GATEWAY_CODEX_HOME='/synthetic-do-not-propagate',
                       NODE_OPTIONS='--synthetic-do-not-propagate')
        # Only this synthetic fixture bypasses the root guard when CI runs as root.
        # File ownership checks still use the real UID. Production has no bypass.
        real_env = pi.Installer.env

        def fixture_env(installer, home=None):
            cleaned = real_env(installer, home)
            cleaned.update({key: value for key, value in env.items() if key.startswith('PI_TEST_')})
            return cleaned

        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(pi.os, 'geteuid', return_value=1000), \
                mock.patch.object(pi.Installer, 'env', fixture_env):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pi.Installer(self.home).install()
            return output.getvalue()

    def cli(self, *args):
        return subprocess.run([str(REPO / 'setup_pi.sh'), *args], env=self.env,
                              cwd=self.base, capture_output=True, text=True, timeout=20)

    def test_default_dry_run_and_help_execute_nothing_and_write_nothing(self):
        put(self.home / '.pi/auth.json', 'synthetic forbidden live credential file\n')
        before = snapshot(self.home)
        for args in ((), ('--dry-run',), ('--help',)):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(snapshot(self.home), before)
            self.assertEqual(self.records(), [])
        self.assertIn('No commands or providers', self.cli().stdout)

    def test_preview_can_print_staged_home_without_reading_it(self):
        staged = self.base / 'nonexistent staged home'
        result = self.cli('--dry-run', '--home', str(staged))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(staged / '.pi'), result.stdout)
        self.assertFalse(staged.exists())
        self.assertEqual(self.records(), [])

    def test_cli_rejects_mixed_modes_and_unknown_arguments(self):
        for args in (('--install', '--dry-run'), ('--preflight', '--install'), ('--repo', 'unsafe'), ('--force',)):
            result = self.cli(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.records(), [])

    def test_preflight_is_read_only_and_does_not_invoke_providers(self):
        before = snapshot(self.home)
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(pi.os, 'geteuid', return_value=1000):
            self.assertEqual(pi.main(['--preflight']), 0)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.records(), [])

    def test_preflight_rejects_root_and_staged_home(self):
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(pi.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(pi.RestoreError, 'normal user'):
                pi.preflight(self.home)
        other = self.base / 'other-home'
        other.mkdir()
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(pi.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(pi.RestoreError, 'must equal HOME'):
                pi.preflight(other)

    def test_all_existing_destinations_are_preserved_without_commands(self):
        paths = ('.pi', str(pi.STATE), str(pi.RUNTIME), '.local/bin/pi', '.local/bin/rtk',
                 'Projects/sol-pi', 'Projects/rtk', 'Projects/computer-use-linux')
        for relative in paths:
            with self.subTest(path=relative):
                target = self.home / relative
                target.mkdir(parents=True)
                put(target / 'unrelated', 'keep exact unrelated bytes\n')
                before = snapshot(self.home)
                with self.assertRaisesRegex(pi.RestoreError, 'existing destination'):
                    self.install()
                self.assertEqual(snapshot(self.home), before)
                self.assertEqual(self.records(), [])
                shutil.rmtree(target)

    def test_existing_file_symlink_and_dirty_pi_are_not_adopted(self):
        target = self.home / '.pi'
        for form in ('file', 'symlink', 'dirty-checkout', 'completed-owned'):
            with self.subTest(form=form):
                if form == 'file':
                    put(target, 'unrelated')
                elif form == 'symlink':
                    target.symlink_to(self.private)
                else:
                    put(target / '.git/config', 'synthetic dirty checkout')
                    put(target / 'README.md', 'unrelated dirty README')
                    if form == 'completed-owned':
                        put(self.home / pi.STATE / 'receipt.json', '{"status":"completed"}')
                before = snapshot(self.home)
                with self.assertRaisesRegex(pi.RestoreError, 'existing destination'):
                    self.install()
                self.assertEqual(snapshot(self.home), before)
                self.assertEqual(self.records(), [])
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()

    def test_symlink_parent_and_existing_pi_on_path_are_refused(self):
        local = self.home / '.local'
        local.symlink_to(self.base / 'outside')
        with self.assertRaisesRegex(pi.RestoreError, 'symlink'):
            self.install()
        local.unlink()
        (self.commands / 'pi').symlink_to(self.stub)
        with self.assertRaisesRegex(pi.RestoreError, 'already on PATH'):
            self.install()
        self.assertEqual(self.records(), [])

    def test_missing_prerequisites_do_not_invoke_commands(self):
        (self.commands / 'cargo').unlink()
        with self.assertRaisesRegex(pi.RestoreError, 'Missing prerequisites: cargo'):
            self.install()
        self.assertEqual(self.records(), [])
        self.assertFalse((self.home / pi.STATE).exists())

    def test_full_restore_uses_pins_ignore_scripts_and_isolated_startup(self):
        output = self.install(credentials=True)
        self.assertIn('Fresh Pi restore completed', output)
        receipt = json.loads((self.home / pi.STATE / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(receipt['commit'], 'a' * 40)
        self.assertEqual(receipt['pi'], '1.5.2')
        self.assertEqual(set(receipt['command_sha256']), {'pi', 'rtk'})
        self.assertEqual((self.home / pi.STATE / 'receipt.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / '.local/bin/rtk').read_bytes(), b'fixture RTK executable\n')
        wrapper = (self.home / '.local/bin/pi').read_text()
        self.assertIn('core:node@26.12.1', wrapper)
        self.assertIn(str(self.home / '.local/share/mise/installs/node/26.12.1/bin/node'), wrapper)
        self.assertNotIn('exec mise', wrapper)
        self.assertTrue(os.access(self.home / '.local/bin/pi', os.X_OK))
        records = self.records()
        git = [r for r in records if r['tool'] == 'git']
        self.assertTrue(all(r['prompt'] == '0' for r in git if 'clone' in r['args']))
        self.assertTrue(all(not any(word in r['args'] for word in ('pull', 'reset', 'push', 'add', 'commit')) for r in git))
        for name, source in self.metadata['sources'].items():
            self.assertEqual((self.home / 'Projects' / name / '.git/head').read_text(), source['commit'])
        npm = [r for r in records if r['tool'] == 'npm']
        cis = [r for r in npm if r['args'][0] == 'ci']
        self.assertEqual(len(cis), 4)
        self.assertEqual({r['cwd'] for r in cis},
                         {str(self.home / '.pi' / folder) for folder in pi.DEPENDENCIES}
                         | {str(self.home / 'Projects/sol-pi')})
        checks = [r for r in npm if r['args'] == ['run', 'check']]
        self.assertEqual([r['cwd'] for r in checks], [str(self.home / '.pi/agent/local-packages/davis')])
        mise = [r for r in records if r['tool'] == 'mise']
        self.assertEqual([r['args'][2] for r in mise], ['install', 'where'])
        self.assertTrue(all(r['cwd'] == str(self.home / pi.STATE) for r in mise))
        self.assertTrue(all('--ignore-scripts' in r['args'] for r in cis))
        for record in cis:
            if record['cwd'].startswith(str(self.home / '.pi')):
                self.assertIn('--legacy-peer-deps', record['args'])
            else:
                self.assertNotIn('--legacy-peer-deps', record['args'])
        for record in records:
            if record['tool'] != 'git':
                self.assertFalse(record['credential_env'])
                self.assertEqual(record['offline'], '1')
        self.assertTrue(any(r['tool'] == 'npm' and r['args'] == ['run', 'check'] for r in records))
        self.assertTrue(any(r['tool'] == 'cargo' and r['args'] == ['build', '--release', '--locked'] for r in records))
        smoke = [r for r in records if r['tool'] == 'node' and r['args'] and Path(r['args'][0]).name == 'offline-startup.mjs']
        self.assertEqual(len(smoke), 1)
        self.assertIn('validation-', smoke[0]['home'])
        self.assertNotEqual(smoke[0]['home'], str(self.home))
        self.assertFalse(any(r['tool'] in ('sudo', 'curl', 'systemctl', 'gh') for r in records))

    def test_portability_preserves_preferences_and_disables_optional_startup(self):
        target = self.home / '.local/share/omarchy/default/omarchy-skill'
        target.mkdir(parents=True)
        self.install()
        settings = json.loads((self.home / '.pi/agent/settings.json').read_text())
        self.assertEqual(settings['theme'], 'tokyo-night')
        self.assertEqual(settings['defaultThinkingLevel'], 'high')
        self.assertEqual(settings['defaultModel'], 'fixture-sol')
        davis = next(p for p in settings['packages'] if isinstance(p, dict) and p['source'] == 'local-packages/davis')
        self.assertEqual(davis['extensions'], ['!extensions/summaries/index.ts', '!extensions/git-info/index.ts'])
        dashboard = [p for p in settings['packages'] if isinstance(p, dict) and 'dashboard' in p['source']]
        self.assertEqual(len(dashboard), 2)
        self.assertTrue(all(p['extensions'] == [] for p in dashboard))
        self.assertTrue(all(not p['source'].startswith('/') for p in dashboard))
        self.assertIn('-extensions/computer-desktop/index.ts', settings['extensions'])
        link = self.home / '.pi/agent/skills/omarchy'
        self.assertTrue(link.is_symlink())
        self.assertFalse(os.readlink(link).startswith('/'))
        self.assertEqual(link.resolve(), target.resolve())
        self.assertEqual((self.home / '.pi/agent/keybindings.json').read_bytes(),
                         (self.private / 'agent/keybindings.json').read_bytes())

    def test_missing_omarchy_skill_is_omitted_only_from_new_clone(self):
        self.install()
        self.assertFalse((self.home / '.pi/agent/skills/omarchy').is_symlink())
        self.assertTrue((self.private / 'agent/skills/omarchy').is_symlink())

    def test_completed_restore_is_not_updated_or_reused(self):
        self.install()
        before, count = snapshot(self.home), len(self.records())
        with self.assertRaisesRegex(pi.RestoreError, 'existing destination'):
            self.install()
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(len(self.records()), count)

    def test_private_authentication_failure_is_clear_and_preserves_partial(self):
        with self.assertRaisesRegex(pi.RestoreError, 'Private GitHub clone failed'):
            self.install(fail='clone')
        receipt = json.loads((self.home / pi.STATE / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'incomplete')
        self.assertTrue((self.home / '.pi').is_dir())
        self.assertFalse((self.home / '.local/bin/pi').exists())
        self.assertFalse(any(r['tool'] in ('npm', 'mise', 'gh') for r in self.records()))

    def test_dependency_failure_never_publishes_pi_or_claims_completion(self):
        with self.assertRaises(pi.RestoreError):
            self.install(fail='npm')
        receipt = json.loads((self.home / pi.STATE / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'incomplete')
        self.assertFalse((self.home / '.local/bin/pi').exists())
        self.assertFalse((self.home / '.local/bin/rtk').exists())
        self.assertTrue((self.home / '.pi/installed-versions.json').exists())

    def test_missing_smoke_success_marker_blocks_publication(self):
        with self.assertRaisesRegex(pi.RestoreError, 'success marker'):
            self.install(fail='smoke-marker')
        self.assertFalse((self.home / '.local/bin/pi').exists())
        self.assertEqual(json.loads((self.home / pi.STATE / 'receipt.json').read_text())['status'], 'incomplete')

    def test_racing_state_reservation_never_overwrites_another_receipt(self):
        real_mkdir = Path.mkdir
        state = self.home / pi.STATE

        def racing(path, *args, **kwargs):
            if path == state and kwargs.get('exist_ok') is False:
                real_mkdir(path, parents=True)
                put(path / 'receipt.json', '{"owner":"another-transaction"}\n')
                raise FileExistsError('synthetic race')
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(Path, 'mkdir', racing):
            with self.assertRaises(FileExistsError):
                self.install()
        self.assertEqual((state / 'receipt.json').read_text(), '{"owner":"another-transaction"}\n')
        self.assertEqual(self.records(), [])

    def test_metadata_rejects_unpinned_or_redirected_inputs(self):
        original = json.loads(json.dumps(self.metadata))
        variants = [
            ('pi', 'latest'), ('pi', '1.6.0'), ('node', '26; false'),
            ('node', 'v20.0.0'), ('sources', {}),
        ]
        for field, value in variants:
            self.metadata = dict(original, **{field: value})
            self.save_metadata()
            with self.subTest(field=field, value=value), self.assertRaises(pi.RestoreError):
                pi.metadata(self.private)
        for field, value in [('url', 'https://example.invalid/other'), ('path', '~/../../outside'), ('commit', 'main')]:
            self.metadata = json.loads(json.dumps(original))
            self.metadata['sources']['sol-pi'][field] = value
            self.save_metadata()
            with self.subTest(field=field), self.assertRaises(pi.RestoreError):
                pi.metadata(self.private)

    def test_old_readme_version_never_overrides_metadata(self):
        put(self.private / 'README.md', 'Old example: pi-coding-agent@1.4.0\n')
        self.install()
        install = next(r for r in self.records() if r['tool'] == 'npm' and r['args'][0] == 'install')
        self.assertIn('@earendil-works/pi-coding-agent@1.5.2', install['args'])
        self.assertNotIn('@earendil-works/pi-coding-agent@1.4.0', install['args'])

    def test_unknown_absolute_home_paths_stop_before_dependency_install(self):
        put(self.private / 'agent/subagents.json', '{"path":"/home/somebody/unsafe"}')
        with self.assertRaisesRegex(pi.RestoreError, 'machine-specific home path'):
            self.install()
        self.assertFalse(any(r['tool'] in ('npm', 'mise') for r in self.records()))

    def test_backup_allowlist_rejects_runtime_and_unknown_package_sources(self):
        for path in ('agent/auth.json', 'agent/providers.json', 'agent/models-store.json',
                     'agent/sessions/s1.jsonl', 'agent/agents/resources/x/node_modules/x',
                     'agent/cache/data', 'dashboard/config.json', 'agent/local-packages/unreviewed/index.ts',
                     '../outside', '/absolute'):
            self.assertFalse(pi.allowed(path), path)
        self.assertTrue(pi.allowed('agent/models.json'))
        self.assertTrue(pi.allowed('agent/local-packages/davis/package-lock.json'))
        self.assertTrue(pi.allowed('agent/agents/resources/web-access/package-lock.json'))
        put(self.private / 'agent/auth.json', 'not a real credential')
        with self.assertRaisesRegex(pi.RestoreError, 'outside the reviewed backup allowlist'):
            self.install()
        self.assertFalse(any(r['tool'] in ('npm', 'mise') for r in self.records()))

    def test_external_resource_symlink_is_not_dereferenced_or_restored(self):
        outside = put(self.base / 'unrelated-resource', 'preserve unrelated bytes')
        (self.private / 'agent/extensions/external.ts').symlink_to(outside)
        before = outside.read_bytes()
        with self.assertRaisesRegex(pi.RestoreError, 'external resource symlink'):
            self.install()
        self.assertEqual(outside.read_bytes(), before)
        self.assertFalse(any(r['tool'] in ('npm', 'mise') for r in self.records()))

    def test_original_home_in_bundled_resources_requires_manual_review(self):
        put(self.private / 'agent/agents/resources/tool/config.json',
            '{"path":"/home/fixture-original/private-location"}')
        with self.assertRaisesRegex(pi.RestoreError, 'original-machine home path'):
            self.install()
        self.assertFalse(any(r['tool'] in ('npm', 'mise') for r in self.records()))

    def test_malformed_settings_and_new_package_sources_are_clear_failures(self):
        path = self.private / 'agent/settings.json'
        original = json.loads(path.read_text())
        for package in (123, {'source': 123}, 'git:https://example.invalid/repository',
                        'local-packages/unreviewed', '../../Projects/sol-pi/other'):
            settings = dict(original, packages=[package])
            path.write_text(json.dumps(settings))
            with self.subTest(package=package), self.assertRaises(pi.RestoreError):
                # Check the synthetic source directly, without writing to the target home.
                installer = pi.Installer(self.home)
                installer.root = self.private
                installer.home = self.base
                installer.check_inputs()
        self.assertEqual(self.records(), [])

    def test_raw_blob_identity_matches_a_known_git_object(self):
        path = put(self.home / 'hello.txt', 'hello\n')
        self.assertEqual(pi.Installer.file_identity(self.home, 'hello.txt'),
                         ('100644', 'ce013625030ba8dba906f756967f9e9ca394464a'))
        path.chmod(0o700)
        self.assertEqual(pi.Installer.file_identity(self.home, 'hello.txt'),
                         ('100755', 'ce013625030ba8dba906f756967f9e9ca394464a'))

    def test_mise_stub_applies_cd_and_npm_requires_local_manifest(self):
        package = self.base / 'package-directory'
        package.mkdir()
        put(package / 'package.json', '{"scripts":{"check":"inert"}}')
        result = subprocess.run(['mise', '--cd', str(package), 'exec', 'core:node@26.12.1',
                                 '--', 'npm', 'run', 'check'], cwd=self.base, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.records()[-1]['cwd'], str(package))
        (package / 'package.json').unlink()
        result = subprocess.run(['npm', 'ci', '--ignore-scripts'], cwd=package, env=self.env,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_installed_wrapper_preserves_project_cwd_without_running_mise(self):
        self.install()
        project = self.base / 'caller project with spaces'
        project.mkdir()
        put(project / '.mise.toml', '[hooks]\nenter = "must-not-run"\n')
        before = len(self.records())
        result = subprocess.run([str(self.home / '.local/bin/pi'), '--report-cwd', 'argument with spaces'],
                                cwd=project, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['cwd'], str(project))
        self.assertEqual(data['args'], ['--report-cwd', 'argument with spaces'])
        self.assertEqual(data['path'].split(os.pathsep)[0],
                         str(self.home / '.local/share/mise/installs/node/26.12.1/bin'))
        calls = self.records()[before:]
        self.assertEqual([call['tool'] for call in calls], ['node', 'pi'])
        self.assertTrue(all(call['cwd'] == str(project) for call in calls))

    def test_checkout_filter_byte_changes_are_rejected_with_unchanged_head(self):
        with self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
            self.install(mutation='sol-pi')
        path = self.home / 'Projects/sol-pi'
        self.assertEqual((path / '.git/head').read_text(), self.metadata['sources']['sol-pi']['commit'])
        self.assertIn(b'changed after checkout', (path / 'README.md').read_bytes())
        self.assertFalse(any(r['tool'] == 'npm' and r['cwd'] == str(path) for r in self.records()))
        self.assertFalse((self.home / '.local/bin/pi').exists())

    def test_private_checkout_is_verified_before_metadata_is_consumed(self):
        with mock.patch.object(pi, 'metadata', side_effect=AssertionError('metadata must not be read')):
            with self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
                self.install(mutation='.pi')
        self.assertEqual((self.home / '.pi/.git/head').read_text(), 'a' * 40)
        self.assertFalse(any(r['tool'] in ('npm', 'mise') for r in self.records()))

    def test_executable_and_symlink_target_changes_are_rejected(self):
        # Test the verifier directly against inert immutable Git tree records.
        installer = pi.Installer(self.home)
        installer.state.mkdir(parents=True)
        with mock.patch.dict(os.environ, self.env, clear=True):
            for kind, name in (('mode', 'README.md'), ('symlink', 'readme-link')):
                if kind == 'symlink':
                    (self.external / 'sol-pi/readme-link').symlink_to('README.md')
                target = self.home / 'Projects' / ('fixture-' + kind)
                # Use the known fixture source while keeping a distinct destination.
                source = self.external / target.name
                shutil.copytree(self.external / 'sol-pi', source, symlinks=True)
                commit = installer.clone('https://example.invalid/inert-source', target)
                path = target / name
                if kind == 'mode':
                    path.chmod(path.stat().st_mode ^ 0o100)
                else:
                    path.unlink()
                    path.symlink_to('different-target')
                with self.subTest(kind=kind), self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
                    installer.verify_checkout(target, commit)

    def test_index_flags_and_clean_status_cannot_hide_same_size_byte_changes(self):
        self.install()
        target = self.home / 'Projects/sol-pi'
        path = target / 'README.md'
        old = path.stat()
        path.write_bytes(b'X' + path.read_bytes()[1:])
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        put(target / '.git/index-flags', 'assume-unchanged skip-worktree')
        installer = pi.Installer(self.home)
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(installer.git('status', '--porcelain', cwd=target), '')
            self.assertEqual(installer.git('rev-parse', 'HEAD', cwd=target),
                             self.metadata['sources']['sol-pi']['commit'])
            with self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
                installer.verify_checkout(target, self.metadata['sources']['sol-pi']['commit'])
        self.assertEqual(path.read_bytes()[:1], b'X', 'Dirty bytes must not be reset.')

    def test_writer_after_initial_external_verification_is_caught_before_npm(self):
        original = pi.Installer.clone

        def clone_then_edit(installer, url, target, *args, **kwargs):
            commit = original(installer, url, target, *args, **kwargs)
            if target.name == 'sol-pi':
                with (target / 'README.md').open('ab') as handle:
                    handle.write(b'changed after initial verification')
            return commit

        with mock.patch.object(pi.Installer, 'clone', clone_then_edit):
            with self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
                self.install()
        target = self.home / 'Projects/sol-pi'
        self.assertFalse(any(r['tool'] == 'npm' and r['cwd'] == str(target) for r in self.records()))

    def test_private_writer_after_portability_is_caught_before_dependency_consumption(self):
        original = pi.Installer.node_run

        def install_then_edit(installer, *args, **kwargs):
            output = original(installer, *args, **kwargs)
            if args[:2] == ('npm', 'install'):
                with (installer.root / 'agent/npm/package.json').open('ab') as handle:
                    handle.write(b'\n ')
            return output

        with mock.patch.object(pi.Installer, 'node_run', install_then_edit):
            with self.assertRaisesRegex(pi.RestoreError, 'Pinned tracked bytes'):
                self.install()
        self.assertFalse(any(r['tool'] == 'npm' and r['args'][0] == 'ci' for r in self.records()))

    def test_no_model_smoke_has_real_error_and_network_guards(self):
        self.assertNotIn('.prompt(', pi.SMOKE_JS)
        for guard in ('PI_RESTORE_OFFLINE_OK', 'networkAttempts', 'globalThis.fetch = denied',
                      'session.bindExtensions', 'getExtensions().errors', 'SessionManager.inMemory',
                      'session.messages.length', 'session?.dispose()'):
            self.assertIn(guard, pi.SMOKE_JS)


if __name__ == '__main__':
    unittest.main()
