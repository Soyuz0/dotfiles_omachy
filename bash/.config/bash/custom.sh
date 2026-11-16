# Sourced after Omarchy's stock ~/.bashrc, never instead of it.
# Omarchy already supplies aliases, functions, completion, and mise activation.
[[ $- == *i* ]] || return 0

# Keep installed personal wrappers on this machine; do not copy their contents.
# Append so a local wrapper cannot shadow an Omarchy/system command by default.
case ":${PATH:-}:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="${PATH:+$PATH:}$HOME/.local/bin" ;;
esac

# Credentials and machine-specific overrides belong only in this untracked file.
# The installer must neither create it nor copy a source machine's local.sh.
if [[ -r "$HOME/.config/bash/local.sh" ]]; then
  source "$HOME/.config/bash/local.sh"
fi

# Show the system summary once per interactive terminal, never in piped output.
if [[ -t 1 && ${DOTFILES_DISABLE_FASTFETCH:-0} != 1 && -z ${_DOTFILES_FASTFETCH_SHOWN:-} ]] && command -v fastfetch >/dev/null 2>&1; then
  _DOTFILES_FASTFETCH_SHOWN=1
  command fastfetch || true
fi

# Atuin owns Ctrl-R after Omarchy's fzf initialization. Leave Up-arrow alone.
# Current Atuin bundles Bash preexec support. No history import or login here.
if [[ ${DOTFILES_DISABLE_ATUIN:-0} != 1 && -z ${_DOTFILES_ATUIN_INITIALIZED:-} ]] && command -v atuin >/dev/null 2>&1; then
  if _dotfiles_atuin_init=$(atuin init bash --disable-up-arrow --disable-ai); then
    eval "$_dotfiles_atuin_init"
    _DOTFILES_ATUIN_INITIALIZED=1
  fi
  unset _dotfiles_atuin_init
fi
