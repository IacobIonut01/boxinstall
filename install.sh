#!/usr/bin/env bash
# Install boxinstall into the user's home directory and register it as the
# default handler for Linux package files.
set -Eeuo pipefail

SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
STATE_DIR="$HOME/.local/state/boxinstall"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
MIME_DEFAULTS_FILE="$STATE_DIR/previous-mime-defaults"

MIMES=(
	application/x-rpm
	application/vnd.debian.binary-package
	application/x-deb
	application/vnd.appimage
	application/x-iso9660-appimage
	application/vnd.flatpak.ref
	application/vnd.flatpak
)

INSTALL_ICONS=1
for arg in "$@"; do
	case "$arg" in
	--no-desktop-icons) INSTALL_ICONS=0 ;;
	-h | --help)
		cat <<EOF
Usage: ./install.sh [--no-desktop-icons]

Installs boxinstall to ~/.local/bin, adds an "Install Linux App" launcher,
registers it as the default handler for RPM/DEB/AppImage/Flatpak files, and
(unless --no-desktop-icons is used) enables the GNOME Desktop Icons NG
extension so desktop shortcuts are visible.
EOF
		exit 0
		;;
	*)
		printf 'Unknown option: %s\n' "$arg" >&2
		exit 2
		;;
	esac
done

say() {
	printf '==> %s\n' "$*"
}

warn() {
	printf 'Warning: %s\n' "$*" >&2
}

for cmd in distrobox podman flatpak zenity xdg-mime update-desktop-database; do
	if ! command -v "$cmd" >/dev/null 2>&1; then
		warn "missing recommended command: $cmd"
	fi
done

mkdir -p "$BIN_DIR" "$APPS_DIR" "$STATE_DIR" "${XDG_CONFIG_HOME:-$HOME/.config}"

say "Installing boxinstall to $BIN_DIR"
install -m 0755 "$SRC_DIR/boxinstall" "$BIN_DIR/boxinstall"

# Record the *previous* associations before adding our own .desktop file,
# otherwise xdg-mime can report our handler as the "previous" default.
if [ ! -f "$MIME_DEFAULTS_FILE" ]; then
	: >"$MIME_DEFAULTS_FILE"
	for mime in "${MIMES[@]}"; do
		prev=$(xdg-mime query default "$mime" 2>/dev/null || true)
		[ "$prev" = "boxinstall.desktop" ] && prev=""
		printf '%s=%s\n' "$mime" "$prev" >>"$MIME_DEFAULTS_FILE"
	done
fi

say "Installing application launcher"
sed "s|@BIN@|$BIN_DIR/boxinstall|g" "$SRC_DIR/boxinstall.desktop.in" >"$APPS_DIR/boxinstall.desktop"
chmod 0644 "$APPS_DIR/boxinstall.desktop"
if command -v desktop-file-validate >/dev/null 2>&1; then
	desktop-file-validate "$APPS_DIR/boxinstall.desktop" || true
fi

say "Installing app manager launcher"
sed "s|@BIN@|$BIN_DIR/boxinstall|g" "$SRC_DIR/boxinstall-manage.desktop.in" >"$APPS_DIR/boxinstall-manage.desktop"
chmod 0644 "$APPS_DIR/boxinstall-manage.desktop"
if command -v desktop-file-validate >/dev/null 2>&1; then
	desktop-file-validate "$APPS_DIR/boxinstall-manage.desktop" || true
fi

say "Installing GTK app manager"
mkdir -p "$HOME/.local/lib/boxinstall"
install -m 0644 "$SRC_DIR/manager.py" "$HOME/.local/lib/boxinstall/manager.py"

say "Installing shell completion"
mkdir -p "$COMPLETION_DIR"
install -m 0644 "$SRC_DIR/completions/boxinstall.bash" "$COMPLETION_DIR/boxinstall"

say "Registering file associations"
for mime in "${MIMES[@]}"; do
	xdg-mime default boxinstall.desktop "$mime" 2>/dev/null || warn "could not register $mime"
done
update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Desktop Icons NG
# ---------------------------------------------------------------------------
enable_ding_setting() {
	local current new
	current=$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || true)
	[ -n "$current" ] || return 0
	case "$current" in
	*"ding@rastersoft.com"*) return 0 ;;
	esac
	if [ "$current" = "@as []" ] || [ "$current" = "[]" ]; then
		new="['ding@rastersoft.com']"
	else
		new="${current%]}"
		new="${new}, 'ding@rastersoft.com']"
	fi
	gsettings set org.gnome.shell enabled-extensions "$new" 2>/dev/null || {
		warn "could not enable Desktop Icons NG in GSettings"
		return 0
	}
	say "Enabled Desktop Icons NG in the GNOME session settings"
}

ding_state() {
	gnome-extensions info ding@rastersoft.com 2>/dev/null |
		awk -F': ' '/State:/{print $2; exit}'
}

activate_ding_now() {
	command -v gdbus >/dev/null 2>&1 || return 1
	# Ask the running Shell to install/rescan and load the extension. This
	# can print a "Remote peer disconnected" error while still succeeding,
	# so ignore the exit status and check the state instead.
	gdbus call --session --dest org.gnome.Shell.Extensions \
		--object-path /org/gnome/Shell/Extensions \
		--method org.gnome.Shell.Extensions.InstallRemoteExtension \
		'ding@rastersoft.com' >/dev/null 2>&1 || true
	sleep 2
	[ "$(ding_state)" = "ACTIVE" ]
}

install_desktop_icons() {
	local shell_major info download_path zip tmp ding_dir

	if ! command -v gnome-extensions >/dev/null 2>&1; then
		warn "gnome-extensions is unavailable; desktop icons are not enabled"
		return 0
	fi
	case "${XDG_CURRENT_DESKTOP:-}" in
	*GNOME* | *gnome*) ;;
	*)
		warn "not running GNOME; skipping the Desktop Icons NG extension"
		return 0
		;;
	esac

	shell_major=$(gnome-shell --version 2>/dev/null | awk '{print $3}' | cut -d. -f1)
	[ -n "$shell_major" ] || shell_major=50
	ding_dir="$HOME/.local/share/gnome-shell/extensions/ding@rastersoft.com"

	if [ -d "$ding_dir" ] && { [ ! -f "$ding_dir/metadata.json" ] || grep -q "\"$shell_major\"" "$ding_dir/metadata.json"; }; then
		enable_ding_setting
		gnome-extensions enable ding@rastersoft.com 2>/dev/null || true
		if [ "$(ding_state)" = "ACTIVE" ] || activate_ding_now; then
			say "Desktop Icons NG is active now"
		else
			warn "Desktop Icons NG is installed and enabled for the next login; log out and back in once"
		fi
		return 0
	fi

	if gnome-extensions list 2>/dev/null | grep -qx 'ding@rastersoft.com'; then
		enable_ding_setting
		gnome-extensions enable ding@rastersoft.com 2>/dev/null || true
		if [ "$(ding_state)" = "ACTIVE" ] || activate_ding_now; then
			say "Desktop Icons NG is active now"
		else
			warn "Desktop Icons NG is installed; log out and back in to enable it"
		fi
		return 0
	fi

	say "Installing the GNOME Desktop Icons NG extension"
	info=$(curl -fsS --max-time 25 \
		"https://extensions.gnome.org/extension-info/?uuid=ding@rastersoft.com&shell_version=$shell_major" 2>/dev/null) || {
		warn "could not reach extensions.gnome.org; desktop shortcuts will not be visible until an icon extension is installed"
		return 0
	}

	if command -v python3 >/dev/null 2>&1; then
		download_path=$(printf '%s' "$info" | python3 -c \
			'import json,sys; print(json.load(sys.stdin).get("download_url", ""))' 2>/dev/null || true)
	else
		download_path=$(printf '%s' "$info" | grep -o '"download_url":"[^"]*"' | head -n1 | cut -d'"' -f4 || true)
	fi
	if [ -z "$download_path" ]; then
		warn "could not find a Desktop Icons NG build for GNOME $shell_major"
		return 0
	fi

	tmp=$(mktemp -d)
	zip="$tmp/ding@rastersoft.com.shell-extension.zip"
	if ! curl -fsSL --retry 2 --max-time 90 -o "$zip" "https://extensions.gnome.org$download_path"; then
		rm -rf "$tmp"
		warn "could not download Desktop Icons NG"
		return 0
	fi

	if gnome-extensions install --force "$zip"; then
		enable_ding_setting
		gnome-extensions enable ding@rastersoft.com 2>/dev/null || true
		if [ "$(ding_state)" = "ACTIVE" ] || activate_ding_now; then
			say "Desktop Icons NG is active now"
		else
			warn "Desktop Icons NG is installed and enabled for the next login; log out and back in once to show desktop icons"
		fi
	else
		warn "Desktop Icons NG could not be installed; shortcuts will still work from the app grid"
	fi
	rm -rf "$tmp"
}

if [ "$INSTALL_ICONS" -eq 1 ]; then
	install_desktop_icons
else
	say "Skipping Desktop Icons NG (--no-desktop-icons)"
fi

say "Done"
printf '\n'
printf 'Try it:\n'
printf '  boxinstall ~/Downloads/app.rpm\n'
printf '  boxinstall ~/Downloads/app.deb\n'
printf '  boxinstall ~/Downloads/App.AppImage\n'
printf '  boxinstall ~/Downloads/app.flatpakref\n'
printf '  boxinstall manage        # open Manage Installed Apps\n'
printf '\n'
printf 'Or double-click a package file, or open "Install Linux App" from the app grid.\n'
case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) printf '\nNote: add %s to your PATH to run boxinstall by name.\n' "$BIN_DIR" ;;
esac
