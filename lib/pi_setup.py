#!/usr/bin/env python3
"""Opt-in, fresh-home restore of the private Pi backup. Stdlib only.

No imports from, or inspection of, the invoking user's installed Pi. Preview and
preflight never execute a provider. Installation refuses all existing Pi homes;
this is deliberately not an updater, merger, or automatic repair tool.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

REPOSITORY = 'https://github.com/Soyuz0/pi-config.git'
STATE = Path('.local/state/dotfiles-omachy/pi-restore')
RUNTIME = Path('.local/share/dotfiles-omachy/pi-runtime')
SOURCES = {
    'sol-pi': 'https://github.com/NVlabs/SoL-Pi.git',
    'rtk': 'https://github.com/rtk-ai/rtk.git',
    'computer-use-linux': 'https://github.com/agent-sh/computer-use-linux.git',
}
DEPENDENCIES = (
    'agent/npm', 'agent/local-packages/davis',
    'agent/agents/resources/web-access',
)
TOOLS = ('git', 'mise', 'cargo', 'cc', 'pkg-config')
DENIED = {
    'node_modules', 'sessions', 'pi-subagents', 'davis-durable', 'backups',
    'cache', '.cache', '__pycache__', 'auth.json', 'providers.json',
    'models-store.json', '.env',
}
CONFIG = {
    'AGENTS.md', 'settings.json', 'models.json', 'keybindings.json',
    'sol-pi.json', 'subagents.json', 'davis-summary.json', 'pi-lsp.json',
    'pi-btw.json', 'pi-plan-mode.json', 'pi-statusline.json', 'pi-file-context.json',
}


class RestoreError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise RestoreError(message)


def exists(path):
    return path.exists() or path.is_symlink()


def stable_stat(info):
    # Reading files/links may update atime, which is not a source-byte change.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def safe_path(home, path):
    """Reject redirected or foreign-owned existing parents before any writes."""
    require(path.is_relative_to(home), 'A destination escaped the target home.')
    for current in (path, *path.parents):
        if current == home.parent:
            break
        if exists(current):
            info = current.lstat()
            require(not stat.S_ISLNK(info.st_mode), f'Refusing symlink: {current}')
            require(info.st_uid == os.getuid(), f'Refusing foreign-owned path: {current}')
            require(stat.S_ISDIR(info.st_mode), f'Expected a directory: {current}')


def preflight(home):
    require(os.geteuid() != 0, 'Run Pi setup as your normal user, never with sudo.')
    require(home.is_absolute() and home.is_dir(), 'HOME must be an existing absolute directory.')
    require(home == Path(os.environ.get('HOME', '')).absolute(),
            '--install/--preflight --home must equal HOME; staged-home installation is not supported.')
    # Do not resolve away a symlink before checking it.
    require(home == home.resolve(), 'The target home must not contain symlinks or .. components.')
    safe_path(home, home)
    for path in (home / '.pi', home / STATE, home / RUNTIME,
                 home / '.local/bin/pi', home / '.local/bin/rtk',
                 *(home / 'Projects' / name for name in SOURCES)):
        require(not exists(path), f'Refusing existing destination: {path}. Nothing was updated or reset.')
        safe_path(home, path.parent)
    require(shutil.which('pi') is None,
            'Pi is already on PATH. Refusing to replace or shadow a working installation.')
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    require(not missing, 'Missing prerequisites: ' + ', '.join(missing) +
            '. Install packages/pi.txt through the main installer first.')


def plan(home):
    print('Pi fresh-machine restore plan. No commands or providers are invoked in this mode.')
    print(f'Private repository: {REPOSITORY}')
    print(f'Clone destination: {home / ".pi"}')
    print('Use existing normal GitHub authentication; no token extraction or login.')
    print('Read installed-versions.json from the fetched commit, not the README\'s old version example.')
    print('Install its exact Node with mise core:node@VERSION, without mise use or global config changes.')
    print(f'Install exact Pi with npm install --global --prefix {home / RUNTIME} --ignore-scripts.')
    print('Restore npm, vendored Davis, and research web-access lockfiles with:')
    print('  npm ci --ignore-scripts --legacy-peer-deps')
    print('Run only Davis\'s reviewed offline npm run check, not its live backend tests.')
    print('Clone the recorded SoL-Pi and RTK commits into new ~/Projects directories;')
    print('also clone the optional recorded computer-use source review checkout.')
    print('SoL-Pi: npm ci --ignore-scripts. RTK: cargo build --release --locked.')
    print('Publish user-local pi and rtk only after an isolated no-model offline SDK startup passes.')
    print('Rebase recognized home paths, check the Omarchy skill target, and disable dashboard/computer-use startup.')
    print('No existing ~/.pi, external checkout, runtime prefix or command destination is adopted, even if empty.')
    print('No credentials, history, runtime state, optional Slack skills, services, gateways or dashboard are restored.')
    print('Prerequisites: git python mise rust base-devel pkgconf openssl. See packages/pi.txt.')
    print('Use --preflight for read-only local checks, or --install to authorize network and writes.')


def allowed(name):
    """Mirror the private backup's narrow path policy, before checking files out."""
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        return False
    if any(part in DENIED or part.startswith(('.env.', 'wf_')) for part in p.parts):
        return False
    low = p.name.lower()
    if any(word in low for word in ('credential', 'secret')) or low.endswith(
            ('.log', '.db', '.sqlite', '.pem', '.key', '.p12', '.pfx', '.private.json')):
        return False
    if name in {'.gitignore', 'README.md', 'AGENTS.md', 'installed-versions.json'}:
        return True
    if p.parts[0] == 'scripts':
        return len(p.parts) > 1
    if p.parts[0] != 'agent' or len(p.parts) < 2:
        return False
    if len(p.parts) == 2:
        return p.name in CONFIG
    if p.parts[1] == 'local-packages':
        return len(p.parts) > 3 and p.parts[2] in {'davis', 'todo'}
    if p.parts[1] == 'npm':
        return name in {'agent/npm/.gitignore', 'agent/npm/package.json', 'agent/npm/package-lock.json'}
    return p.parts[1] in {'extensions', 'skills', 'agents', 'prompts', 'themes'}


def regular(path):
    require(path.is_file() and not path.is_symlink(), f'Expected a regular file: {path.name}')
    return path


def read_json(path):
    try:
        return json.loads(regular(path).read_text())
    except (ValueError, UnicodeError):
        raise RestoreError(f'Invalid JSON in {path.name}.') from None


def metadata(root):
    data = read_json(root / 'installed-versions.json')
    require(isinstance(data, dict), 'Unsupported installed-versions.json schema.')
    for key in ('pi', 'node'):
        require(isinstance(data.get(key), str) and re.fullmatch(r'v?\d+\.\d+\.\d+', data[key]),
                f'Expected an exact {key} version in installed-versions.json.')
    require(data['pi'].startswith('1.5.'), 'This helper was reviewed for Pi 1.5.x. Review newer SDKs before restoring.')
    node_version = tuple(map(int, data['node'].lstrip('v').split('.')))
    require(node_version >= (22, 19, 0), 'Recorded Node is too old for Pi.')
    sources = data.get('sources')
    require(isinstance(sources, dict) and {'sol-pi', 'rtk'} <= sources.keys() <= SOURCES.keys(),
            'Unsupported source registry. Review new source entries before restoring.')
    for name, source in sources.items():
        require(isinstance(source, dict) and source.get('url') == SOURCES[name]
                and source.get('path') == '~/Projects/' + name
                and isinstance(source.get('commit'), str)
                and re.fullmatch(r'[0-9a-f]{40}', source['commit']),
                f'Unsafe or incomplete pinned source metadata for {name}.')
    return data


def atomic_json(path, data):
    temp = path.with_name(path.name + '.new')
    with temp.open('x', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        json.dump(data, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_home(value, old, new):
    if isinstance(value, str):
        return str(new) + value[len(str(old)):] if value.startswith(str(old) + '/') else value
    if isinstance(value, list):
        return [replace_home(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: replace_home(item, old, new) for key, item in value.items()}
    return value


def portable_settings(root, home):
    path = root / 'agent/settings.json'
    settings = read_json(path)
    require(isinstance(settings, dict) and isinstance(settings.get('packages'), list),
            'Expected a packages array in settings.json.')
    old_homes = set()
    link = root / 'agent/skills/omarchy'
    suffix = '/.local/share/omarchy/default/omarchy-skill'
    if link.is_symlink() and os.readlink(link).endswith(suffix):
        old_homes.add(os.readlink(link)[:-len(suffix)])
    dashboard_suffix = '/.pi/agent/npm/node_modules/@blackbelt-technology/pi-dashboard-extension'
    for entry in settings['packages']:
        source = entry if isinstance(entry, str) else entry.get('source', '') if isinstance(entry, dict) else ''
        if source.startswith('/') and source.endswith(dashboard_suffix):
            old_homes.add(source[:-len(dashboard_suffix)])
    require(len(old_homes) <= 1, 'Conflicting original home paths require manual review.')
    old = next(iter(old_homes), str(home))
    require(old.startswith('/') and old != '/', 'Invalid original home prefix.')
    settings = replace_home(settings, old, home)
    packages = []
    for entry in settings['packages']:
        source = entry if isinstance(entry, str) else entry.get('source', '') if isinstance(entry, dict) else ''
        require(isinstance(source, str) and source, 'Invalid package source in settings.json.')
        if source.startswith(str(home) + '/.pi/agent/'):
            source = source[len(str(home) + '/.pi/agent/'):]
            entry = dict(entry, source=source) if isinstance(entry, dict) else source
        require(not source.startswith(('/', 'git:', 'http:', 'https:', '~')),
                'Unrecognized absolute or remote package source needs manual review.')
        if 'pi-agent-dashboard' in source or 'pi-dashboard-extension' in source:
            entry = dict(entry) if isinstance(entry, dict) else {'source': source}
            entry.update(extensions=[], skills=[], prompts=[], themes=[])
        packages.append(entry)
    settings['packages'] = packages
    # Its reviewed binary installer is an explicit manual step, not a lifecycle hook.
    extensions = settings.setdefault('extensions', [])
    require(isinstance(extensions, list), 'Unsupported extensions setting.')
    disabled = '-extensions/computer-desktop/index.ts'
    if disabled not in extensions:
        extensions.append(disabled)
    atomic_json(path, settings)
    if link.is_symlink():
        require(os.readlink(link).endswith(suffix), 'Unknown Omarchy skill symlink requires manual review.')
        link.unlink()
        target = home / suffix.lstrip('/')
        if target.is_dir():
            link.symlink_to(os.path.relpath(target, link.parent))
    # Only known path fields are migrated. Never rewrite arbitrary extension code.
    # Refuse any other machine-specific absolute home path in runtime resources.
    home_pattern = re.compile(rb'/(?:home/[^/\s"\x27]+|Users/[^/\s"\x27]+)(?=/)')
    for path in (root / 'agent').rglob('*'):
        if 'node_modules' in path.parts or not path.is_file() or path.is_symlink():
            continue
        content = path.read_bytes()
        require(old == str(home) or (old + '/').encode() not in content,
                'An original-machine home path remains in restored agent resources; review privately.')
        if 'local-packages' in path.parts or 'resources' in path.parts:
            continue  # Other users' paths in vendored source/test fixtures are not configuration.
        require(not any(match.group().decode() != str(home) for match in home_pattern.finditer(content)),
                'An unrecognized machine-specific home path remains in agent resources; review privately.')
    return old


SMOKE_JS = r'''
// Restored non-secret resources only. Never prompt, authenticate, or start the CLI bridge.
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { syncBuiltinESMExports } from 'node:module';
let networkAttempts = 0;
const denied = () => { networkAttempts++; throw new Error('Offline restore check forbids networking'); };
globalThis.fetch = denied;
http.request = denied; http.get = denied; https.request = denied; https.get = denied;
net.connect = denied; net.createConnection = denied;
syncBuiltinESMExports();
const { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager } =
  await import(pathToFileURL(process.argv[2]).href);
const cwd = process.cwd();
const agentDir = process.env.PI_CODING_AGENT_DIR;
const settingsManager = SettingsManager.create(cwd, agentDir);
const loader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await loader.reload();
assert.equal(loader.getExtensions().errors.length, 0, 'Extension import errors');
assert.ok(loader.getExtensions().extensions.length > 0, 'No restored extensions loaded');
const model = { id: 'never-called', name: 'Offline restore fixture', provider: 'offline',
  api: 'openai-responses', baseUrl: 'https://example.invalid', reasoning: false,
  input: ['text'], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 100000, maxTokens: 1000 };
let session;
try {
  ({ session } = await createAgentSession({ cwd, agentDir, model, settingsManager,
    resourceLoader: loader, sessionManager: SessionManager.inMemory(cwd) }));
  const errors = [];
  session.extensionRunner.onError(error => errors.push(error));
  await session.bindExtensions({ mode: 'print' });
  assert.equal(errors.length, 0, 'Extension startup errors');
  assert.equal(networkAttempts, 0, 'Unexpected network activity');
  assert.equal(session.messages.length, 0, 'The restore check must not create a model turn');
} finally { session?.dispose(); }
console.log('PI_RESTORE_OFFLINE_OK');
'''


class Installer:
    def __init__(self, home):
        self.home = home
        self.root = home / '.pi'
        self.state = home / STATE
        self.runtime = home / RUNTIME
        self.node = None
        self.node_executable = None
        self.npm_cli = None
        self.private_overrides = {}
        self.owned_state = False
        self.journal = {'schema': 1, 'status': 'in_progress', 'repository': REPOSITORY,
                        'steps': [], 'manual': [
                            'Provider authentication and machine-specific model configuration',
                            'Dashboard and gateways/services/Tailscale/Homarr are not enabled',
                            'Computer-use binary and desktop dependencies require separate review/install',
                            'Optional language servers and native backend CLIs are not installed',
                            'Slack tools/skills and runtime/history are not restored',
                        ]}

    def env(self, home=None):
        home = home or self.home
        # Dependencies and offline checks never inherit provider/gateway credentials,
        # Node preload flags, session paths or orchestration worker markers.
        env = {key: value for key, value in os.environ.items() if key in {
            'PATH', 'LANG', 'LC_ALL', 'TERM', 'TMPDIR', 'HTTP_PROXY', 'HTTPS_PROXY',
            'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy',
        }}
        env.update(HOME=str(home), CI='1', GIT_TERMINAL_PROMPT='0',
                   PI_OFFLINE='1', PI_SKIP_VERSION_CHECK='1', PI_TELEMETRY='0',
                   NPM_CONFIG_PREFIX=str(self.runtime), NPM_CONFIG_IGNORE_SCRIPTS='true',
                   NPM_CONFIG_AUDIT='false', NPM_CONFIG_FUND='false',
                   NPM_CONFIG_UPDATE_NOTIFIER='false',
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), XDG_CACHE_HOME=str(home / '.cache'))
        return env

    def run(self, args, cwd=None, env=None, timeout=1800):
        try:
            result = subprocess.run(args, cwd=cwd or self.state, env=env or self.env(),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise RestoreError(f'{Path(args[0]).name} could not finish. No command output or credentials were logged.') from None
        require(result.returncode == 0,
                f'{Path(args[0]).name} failed. Review the recorded step locally; output is withheld to avoid credential leaks.')
        return result.stdout.decode('utf-8', errors='strict').strip()

    def git(self, *args, cwd=None):
        # Normal Git authentication, including SSH agent / Git credential helpers.
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
        for key in list(env):
            if key.startswith(('GIT_TRACE', 'GIT_CONFIG_', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE')):
                env.pop(key)
        env['GIT_OPTIONAL_LOCKS'] = '0'
        return self.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd, env=env)

    def step(self, name):
        print(name, flush=True)
        self.journal['steps'].append(name)
        atomic_json(self.state / 'receipt.json', self.journal)

    def clone(self, url, target, commit=None, private=False):
        require(not exists(target), f'Refusing existing checkout: {target}')
        safe_path(self.home, target.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(mode=0o700)
        try:
            self.git('clone', '--no-checkout', '--', url, str(target))
        except RestoreError:
            if private:
                raise RestoreError('Private GitHub clone failed. Confirm access with normal Git authentication. '
                                   'No login or token extraction was attempted; partial owned files were retained.') from None
            raise
        head = commit or self.git('rev-parse', 'HEAD', cwd=target)
        require(re.fullmatch(r'[0-9a-f]{40}', head), 'Git did not resolve a full commit identity.')
        if private:
            tree = self.git('ls-tree', '-r', '--name-only', '-z', head, cwd=target)
            require(all(allowed(name) for name in tree.split('\0') if name),
                    'The private checkout contains paths outside the reviewed backup allowlist.')
        self.git('checkout', '--detach', head, cwd=target)
        self.verify_checkout(target, head)
        return head

    @staticmethod
    def file_identity(root, name):
        """Read raw filesystem bytes, never Git's index, filters, or stat cache."""
        path = root / name
        for parent in path.parents:
            if parent == root:
                break
            require(parent.is_relative_to(root) and stat.S_ISDIR(parent.lstat().st_mode),
                    'A tracked file parent is no longer a directory.')
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode):
            data = os.fsencode(os.readlink(path))
            mode = '120000'
            digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        else:
            require(stat.S_ISREG(before.st_mode), 'A tracked file changed filesystem type.')
            mode = '100755' if before.st_mode & stat.S_IXUSR else '100644'
            require(mode == '100755' or not before.st_mode & 0o111,
                    'A non-executable tracked file gained executable permissions.')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                require(stable_stat(os.fstat(handle.fileno())) == stable_stat(before),
                        'A tracked file changed before verification.')
                digest = hashlib.sha1(b'blob ' + str(before.st_size).encode() + b'\0')
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
                require(stable_stat(os.fstat(handle.fileno())) == stable_stat(before),
                        'A tracked file changed during verification.')
            digest = digest.hexdigest()
        require(stable_stat(path.lstat()) == stable_stat(before), 'A tracked file changed during verification.')
        return mode, digest

    def verify_checkout(self, root, commit, overrides=None):
        """Compare the worktree with immutable commit blobs, ignoring index flags.

        Overrides are only the two intentional fresh-home portability edits.
        This is a before/after check, not a lock against another same-user writer.
        """
        require(stat.S_ISDIR(root.lstat().st_mode), 'The checkout root is no longer a real directory.')
        require(self.git('rev-parse', 'HEAD', cwd=root) == commit,
                'Pinned source commit verification failed.')
        tree = self.git('ls-tree', '-r', '-z', '--full-tree', commit, cwd=root)
        entries = {}
        for record in filter(None, tree.split('\0')):
            header, separator, name = record.partition('\t')
            fields = header.split(' ')
            require(separator and len(fields) == 3, 'Invalid pinned Git tree entry.')
            mode, kind, oid = fields
            path = PurePosixPath(name)
            require(not path.is_absolute() and path.parts and '..' not in path.parts
                    and '.git' not in path.parts and name not in entries,
                    'Unsafe or duplicate pinned Git tree path.')
            require(kind == 'blob' and mode in {'100644', '100755', '120000'}
                    and re.fullmatch(r'[0-9a-f]{40}', oid),
                    'Unsupported pinned tree mode or object. Submodules require manual review.')
            entries[name] = (mode, oid)
        require(entries, 'The pinned Git tree is empty.')
        for name, identity in (overrides or {}).items():
            require(name in {'agent/settings.json', 'agent/skills/omarchy'} and name in entries,
                    'Unexpected portability override in source verification.')
            if identity is None:
                entries.pop(name)
                require(not exists(root / name), 'An omitted portability link reappeared.')
            else:
                entries[name] = identity
        for name, identity in entries.items():
            require(self.file_identity(root, name) == identity,
                    'Pinned tracked bytes, symlink target or executable bit differ; '
                    'the checkout was retained without reset.')

    def verify_private(self):
        self.verify_checkout(self.root, self.journal['commit'], self.private_overrides)

    def resolve_node(self):
        # Resolve only from the owned receipt directory. Do not evaluate project
        # mise configuration before Pi has made its own project trust decision.
        prefix = Path(self.run(['mise', '--cd', str(self.state), 'where', self.node]))
        require(prefix.is_absolute(), 'mise did not return an absolute managed Node prefix.')
        prefix = prefix.resolve(strict=True)
        safe_path(self.home, prefix)
        self.node_executable = regular(prefix / 'bin/node').resolve(strict=True)
        self.npm_cli = regular(prefix / 'lib/node_modules/npm/bin/npm-cli.js').resolve(strict=True)
        require(self.node_executable.is_relative_to(prefix) and self.npm_cli.is_relative_to(prefix)
                and os.access(self.node_executable, os.X_OK), 'Unsafe managed Node installation paths.')
        require(all(path.stat().st_uid == os.getuid() and not path.stat().st_mode & 0o022
                    for path in (self.node_executable, self.npm_cli)),
                'Managed Node/npm files must be user-owned and not group/other-writable.')

    def node_run(self, *args, cwd=None, env=None, timeout=1800):
        require(self.node_executable is not None, 'Managed Node has not been resolved.')
        if args[0] == 'node':
            command = [str(self.node_executable), *args[1:]]
        elif args[0] == 'npm':
            command = [str(self.node_executable), str(self.npm_cli), *args[1:]]
        else:
            require(args[0] == str(self.runtime / 'bin/pi'), 'Unreviewed managed Node command.')
            command = [str(self.node_executable), *args]
        env = dict(env if env is not None else self.env())
        env['PATH'] = str(self.node_executable.parent) + os.pathsep + env.get('PATH', '')
        return self.run(command, cwd=cwd or self.state, env=env, timeout=timeout)

    def check_inputs(self):
        for path in self.root.rglob('*'):
            if '.git' in path.relative_to(self.root).parts or not path.is_symlink():
                continue
            if path == self.root / 'agent/skills/omarchy':
                continue  # Its known external target is checked without dereferencing below.
            target = os.readlink(path)
            require(not os.path.isabs(target) and (path.parent / target).resolve().is_relative_to(self.root),
                    'An external resource symlink requires manual review.')
        for folder in DEPENDENCIES:
            path = self.root / folder
            safe_path(self.home, path)
            regular(path / 'package.json')
            regular(path / 'package-lock.json')
        for name in ('INTEGRATION.md', 'UPSTREAM.json'):
            regular(self.root / 'agent/local-packages/davis' / name)
        require((self.root / 'agent/local-packages/todo/package.json').is_file(),
                'The vendored todo package is missing.')
        regular(self.root / 'scripts/check-backup.py')
        # Do not restore arbitrary sources whose unpinned startup could download or run code.
        settings = read_json(self.root / 'agent/settings.json')
        npm_manifest = read_json(self.root / 'agent/npm/package.json')
        require(isinstance(settings, dict) and isinstance(settings.get('packages'), list),
                'Expected a packages array in settings.json.')
        require(isinstance(npm_manifest, dict) and isinstance(npm_manifest.get('dependencies'), dict),
                'Expected locked managed npm dependencies.')
        dependencies = npm_manifest['dependencies']
        for entry in settings['packages']:
            source = entry if isinstance(entry, str) else entry.get('source', '') if isinstance(entry, dict) else ''
            require(isinstance(source, str) and source, 'Invalid package source in settings.json.')
            if source.startswith('npm:'):
                spec = source[4:]
                package = spec.rsplit('@', 1)[0] if '@' in spec[1:] else spec
                require(package in dependencies, 'A configured npm package is absent from the locked manifest.')
            elif source in {'local-packages/davis', 'local-packages/todo', '../../Projects/sol-pi'}:
                continue
            elif source.startswith('/') and source.endswith(
                    '/.pi/agent/npm/node_modules/@blackbelt-technology/pi-dashboard-extension'):
                continue
            else:
                raise RestoreError('An unreviewed package source requires manual restore.')

    def smoke(self):
        self.step('Validate restored resources in an isolated HOME, offline and without a model prompt')
        with tempfile.TemporaryDirectory(prefix='validation-', dir=self.state) as temp:
            fixture = Path(temp) / 'home'
            agent = fixture / '.pi/agent'
            cwd = fixture / 'empty-project'
            cwd.mkdir(parents=True)
            names = self.git('ls-files', '-z', cwd=self.root).split('\0')
            for name in filter(None, names):
                source, target = self.root / name, fixture / '.pi' / name
                # The intentionally omitted Omarchy link need not exist on this OS.
                if not exists(source):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_symlink():
                    target.symlink_to(os.readlink(source))
                else:
                    shutil.copyfile(source, target)
            settings = replace_home(read_json(agent / 'settings.json'), self.home, fixture)
            atomic_json(agent / 'settings.json', settings)
            for folder in DEPENDENCIES:
                (fixture / '.pi' / folder / 'node_modules').symlink_to(self.root / folder / 'node_modules')
            (fixture / 'Projects').mkdir()
            (fixture / 'Projects/sol-pi').symlink_to(self.home / 'Projects/sol-pi')
            # Do not dereference or import machine-local skill content in this fixture.
            omarchy = agent / 'skills/omarchy'
            if omarchy.is_symlink():
                omarchy.unlink()
            script = Path(temp) / 'offline-startup.mjs'
            script.write_text(SMOKE_JS)
            env = self.env(fixture)
            env['PI_CODING_AGENT_DIR'] = str(agent)
            sdk = self.runtime / 'lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js'
            output = self.node_run('node', str(script), str(sdk), cwd=cwd, env=env, timeout=120)
            require('PI_RESTORE_OFFLINE_OK' in output.splitlines(), 'The offline startup did not return its success marker.')

    def install(self):
        preflight(self.home)
        old_umask = os.umask(0o077)
        try:
            self.state.mkdir(parents=True, exist_ok=False)
            self.owned_state = True
            self.step('Clone the private backup into a new ~/.pi and pin the fetched commit')
            self.journal['commit'] = self.clone(REPOSITORY, self.root, private=True)
            data = metadata(self.root)
            self.check_inputs()
            self.step('Check the cloned backup policy and enable its local safety hook')
            self.run([sys.executable, str(self.root / 'scripts/check-backup.py')], cwd=self.root)
            self.run(['git', '-C', str(self.root), 'config', '--local', 'core.hooksPath', 'scripts/hooks'])
            self.step('Adapt only the new checkout for this home; leave optional services disabled')
            self.verify_private()
            portable_settings(self.root, self.home)
            for name in ('agent/settings.json', 'agent/skills/omarchy'):
                self.private_overrides[name] = self.file_identity(self.root, name) if exists(self.root / name) else None
            self.verify_private()
            self.node = 'core:node@' + data['node'].lstrip('v')
            self.journal.update(pi=data['pi'], node=data['node'], sources=data['sources'])
            self.step('Install the recorded Node and Pi in a separate user-owned runtime prefix')
            self.run(['mise', '--cd', str(self.state), 'install', self.node])
            self.resolve_node()
            require(self.node_run('node', '--version').lstrip('v') == data['node'].lstrip('v'),
                    'The selected Node does not match installed-versions.json.')
            self.runtime.mkdir(parents=True, exist_ok=False)
            self.node_run('npm', 'install', '--global', '--prefix', str(self.runtime), '--ignore-scripts',
                          '--no-audit', '--no-fund', '@earendil-works/pi-coding-agent@' + data['pi'])
            require(self.node_run(str(self.runtime / 'bin/pi'), '--version') == data['pi'],
                    'The installed Pi version does not match installed-versions.json.')
            for folder in DEPENDENCIES:
                self.step('Restore locked dependencies in ' + folder)
                self.verify_private()
                self.node_run('npm', 'ci', '--ignore-scripts', '--legacy-peer-deps', cwd=self.root / folder)
                self.verify_private()
            self.step('Run the vendored Davis offline typecheck and tests')
            self.verify_private()
            self.node_run('npm', 'run', 'check', cwd=self.root / 'agent/local-packages/davis')
            self.verify_private()
            for name, source in data['sources'].items():
                self.step('Restore pinned external source ' + name)
                path = self.home / 'Projects' / name
                self.clone(source['url'], path, source['commit'])
                if name == 'sol-pi':
                    self.verify_checkout(path, source['commit'])
                    regular(path / 'package-lock.json')
                    self.node_run('npm', 'ci', '--ignore-scripts', cwd=path)
                elif name == 'rtk':
                    self.verify_checkout(path, source['commit'])
                    regular(path / 'Cargo.lock')
                    self.run(['cargo', 'build', '--release', '--locked'], cwd=path, timeout=3600)
                self.verify_checkout(path, source['commit'])
            self.verify_private()
            self.smoke()
            self.verify_private()
            for name, source in data['sources'].items():
                self.verify_checkout(self.home / 'Projects' / name, source['commit'])
            self.step('Publish new user-local commands without replacing existing files')
            bindir = self.home / '.local/bin'
            safe_path(self.home, bindir)
            bindir.mkdir(parents=True, exist_ok=True)
            binary = regular(self.home / 'Projects/rtk/target/release/rtk')
            with (bindir / 'rtk').open('xb') as target, binary.open('rb') as source:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            (bindir / 'rtk').chmod(0o755)
            wrapper = ('#!/usr/bin/env bash\nset -euo pipefail\n'
                       '# Recorded managed ' + self.node + '; preserve the caller project directory.\n'
                       'export NPM_CONFIG_PREFIX="$HOME/' + str(RUNTIME) + '"\n'
                       'export PATH=' + shlex.quote(str(self.node_executable.parent)) + ':"$PATH"\n'
                       'exec ' + shlex.quote(str(self.node_executable)) +
                       ' "$NPM_CONFIG_PREFIX/bin/pi" "$@"\n')
            with (bindir / 'pi').open('x') as target:
                target.write(wrapper)
                target.flush()
                os.fsync(target.fileno())
            (bindir / 'pi').chmod(0o755)
            require(hashlib.sha256(binary.read_bytes()).digest() ==
                    hashlib.sha256((bindir / 'rtk').read_bytes()).digest(), 'RTK copy verification failed.')
            self.journal['command_sha256'] = {
                name: hashlib.sha256((bindir / name).read_bytes()).hexdigest() for name in ('pi', 'rtk')
            }
            self.journal['status'] = 'completed'
            atomic_json(self.state / 'receipt.json', self.journal)
            print('Fresh Pi restore completed. Put ~/.local/bin on PATH. No running Pi was reloaded.')
            print('The restored checkout has intentional local portability/safety edits. Review before a future sync.')
            print('Read docs/pi-setup.md for the integrations deliberately left manual.')
        except BaseException:
            if self.owned_state:
                self.journal['status'] = 'incomplete'
                atomic_json(self.state / 'receipt.json', self.journal)
            raise
        finally:
            os.umask(old_umask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Print a plan; no commands, writes or network. This is the default.')
    mode.add_argument('--preflight', action='store_true', help='Read-only local path/tool checks; no commands or GitHub check.')
    mode.add_argument('--install', action='store_true', help='Authorize the fresh restore, network and user-owned writes.')
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('HOME', '')),
                        help='Target home. Install/preflight require this to equal HOME.')
    args = parser.parse_args(argv)
    try:
        home = args.home.absolute()
        if args.install:
            Installer(home).install()
        elif args.preflight:
            preflight(home)
            print('Local Pi preflight passed. Private GitHub access and fetched metadata are not checked until --install.')
        else:
            plan(home)
    except (RestoreError, OSError, UnicodeError) as error:
        print('setup_pi: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
