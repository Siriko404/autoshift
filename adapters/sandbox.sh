#!/bin/bash
# AutoShift sandbox: every agent call and every agent-written command runs inside this bwrap; there is no
# unsandboxed mode.
#
# usage: sandbox.sh [--rw PATH]... [--ro PATH]... [--net 0|1] [--claude] [--env NAME]... [--path DIR]... [--chdir DIR]
#                   -- cmd...
#   --rw / --ro   bind PATH (resolved) read-write / read-only at the same place; everything else of $HOME is an
#                 empty tmpfs, /tmp is private, the environment is cleared (no display, D-Bus or keyring sockets).
#   --net 1       share the network (model API calls); default 0 = no network.
#   --claude      bind the Claude CLI read-only and the worker's own login home read-write as CLAUDE_CONFIG_DIR
#                 (AUTOSHIFT_CLAUDE_HOME, default ~/.local/state/autoshift/claude-worker). Never the owner's ~/.claude.
#   --env NAME    pass the variable NAME through from the caller's environment.
#   --chdir DIR   working directory inside (default: the first --rw path, else the first --ro path).
#   --path DIR    prepend DIR to PATH inside (bind it with --ro too).
# One-time worker login (owner, interactive):  sandbox.sh --login
set -euo pipefail
H=$HOME
CHOME=${AUTOSHIFT_CLAUDE_HOME:-$H/.local/state/autoshift/claude-worker}
real_cli() {   # prints "ROOT BINDIR" of the REAL executable NAME, never a mise shim (the shims rewrite ~/.local/share/mise)
  local n=$1 r b p x
  r=$(mise where "$n" 2>/dev/null || true)
  if [ -n "$r" ]; then
    for b in "$r" "$r/bin"; do
      if [ -f "$b/$n" ] && [ -x "$b/$n" ]; then echo "$r $b"; return 0; fi
    done
  fi
  local IFS=:
  for x in $PATH; do
    p=$x/$n
    { [ -f "$p" ] && [ -x "$p" ]; } || continue
    if [ "$(head -c 2 "$p")" = '#!' ] && grep -q mise "$p" 2>/dev/null; then continue; fi
    p=$(readlink -f "$p"); echo "$p $(dirname "$p")"; return 0
  done
  return 1
}
claude_dir() { local r b; read -r r b <<<"$(real_cli claude)"; echo "$b"; }
if [ "${1:-}" = --login ]; then
  case "${2:-claude}" in
    claude) mkdir -p "$CHOME"; chmod 700 "$CHOME"
            exec env CLAUDE_CONFIG_DIR="$CHOME" "$(claude_dir)/claude" auth login --claudeai;;
    codex)  D=${AUTOSHIFT_CODEX_HOME:-$H/.local/state/autoshift/codex-worker}; mkdir -p "$D"; chmod 700 "$D"
            read -r r b <<<"$(real_cli codex)"; exec env CODEX_HOME="$D" "$b/codex" login;;
    opencode) D=${AUTOSHIFT_OPENCODE_HOME:-$H/.local/state/autoshift/opencode-worker}; mkdir -p "$D"/{data,config,state,cache}; chmod 700 "$D"
            read -r r b <<<"$(real_cli opencode)"
            exec env XDG_DATA_HOME="$D/data" XDG_CONFIG_HOME="$D/config" XDG_STATE_HOME="$D/state" XDG_CACHE_HOME="$D/cache" "$b/opencode" auth login;;
    agy)    D=${AUTOSHIFT_AGY_HOME:-$H/.local/state/autoshift/agy-worker}; mkdir -p "$D"; chmod 700 "$D"
            read -r r b <<<"$(real_cli agy)"
            # agy keeps its sign-in in ~/.gemini: show it the worker home there, never the owner's own.
            # no session bus: agy must not find the owner's keyring token, so it signs in fresh and saves its own in $D
            exec bwrap --dev-bind / / --bind "$D" "$H/.gemini" --tmpfs "/run/user/$(id -u)" \
                 env -u DBUS_SESSION_BUS_ADDRESS "$b/agy";;
    *) echo "sandbox: --login claude|codex|opencode|agy" >&2; exit 2;;
  esac
fi
XPATH=""; NET=0; CLAUDE=0; PROBE=0; PROVIDER=""; CHDIR=""; FIRST=""; FIRST_RO=""; PASS=()
args=(--unshare-user --unshare-pid --unshare-ipc --unshare-uts --die-with-parent --new-session
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/sbin /sbin --symlink usr/lib /lib --symlink usr/lib /lib64
  --ro-bind /etc /etc --ro-bind /sys /sys --proc /proc --dev /dev --tmpfs /dev/shm --tmpfs /tmp --tmpfs "$H")
binds=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) binds+=(--dir "$2"); shift 2;;
    --rw) p=$(readlink -f "$2"); [ -e "$p" ] || { echo "sandbox: --rw $2 does not exist" >&2; exit 2; }
          binds+=(--bind "$p" "$p"); FIRST=${FIRST:-$p}; shift 2;;
    --ro) p=$(readlink -f "$2"); [ -e "$p" ] || { echo "sandbox: --ro $2 does not exist" >&2; exit 2; }
          binds+=(--ro-bind "$p" "$p"); FIRST_RO=${FIRST_RO:-$p}; shift 2;;
    --net) NET=$2; shift 2;;
    --claude) CLAUDE=1; PROVIDER=claude; shift;;
    --provider) PROVIDER=$2; shift 2;;
    --probe) PROBE=1; shift;;   # skip the login-present checks (--version / DNS probes only)
    --env) [ -n "${!2+x}" ] && PASS+=(--setenv "$2" "${!2}"); shift 2;;
    --chdir) CHDIR=$(readlink -f "$2"); shift 2;;
    --path) XPATH="${XPATH}$2:"; shift 2;;
    --) shift; break;;
    *) echo "sandbox: unknown option $1" >&2; exit 2;;
  esac
done
[ $# -gt 0 ] || { echo "sandbox: no command" >&2; exit 2; }
if [ "$NET" = 1 ]; then
  args+=(--share-net); [ -d /run/systemd/resolve ] && args+=(--ro-bind /run/systemd/resolve /run/systemd/resolve)
else
  args+=(--unshare-net)
fi
WPATH=""; PRE=()
if [ -n "$PROVIDER" ]; then
  case "$PROVIDER" in claude|codex|opencode|agy) ;; *) echo "unknown provider: $PROVIDER" >&2; exit 2;; esac
  # Only the REAL executable's install directory (or the single file) is bound read-only. The owner's
  # ~/.local/bin holds mise shims that rewrite ~/.local/share/mise and fail on a read-only bind.
  read -r CROOT CBIN <<<"$(real_cli "$PROVIDER")" || true
  [ -n "${CROOT:-}" ] || { echo "sandbox: no real $PROVIDER executable found (mise where / PATH)" >&2; exit 78; }
  args+=(--ro-bind "$CROOT" "$CROOT")
  WPATH="$CBIN:"
  # Each provider gets its OWN private login home, writable (the CLIs write session state and refresh tokens
  # there). Never the owner's ~/.codex, ~/.config/opencode, ~/.gemini or ~/.claude.
  if [ "$PROVIDER" = codex ]; then
    CRED=${AUTOSHIFT_CODEX_HOME:-$H/.local/state/autoshift/codex-worker}
    if [ "$PROBE" = 1 ]; then mkdir -p "$CRED"; fi
    [ -f "$CRED/auth.json" ] || [ "$PROBE" = 1 ] || { echo "sandbox: codex worker login missing in $CRED: run $0 --login codex once" >&2; exit 78; }
    args+=(--bind "$CRED" "$CRED")
    PASS+=(--setenv CODEX_HOME "$CRED")
  elif [ "$PROVIDER" = opencode ]; then
    CRED=${AUTOSHIFT_OPENCODE_HOME:-$H/.local/state/autoshift/opencode-worker}
    if [ "$PROBE" = 1 ]; then mkdir -p "$CRED"; fi
    [ -f "$CRED/data/opencode/auth.json" ] || [ "$PROBE" = 1 ] || { echo "sandbox: opencode worker login missing in $CRED: run $0 --login opencode once" >&2; exit 78; }
    mkdir -p "$CRED"/{data,config,state,cache}
    args+=(--bind "$CRED" "$CRED")
    PASS+=(--setenv XDG_DATA_HOME "$CRED/data" --setenv XDG_CONFIG_HOME "$CRED/config"
           --setenv XDG_STATE_HOME "$CRED/state" --setenv XDG_CACHE_HOME "$CRED/cache"
           --setenv OPENCODE_PERMISSION '{"external_directory":"allow"}')   # the handoff file lives outside the work folder; this sandbox is the boundary
  elif [ "$PROVIDER" = agy ]; then
    CRED=${AUTOSHIFT_AGY_HOME:-$H/.local/state/autoshift/agy-worker}
    if [ "$PROBE" = 1 ]; then mkdir -p "$CRED"; fi
    [ -n "$(ls -A "$CRED" 2>/dev/null)" ] || [ "$PROBE" = 1 ] || { echo "sandbox: agy worker login missing in $CRED: run $0 --login agy once" >&2; exit 78; }
    # agy reads and writes ~/.gemini: the worker home appears there, the owner's own never does.
    args+=(--bind "$CRED" "$H/.gemini")
    PASS+=(--setenv AGY_HOME "$CRED")
    P=$(cd "$(dirname "$0")/.." && pwd)
    args+=(--ro-bind "$P/adapters" "$P/adapters")
  fi
fi
if [ "$PROVIDER" = claude ] || [ "$CLAUDE" = 1 ]; then
  mkdir -p "$CHOME"; chmod 700 "$CHOME"
  [ -f "$CHOME/.credentials.json" ] || [ "$PROBE" = 1 ] || { echo "sandbox: worker login missing: run $0 --login once" >&2; exit 78; }
  PASS+=(--setenv CLAUDE_CONFIG_DIR "$CHOME" --setenv DISABLE_AUTOUPDATER 1)   # after --clearenv, which wipes earlier ones
  # Site-specific additions (extra read-only binds, a wrapper command in PRE) come from a bash file you own,
  # sourced here before the worker home is bound writable, so a read-only bind of a parent cannot cover it.
  EXTRA=${AUTOSHIFT_SANDBOX_EXTRA:-$H/.config/autoshift/sandbox-extra.sh}
  [ -f "$EXTRA" ] && . "$EXTRA"
  args+=(--bind "$CHOME" "$CHOME")
fi
CHDIR=${CHDIR:-${FIRST:-${FIRST_RO:-/tmp}}}
# No core dumps from anything inside: tests that abort on purpose would otherwise each leave a system crash report.
ulimit -c 0
exec bwrap "${args[@]}" "${binds[@]}" --chdir "$CHDIR" --clearenv \
  --setenv PATH "${XPATH}${WPATH}/usr/bin:/bin" --setenv HOME "$H" --setenv TERM dumb --setenv LANG C.UTF-8 \
  --setenv TMPDIR /tmp --setenv AUTOSHIFT_SANDBOX 1 "${PASS[@]}" "${PRE[@]}" "$@"
