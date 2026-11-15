"""Optional helpers must remain inert unless an action is explicitly requested."""
from support import CliCase, snapshot


class HelperPreviewTests(CliCase):
    def assert_default_and_dry_run_plan(self, name, expected):
        for args in ((), ('--dry-run',)):
            with self.subTest(script=name, args=args):
                # Include cwd, HOME, TMPDIR and the command stubs in the snapshot.
                # The helper must not create files anywhere in its test workspace.
                before = snapshot(self.base)
                result = self.helper_preview(name, *args)
                self.assertEqual(result.stderr, '')
                for text in expected:
                    self.assertIn(text, result.stdout)
                self.assertEqual(snapshot(self.base), before)
                self.assertEqual(list(self.home.iterdir()), [])

    def test_dev_default_and_dry_run_print_plans_without_providers(self):
        self.assert_default_and_dry_run_plan('setup_dev.sh', (
            'Provider: existing mise', 'core:node@', 'npm:prettier@',
            'npm:cspell@', 'npm:@openai/codex@', 'Plan only.',
        ))

    def test_tmux_default_and_dry_run_print_plans_without_git_or_tmux(self):
        self.assert_default_and_dry_run_plan('setup_tmux.sh', (
            f'TPM destination: {self.home}/.tmux/plugins/tpm',
            'Pinned ref:', 'Expected revision:', 'Plan only.',
        ))

    def test_theme_default_and_dry_run_print_plans_without_desktop_actions(self):
        self.assert_default_and_dry_run_plan('setup_theme.sh', (
            'Theme: tokyo-night',
            f'Wallpaper: {self.home}/.local/share/omarchy/themes/tokyo-night/backgrounds/',
            'Preview only.',
        ))

    def test_displaylink_help_does_not_probe_hardware_or_run_providers(self):
        before = snapshot(self.base)
        result = self.helper_preview('setup_displaylink.sh', '--help')
        self.assertIn('Usage: bash setup_displaylink.sh', result.stdout)
        self.assertEqual(result.stderr, '')
        self.assertEqual(snapshot(self.base), before)

    def test_compatibility_wrapper_help_does_not_probe_hardware_or_run_providers(self):
        before = snapshot(self.base)
        result = self.helper_preview('setup_thunderbold.sh', '--help')
        self.assertIn('Usage: bash setup_displaylink.sh', result.stdout)
        self.assertIn('compatibility wrapper', result.stderr)
        self.assertEqual(snapshot(self.base), before)


if __name__ == '__main__':
    import unittest
    unittest.main()
