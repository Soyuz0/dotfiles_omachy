"""Selected editor, LazyGit and local-only Atuin additions. No live startup."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import uuid

from support import REPO, put


class DesktopConfigTests(unittest.TestCase):
    def test_atuin_defaults_are_local_only(self):
        data = tomllib.loads((REPO / 'atuin/.config/atuin/config.toml').read_text())
        self.assertFalse(data['auto_sync'])
        self.assertFalse(data['update_check'])
        self.assertTrue(data['secrets_filter'])
        self.assertTrue(data['enter_accept'])
        for section in ('ai', 'pty_proxy', 'daemon'):
            self.assertFalse(data[section]['enabled'])
        self.assertFalse(data['sync']['records'])
        self.assertNotIn('session_path', data)
        self.assertNotIn('key_path', data)

    def test_packages_and_managed_roots_include_both_tools(self):
        entries = {s.split('#', 1)[0].strip() for s in
                   (REPO / 'packages/development.txt').read_text().splitlines()}
        self.assertTrue({'lazygit', 'atuin'} <= entries)
        code = (REPO / 'lib/install.py').read_text()
        for path in ('lazygit/.config/lazygit', 'atuin/.config/atuin'):
            self.assertIn('"' + path + '"', code)

    def test_lazygit_preserves_requested_preferences(self):
        code = (REPO / 'lazygit/.config/lazygit/config.yml').read_text()
        for line in ('  showIcons: true', '  nerdFontsVersion: "3"',
                     '  autoFetch: true', '  autoRefresh: true', '  editPreset: nvim'):
            self.assertIn(line, code)
        self.assertIn('"#7aa2f7"', code)

    def test_lsp_restart_and_explicit_discard_mappings(self):
        code = (REPO / 'nvim/.config/nvim/init.lua').read_text()
        for key, command in (('a', 'LspRestart'), ('v', 'e!')):
            matching = [line for line in code.splitlines()
                        if line.startswith("vim.keymap.set('n', '<leader>" + key + "',")]
            self.assertEqual(len(matching), 1)
            self.assertIn("'<cmd>" + command + "<CR>'", matching[0])
        self.assertIn('discard', matching[0].lower())

    @unittest.skipUnless(shutil.which('nvim'), 'Neovim executable is unavailable')
    def test_explicit_reload_mapping_discards_only_temporary_buffer_edits(self):
        with tempfile.TemporaryDirectory(prefix='nvim-selected-map-test-') as d:
            home = Path(d)
            file = put(home / 'test file.txt', b'original on disk\n')
            code = (REPO / 'nvim/.config/nvim/init.lua').read_text()
            mappings = [line for line in code.splitlines()
                        if line.startswith(("vim.keymap.set('n', '<leader>a',",
                                            "vim.keymap.set('n', '<leader>v',"))]
            script = 'vim.g.mapleader = " "\n' + '\n'.join(mappings) + '\n'
            script += '''
vim.cmd('edit ' .. vim.fn.fnameescape(FILE))
vim.api.nvim_buf_set_lines(0, 0, -1, false, {'unsaved edit'})
assert(vim.bo.modified)
local keys = vim.api.nvim_replace_termcodes('<Space>v', true, false, true)
vim.api.nvim_feedkeys(keys, 'x', false)
assert(vim.api.nvim_buf_get_lines(0, 0, -1, false)[1] == 'original on disk')
assert(not vim.bo.modified)
assert(vim.fn.maparg(' a', 'n'):find('LspRestart', 1, true))
vim.cmd('qa!')
'''.replace('FILE', json.dumps(str(file)))
            lua = put(home / 'test.lua', script.encode())
            env = {'HOME': str(home), 'PATH': '/usr/bin:/bin',
                   'XDG_CONFIG_HOME': str(home / '.config'),
                   'XDG_DATA_HOME': str(home / '.local/share'),
                   'XDG_STATE_HOME': str(home / '.local/state'),
                   'XDG_CACHE_HOME': str(home / '.cache')}
            result = subprocess.run([shutil.which('nvim'), '--headless', '--noplugin',
                                     '-u', 'NONE', '-i', 'NONE', '-n', '-l', str(lua)],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(file.read_bytes(), b'original on disk\n')

    @unittest.skipUnless(shutil.which('lua'), 'Lua interpreter is unavailable')
    def test_relative_path_callback_and_unnamed_buffer(self):
        remap = str(REPO / 'nvim/.config/nvim/lua/custom/plugins/remap.lua')
        script = '''
local maps = {}
local name = '/work/project/file with spaces.py'
local written = nil
vim = {
  g = {}, keymap = { set = function(mode, key, rhs) maps[key] = rhs end },
  api = {
    nvim_create_autocmd = function() end,
    nvim_buf_get_name = function() return name end,
  },
  fn = {
    fnamemodify = function(value, modifier)
      assert(value == name and modifier == ':.')
      return 'file with spaces.py'
    end,
    setreg = function(reg, value) assert(reg == '+'); written = value end,
  },
}
dofile(PATH)
assert(type(maps['<leader>cr']) == 'function')
maps['<leader>cr']()
assert(written == 'file with spaces.py')
name = ''; written = 'keep clipboard'
maps['<leader>cr']()
assert(written == 'keep clipboard')
'''.replace('PATH', json.dumps(remap))
        result = subprocess.run(['lua', '-'], input=script, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class AtuinBashHookTests(unittest.TestCase):
    def run_shell(self, interactive=True, disable=False):
        with tempfile.TemporaryDirectory(prefix='atuin-hook-test-') as d:
            root = Path(d)
            home = root / 'home'
            home.mkdir()
            commands = root / 'bin'
            commands.mkdir()
            log = root / 'calls'
            put(commands / 'atuin', b'''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_ATUIN_LOG"
[[ "$*" == 'init bash --disable-up-arrow --disable-ai' ]] || exit 91
printf '_TEST_ATUIN_READY=1\\n'
''', 0o755)
            env = {'HOME': str(home), 'PATH': str(commands) + ':/usr/bin:/bin',
                   'TEST_ATUIN_LOG': str(log), 'TERM': 'dumb', 'LANG': 'C.UTF-8'}
            if disable:
                env['DOTFILES_DISABLE_ATUIN'] = '1'
            script = 'source "$1"; source "$1"; printf "ready=%s\\n" "${_TEST_ATUIN_READY:-0}"'
            flags = '-ic' if interactive else '-c'
            result = subprocess.run(['bash', '--noprofile', '--norc', flags, script,
                                     'test-shell', str(REPO / 'bash/.config/bash/custom.sh')],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            calls = log.read_text().splitlines() if log.exists() else []
            return result.stdout, calls

    def test_interactive_init_is_idempotent_and_preserves_up_arrow(self):
        output, calls = self.run_shell()
        self.assertIn('ready=1', output)
        self.assertEqual(calls, ['init bash --disable-up-arrow --disable-ai'])

    def test_noninteractive_shell_never_initializes_history(self):
        output, calls = self.run_shell(interactive=False)
        self.assertIn('ready=0', output)
        self.assertEqual(calls, [])

    def test_explicit_local_opt_out(self):
        output, calls = self.run_shell(disable=True)
        self.assertIn('ready=0', output)
        self.assertEqual(calls, [])

    @unittest.skipUnless(shutil.which('atuin'), 'Atuin binary is not installed')
    def test_real_init_in_isolated_home_has_expected_bindings_and_valid_bash(self):
        with tempfile.TemporaryDirectory(prefix='atuin-init-test-') as d:
            home = Path(d)
            target = home / '.config/atuin/config.toml'
            target.parent.mkdir(parents=True)
            shutil.copyfile(REPO / 'atuin/.config/atuin/config.toml', target)
            env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'TERM': 'dumb',
                   'XDG_CONFIG_HOME': str(home / '.config'),
                   'XDG_DATA_HOME': str(home / '.local/share'),
                   'XDG_CACHE_HOME': str(home / '.cache')}
            init = subprocess.run([shutil.which('atuin'), 'init', 'bash',
                                   '--disable-up-arrow', '--disable-ai'], env=env,
                                  capture_output=True, text=True, timeout=15)
            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertIn('__atuin_bind_ctrl_r=true', init.stdout)
            self.assertIn('__atuin_bind_up_arrow=false', init.stdout)
            syntax = subprocess.run(['bash', '-n'], input=init.stdout, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            # Prove this binary is reading our managed XDG config rather than
            # silently using defaults from the newer ~/.atuin layout.
            target.write_text('auto_sync = "invalid-boolean-fixture"\n')
            invalid = subprocess.run([shutil.which('atuin'), 'init', 'bash',
                                      '--disable-up-arrow', '--disable-ai'], env=env,
                                     capture_output=True, text=True, timeout=15)
            self.assertNotEqual(invalid.returncode, 0)

    @unittest.skipUnless(shutil.which('atuin'), 'Atuin binary is not installed')
    def test_real_atuin_fixture_history_files_are_private_with_normal_umask(self):
        with tempfile.TemporaryDirectory(prefix='atuin-private-history-test-') as d:
            home = Path(d)
            target = home / '.config/atuin/config.toml'
            target.parent.mkdir(parents=True)
            shutil.copyfile(REPO / 'atuin/.config/atuin/config.toml', target)
            env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'TERM': 'dumb',
                   'SHELL': '/bin/bash', 'ATUIN_SESSION': uuid.uuid4().hex,
                   'XDG_CONFIG_HOME': str(home / '.config'),
                   'XDG_DATA_HOME': str(home / '.local/share'),
                   'XDG_STATE_HOME': str(home / '.local/state'),
                   'XDG_CACHE_HOME': str(home / '.cache')}
            result = subprocess.run([shutil.which('atuin'), 'history', 'start', '--',
                                     'printf synthetic-permission-fixture'], env=env,
                                    umask=0o022, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = [p for p in home.rglob('history.db*') if p.is_file()]
            self.assertTrue(files)
            for file in files:
                self.assertEqual(file.stat().st_mode & 0o077, 0)
                self.assertEqual(file.parent.stat().st_mode & 0o077, 0)
