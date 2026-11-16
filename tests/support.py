"""Isolated stdlib helpers. Never use the invoking user's home or command PATH."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

REPO = Path(__file__).resolve().parents[1]
STATE = Path('.local/state/dotfiles-omachy/installs')
ROOT_FILES = {
    'hypr': '.config/hypr/hyprland.conf',
    'ghostty': '.config/ghostty/config',
    'waybar': '.config/waybar/config.jsonc',
    'nvim': '.config/nvim/init.lua',
    'tmux': '.config/tmux/tmux.conf',
    'bash': '.config/bash/custom.sh',
    'git': '.config/git/config',
    'mise': '.config/mise/config.toml',
    'kitty': '.config/kitty/kitty.conf',
    'swayosd': '.config/swayosd/config.toml',
    'wireplumber': '.config/wireplumber/wireplumber.conf.d/bluetooth-a2dp-autoconnect.conf',
    'lazygit': '.config/lazygit/config.yml',
    'atuin': '.config/atuin/config.toml',
}
HOOK = b'[ -r "$HOME/.config/bash/custom.sh" ] && . "$HOME/.config/bash/custom.sh"'


def put(path, data=b'fixture\n', mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)
    return path


def snapshot(root):
    """Record contents, permissions, inode and mtime without following symlinks."""
    result = {}

    def visit(path):
        info = path.lstat()
        key = str(path.relative_to(root))
        details = (stat.S_IMODE(info.st_mode), info.st_ino, info.st_mtime_ns)
        if stat.S_ISLNK(info.st_mode):
            result[key] = ('link', details, os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            result[key] = ('dir', details)
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            result[key] = ('file', details, path.read_bytes())
    visit(root)
    return result


def load_installer():
    # Register before exec_module so this also works if the engine gains dataclasses.
    name = '_installer_test_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, REPO / 'lib/install.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return name, module


class IsolatedCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='dotfiles-tests-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home with spaces'
        self.home.mkdir()

    def install_dir(self):
        folders = list((self.home / STATE).glob('*/manifest.json'))
        self.assertEqual(len(folders), 1, 'Expected exactly one install record')
        return folders[0].parent

    def read_journal(self, folder=None):
        folder = folder or self.install_dir()
        return json.loads((folder / 'manifest.json').read_text())

    def assert_link(self, target, source):
        self.assertTrue(target.is_symlink(), f'Not a symlink: {target}')
        self.assertEqual(target.resolve(), source.resolve())


class CliCase(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.commands = self.base / 'commands'
        self.commands.mkdir()
        self.command_log = self.base / 'forbidden-commands'
        # No inherited PATH, credentials, display, shell startup or XDG settings.
        for name, executable in {
            'bash': shutil.which('bash'),
            'python3': sys.executable,
            'dirname': shutil.which('dirname'),
        }.items():
            if not executable:
                self.fail(f'Test prerequisite missing: {name}')
            (self.commands / name).symlink_to(executable)
        for name in ('sudo', 'pacman', 'yay', 'paru', 'systemctl', 'stow',
                     'curl', 'wget', 'git', 'apt', 'apt-get', 'dnf', 'brew',
                     'omarchy-pkg-install', 'omarchy-restart-waybar',
                     'hyprctl', 'mise', 'npm', 'pip', 'pip3', 'npx', 'node',
                     'prettier', 'cspell', 'codex', 'tmux', 'dkms', 'modinfo',
                     'uname', 'make', 'gcc', 'omarchy-theme-set', 'omarchy-theme-bg-set'):
            put(self.commands / name,
                b'#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$TEST_COMMAND_LOG"\nexit 97\n',
                0o755)
        self.env = {
            'HOME': str(self.home), 'PATH': str(self.commands),
            'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
            'XDG_CONFIG_HOME': str(self.home / '.config'),
            'XDG_STATE_HOME': str(self.home / '.local/state'),
            'XDG_DATA_HOME': str(self.home / '.local/share'),
            'XDG_CACHE_HOME': str(self.home / '.cache'),
            'TEST_COMMAND_LOG': str(self.command_log),
            'TMPDIR': str(self.base),
        }

    def cli(self, *args, ok=True, staged=True):
        command = [str(REPO / 'setup.sh')]
        if staged:
            command += ['--home', str(self.home)]
        command += [str(arg) for arg in args]
        return self.run_command(command, ok=ok)

    def helper_preview(self, name, *args):
        self.assertIn(name, ('setup_dev.sh', 'setup_tmux.sh', 'setup_theme.sh',
                             'setup_displaylink.sh', 'setup_thunderbold.sh'))
        self.assertIn(args, ((), ('--dry-run',), ('--help',)))
        if name in ('setup_displaylink.sh', 'setup_thunderbold.sh'):
            self.assertEqual(args, ('--help',), 'Never run hardware checks or actions')
        return self.run_command([str(self.commands / 'bash'), str(REPO / name), *args])

    def run_command(self, command, ok=True):
        result = subprocess.run(command, cwd=self.base, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=30)
        self.assertFalse(self.command_log.exists(),
                         'Installer attempted a package, service or network command')
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class FixtureCase(IsolatedCase):
    def setUp(self):
        super().setUp()
        name, self.engine = load_installer()
        self.addCleanup(sys.modules.pop, name, None)
        self.repo = self.base / 'synthetic repo'
        self.repo.mkdir()
        for root, relative in ROOT_FILES.items():
            put(self.repo / root / relative, f'# synthetic {root}\n'.encode())
        put(self.repo / 'hypr/.config/hypr/monitors.conf', b'# old hardware\n')
        for profile in ('generic', 'macmini-t2'):
            put(self.repo / 'profiles' / profile / 'monitors.conf',
                f'# synthetic {profile}\n'.encode())
        put(self.repo / 'bin/smart-close.sh', b'#!/bin/sh\nexit 0\n', 0o755)
        # Only REPO is reassigned. All writes stay inside this temporary directory.
        repo_patch = mock.patch.object(self.engine, 'REPO', self.repo)
        repo_patch.start()
        self.addCleanup(repo_patch.stop)
        command_patch = mock.patch.object(
            self.engine.subprocess, 'run',
            side_effect=AssertionError('Engine test attempted to run an external command'))
        command_patch.start()
        self.addCleanup(command_patch.stop)
        self.output = io.StringIO()
        redirects = contextlib.ExitStack()
        self.addCleanup(redirects.close)
        redirects.enter_context(contextlib.redirect_stdout(self.output))
        redirects.enter_context(contextlib.redirect_stderr(self.output))

    def apply(self, backup=False, machine='generic'):
        return self.engine.install(self.home,
                                   self.engine.plan(self.home, machine, backup))

    def write_journal(self, journal, folder=None):
        folder = folder or self.install_dir()
        (folder / 'manifest.json').write_text(json.dumps(journal))
        return folder
