"""Terminal-start banner tests with private homes and an inert fastfetch."""
import errno
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tempfile
import unittest

from support import REPO, put


class FastfetchStartupTests(unittest.TestCase):
    def run_startup(self, *, tty=True, interactive=True, disabled=False,
                    failing=False, missing=False):
        with tempfile.TemporaryDirectory(prefix='fastfetch-startup-test-') as d:
            root = Path(d)
            home = root / 'home'
            home.mkdir()
            commands = root / 'bin'
            commands.mkdir()
            log = root / 'fastfetch-calls'
            if not missing:
                code = b'#!/bin/bash\nprintf "called\\n" >> "$FASTFETCH_TEST_LOG"\nprintf "FASTFETCH-TEST-BANNER\\n"\n'
                code += b'exit 2\n' if failing else b'exit 0\n'
                put(commands / 'fastfetch', code, 0o755)
            env = {'HOME': str(home), 'PATH': str(commands), 'TERM': 'xterm-256color',
                   'HISTFILE': '/dev/null', 'DOTFILES_DISABLE_ATUIN': '1',
                   'FASTFETCH_TEST_LOG': str(log)}
            if disabled:
                env['DOTFILES_DISABLE_FASTFETCH'] = '1'
            script = 'source "$1"; source "$1"; printf "SHELL-READY\\n"'
            args = [shutil.which('bash'), '--noprofile', '--norc',
                    '-ic' if interactive else '-c', script, 'startup-test',
                    str(REPO / 'bash/.config/bash/custom.sh')]
            if tty:
                master, slave = pty.openpty()
                try:
                    result = subprocess.run(args, env=env, stdout=slave,
                                            stderr=subprocess.PIPE, timeout=15)
                    os.close(slave)
                    slave = -1
                    data = bytearray()
                    while True:
                        try:
                            chunk = os.read(master, 4096)
                        except OSError as error:
                            if error.errno == errno.EIO:
                                break
                            raise
                        if not chunk:
                            break
                        data.extend(chunk)
                    output = data.decode()
                finally:
                    if slave >= 0:
                        os.close(slave)
                    os.close(master)
            else:
                result = subprocess.run(args, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=15)
                output = result.stdout.decode()
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn('SHELL-READY', output)
            calls = log.read_text().splitlines() if log.exists() else []
            return output, calls

    def test_new_interactive_terminal_runs_banner_once(self):
        output, calls = self.run_startup()
        self.assertEqual(output.count('FASTFETCH-TEST-BANNER'), 1)
        self.assertEqual(calls, ['called'])

    def test_interactive_redirected_output_stays_clean(self):
        output, calls = self.run_startup(tty=False)
        self.assertNotIn('FASTFETCH-TEST-BANNER', output)
        self.assertEqual(calls, [])

    def test_noninteractive_terminal_does_not_run_banner(self):
        output, calls = self.run_startup(interactive=False)
        self.assertNotIn('FASTFETCH-TEST-BANNER', output)
        self.assertEqual(calls, [])

    def test_local_opt_out(self):
        output, calls = self.run_startup(disabled=True)
        self.assertNotIn('FASTFETCH-TEST-BANNER', output)
        self.assertEqual(calls, [])

    def test_missing_binary_does_not_break_startup(self):
        output, calls = self.run_startup(missing=True)
        self.assertNotIn('FASTFETCH-TEST-BANNER', output)
        self.assertEqual(calls, [])

    def test_failed_banner_does_not_break_shell_or_retry_on_source(self):
        output, calls = self.run_startup(failing=True)
        self.assertEqual(output.count('FASTFETCH-TEST-BANNER'), 1)
        self.assertEqual(calls, ['called'])

    def test_package_is_declared_for_fresh_install(self):
        entries = {s.split('#', 1)[0].strip() for s in
                   (REPO / 'packages/desktop.txt').read_text().splitlines()}
        self.assertIn('fastfetch', entries)
