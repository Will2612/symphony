# deploy/lib/render.sh — small helpers shared between install.sh and
# pull-and-restart.sh. Source this file from a caller; it expects the
# caller to define `log` and `die` shell functions before sourcing.
#
# Public API:
#   render_template <src> <dst> <mode>
#       Render <src> (a `envsubst` template) to <dst> with REPO_DIR and
#       CONFIG_DIR substituted. Tilde-prefixed values are expanded to
#       $HOME before substitution so systemd and `docker compose` (which
#       do not expand `~`) see absolute paths. Idempotent and atomic
#       (writes to <dst>.tmp, then `mv -f`).
#   update_env_var <env_file> <key> <value>
#       If <env_file> contains an uncommented line `<key>=...`, replace
#       its value; otherwise append `<key>=<value>`. Value is
#       tilde-expanded before writing.

# Resolve a path's leading tilde to $HOME. Used for values that will be
# read by tools that don't expand `~` (systemd, docker compose).
expand_home() {
  printf '%s' "${1/#\~/$HOME}"
}

render_template() {
  local src="$1" dst="$2" mode="$3"
  [ -f "$src" ] || die "template not found: $src"
  install -d -m 0755 "$(dirname "$dst")"
  local repo config
  repo="$(expand_home "$REPO_DIR")"
  config="$(expand_home "$CONFIG_DIR")"
  REPO_DIR="$repo" CONFIG_DIR="$config" \
    envsubst "\$REPO_DIR \$CONFIG_DIR" \
    < "$src" > "$dst.tmp"
  chmod "$mode" "$dst.tmp"
  mv -f "$dst.tmp" "$dst"
}

update_env_var() {
  local env_file="$1" key="$2" value="$3"
  value="$(expand_home "$value")"
  if grep -q "^${key}=" "$env_file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}
