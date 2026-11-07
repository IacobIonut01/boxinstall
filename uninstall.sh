#!/usr/bin/env bash
# Remove boxinstall's launchers, file associations, and helper files.
# Installed applications, distroboxes, AppImages, and Flatpaks are left alone.
set -Eeuo pipefail

BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
STATE_DIR="$HOME/.local/state/boxinstall"
CACHE_DIR="$HOME/.cache/boxinstall"
DATA_DIR="$HOME/.local/share/boxinstall"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
MIME_DEFAULTS_FILE="$STATE_DIR/previous-mime-defaults"

PURGE=0
for arg in "$@"; do
	case "$arg" in
	--purge) PURGE=1 ;;
	-h | --help)
		cat <<EOF
Usage: ./uninstall.sh [--purge]

Removes boxinstall itself and restores the previous file associations.
Installed apps, distroboxes, AppImages, Flatpaks, and the Desktop Icons NG
extension are not removed.

  --purge   also delete boxinstall logs and cache
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

mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}"

app_exists() {
	local app=$1 dir
	[ -n "$app" ] || return 1
	for dir in \
		"$APPS_DIR" \
		"$HOME/.local/share/flatpak/exports/share/applications" \
		"/var/lib/flatpak/exports/share/applications" \
		"/usr/share/applications" \
		"/usr/local/share/applications"; do
		if [ -f "$dir/$app" ]; then
			return 0
		fi
	done
	return 1
}

say "Removing boxinstall"
rm -f "$BIN_DIR/boxinstall"
rm -f "$APPS_DIR/boxinstall.desktop"
rm -f "$APPS_DIR/boxinstall-manage.desktop"
rm -f "$COMPLETION_DIR/boxinstall"

say "Restoring previous file associations"
if [ -f "$MIME_DEFAULTS_FILE" ]; then
	while IFS='=' read -r mime app; do
		[ -n "$mime" ] || continue
		if [ -n "$app" ] && [ "$app" != "boxinstall.desktop" ] && app_exists "$app"; then
			xdg-mime default "$app" "$mime" 2>/dev/null || true
		else
			for file in "$HOME/.config/mimeapps.list" "$APPS_DIR/mimeapps.list"; do
				[ -f "$file" ] || continue
				sed -i "\|^${mime}=boxinstall.desktop$|d" "$file" 2>/dev/null || true
			done
		fi
	done <"$MIME_DEFAULTS_FILE"
else
	for mime in \
		application/x-rpm \
		application/vnd.debian.binary-package \
		application/x-deb \
		application/vnd.appimage \
		application/x-iso9660-appimage \
		application/vnd.flatpak.ref \
		application/vnd.flatpak; do
		for file in "$HOME/.config/mimeapps.list" "$APPS_DIR/mimeapps.list"; do
			[ -f "$file" ] || continue
			sed -i "\|^${mime}=boxinstall.desktop$|d" "$file" 2>/dev/null || true
		done
	done
fi

if command -v update-desktop-database >/dev/null 2>&1; then
	update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

if [ "$PURGE" -eq 1 ]; then
	say "Removing logs and cache"
	rm -rf "$STATE_DIR" "$CACHE_DIR" "$DATA_DIR"
fi

say "Done"
printf '\nNot removed: installed applications, distroboxes, ~/AppImages, Flatpaks.\n'
printf 'To remove the desktop icon extension as well:\n'
printf '  gnome-extensions disable ding@rastersoft.com\n'
printf '  gnome-extensions uninstall ding@rastersoft.com\n'
