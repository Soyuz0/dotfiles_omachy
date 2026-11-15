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
