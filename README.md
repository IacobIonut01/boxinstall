# boxinstall

[![CI](https://github.com/IacobIonut01/boxinstall/actions/workflows/ci.yml/badge.svg)](https://github.com/IacobIonut01/boxinstall/actions/workflows/ci.yml)
[![Release](https://github.com/IacobIonut01/boxinstall/actions/workflows/release.yml/badge.svg)](https://github.com/IacobIonut01/boxinstall/actions/workflows/release.yml)

> **AI-assisted disclaimer:** this project is developed with the assistance of AI coding tools. AI-generated changes are reviewed and tested and must pass CI, but mistakes are still possible. Review the scripts before running them and please report issues using the templates.

A one-click installer for Linux packages on **Bazzite / Fedora Atomic (Silverblue, Kinoite, …)**.

Double-click an `.rpm`, `.deb`, `.AppImage`, `.flatpakref`, or `.flatpak` file and it:

1. shows a review with package details, estimated size, and a Dependencies window,
2. picks the right installation method,
3. reuses or creates the needed distrobox,
4. installs the app with `dnf`, `apt`, `flatpak`, or natively for AppImages,
5. exports the app to the GNOME application menu,
6. places a trusted launcher on your GNOME desktop.

The same thing works from a terminal:

```bash
boxinstall ~/Downloads/google-chrome-stable_current_x86_64.rpm
boxinstall ~/Downloads/code_1.99_amd64.deb
boxinstall ~/Downloads/Obsidian-1.8.10.AppImage
boxinstall ~/Downloads/app.flatpakref
boxinstall https://example.org/app.rpm
```

## Install

```bash
cd ~/boxinstall
./install.sh
```

That installs `~/.local/bin/boxinstall`, adds the **Install Linux App** launcher, registers the file associations, and enables **Desktop Icons NG (DING)** so desktop shortcuts are actually visible.

`install.sh` also asks the running GNOME Shell to load DING immediately. A logout is only needed if that immediate activation fails (for example, in a headless/non-graphical session); when successful, DING becomes active without logging out.

If you do not want desktop icons, run `./install.sh --no-desktop-icons`; launchers will still go to the app grid and `~/Desktop`.

## Usage

### Double-click

Just double-click a package file in Files/Nautilus. `boxinstall` is the default handler for these types:

| Format | MIME type | Installed with |
|---|---|---|
| `.rpm` | `application/x-rpm` | `dnf` in a Fedora distrobox |
| `.deb` | `application/vnd.debian.binary-package` | `apt` in an Ubuntu distrobox |
| `.AppImage` / `.appimage` | `application/vnd.appimage` | copied to `~/AppImages` |
| `.flatpakref` | `application/vnd.flatpak.ref` | `flatpak install --system` |
| `.flatpak` | `application/vnd.flatpak` | `flatpak install --system` |

A progress window is shown while it works, followed by a success or error dialog. Errors include the relevant log output.

### From the app grid

Open **Install Linux App**, or run `boxinstall` with no arguments in a graphical session. A file picker opens.

### Terminal

```bash
boxinstall FILE...
boxinstall --pick                 # open the file picker
boxinstall --no-gui FILE          # never show dialogs
boxinstall --dry-run --no-gui FILE
boxinstall --no-desktop FILE      # app-menu entry only, no desktop shortcut
boxinstall --box my-container FILE
boxinstall -y FILE                # skip details/duplicate prompts (CI)
boxinstall --reinstall FILE       # allow duplicate installs without the duplicate prompt
boxinstall --wait 600 FILE        # queue for up to 10 minutes
boxinstall --no-wait FILE         # fail immediately if another run is active
boxinstall --help
```

`boxinstall` is installed in `~/.local/bin`, which is already on your `PATH` on Bazzite.

## Package details before install

In graphical mode, opening a package first shows a review dialog:

- package name, version, architecture, and type;
- target distrobox;
- package download size and declared installed size;
- the package summary;
- **Install**, **Cancel**, and **Dependencies** buttons.

**Dependencies** opens a scrollable window with the declared RPM requirements or the DEB `Depends` / `Pre-Depends` / `Recommends` fields. Flatpaks show the app ID, branch, remote, runtime, and installed size; AppImages explain that their libraries are bundled.

In a terminal the same details are printed. A terminal prompt defaults to **yes**; non-interactive runs proceed unless the app is already installed and no `-y`/`--reinstall` was given.

## Already installed / duplicate detection

Before installing, `boxinstall` compares the package with what is already present:

- **RPM:** installed version from `rpm -q` vs. the version in the RPM file.
- **DEB:** installed version from `dpkg-query` vs. the version in the DEB file.
- **Flatpak:** the app ID is already installed in system or user scope.
- **AppImage:** a file with the same name exists in `~/AppImages` (same SHA-256 = reinstall, different file = replace).

The installed version is included in the same review dialog and the action button changes:

| Situation | Button |
|---|---|
| Same version | **Reinstall** |
| Package is newer | **Upgrade** |
| Package is older | **Downgrade** |
| Different/uncomparable versions | **Replace** |
| Flatpak already installed | **Reinstall / update** |

The other button is **Cancel**, which skips that file without changing anything. In a terminal it asks `[Y/n]`; in non-interactive/CI runs it skips unless `-y/--yes`, `--reinstall`, or `BOXINSTALL_REINSTALL=1` is used.

An accepted reinstall/upgrade/downgrade uses the correct package-manager operation (`dnf reinstall`/`upgrade`/`downgrade`, `apt-get --reinstall`/`--allow-downgrades`, `flatpak --or-update`, or copying the new AppImage).

## CI / non-interactive

```bash
boxinstall -y --no-gui ~/Downloads/app.rpm
BOXINSTALL_YES=1 boxinstall --no-gui --no-wait ~/Downloads/app.deb
```

`-y` / `--yes` / `BOXINSTALL_YES=1` means:

- no details review dialog;
- no duplicate prompt;
- proceed with install/reinstall/upgrade automatically.

Combine it with `--no-gui` in CI. The default lock behavior queues behind another run; use `--no-wait` for fail-fast jobs or `--wait SECONDS` / `BOXINSTALL_LOCK_TIMEOUT` to bound the wait.

## Managing installed apps

Open **Manage Installed Apps** from the app grid, or run:

```bash
boxinstall manage
```

The manager discovers:

- apps exported from your distroboxes (RPM/DEB packages),
- AppImages in `~/AppImages/`,
- Flatpaks installed on the system.

For each app it shows the name, version, type, container, and size. Actions are:

- **Details** – package/container/desktop paths and size;
- **Launch** – start the app;
- **Update / Reinstall** – `dnf upgrade`, `apt-get --only-upgrade`, or `flatpak update`; AppImages open a file picker for a replacement;
- **Remove** – uninstall the package/Flatpak/AppImage and clean up its desktop launcher.

The same operations are available non-interactively for CI:

```bash
boxinstall list                     # human-readable table
boxinstall list --json              # machine-readable inventory
boxinstall list --tsv               # tab-separated
boxinstall show rpm:fedora:google-chrome-stable
boxinstall update --all
boxinstall update flatpak:org.gnome.Calculator
boxinstall remove -y appimage:example
boxinstall launch rpm:fedora:google-chrome-stable
```

IDs have the form `rpm:CONTAINER:PACKAGE`, `deb:CONTAINER:PACKAGE`, `flatpak:APP_ID`, `appimage:SLUG`, or `export:CONTAINER:DESKTOP`. `list` prints them, and `show`/`update`/`remove`/`launch` accept either an ID or an app name.

`remove` requires `-y` in non-interactive runs. Updates and removals use the same waiting queue as installs, so a manager action will wait for an active install to finish rather than race it.

CI example:

```bash
boxinstall list --json > inventory.json
boxinstall update --all -y
boxinstall remove -y "$APP_ID"
```

## Concurrent installs / queue

`boxinstall` no longer fails with “another boxinstall instance is already running”. It uses a waiting queue:

- If another run is active, the new run prints **Waiting for another boxinstall instance…** and starts as soon as the first one finishes.
- In the GUI, that message appears in the progress window.
- In a terminal/CI job, the same message goes to stdout/stderr.
- Installs are serialized deliberately so Podman, `dnf`/`apt`, Flatpak, and the desktop launcher/icon databases cannot race each other.

Controls:

```bash
boxinstall --wait 600 FILE         # wait up to 600 seconds (default 3600)
boxinstall --no-wait FILE          # fail immediately instead of queuing
BOXINSTALL_LOCK_TIMEOUT=600 boxinstall FILE
```

A killed process leaves a stale lock; the next run detects the dead PID and removes it automatically. `--no-wait` is useful for CI jobs that want fail-fast behavior; the default queue is useful for UI and parallel CI jobs that should all complete.

## How containers are chosen

For RPMs, `boxinstall` looks for an existing Fedora-compatible distrobox:

1. a container named `boxinstall-fedora`, if it exists,
2. otherwise the first Fedora/RHEL/CentOS/Alma/Rocky container in `distrobox list`,
3. otherwise it creates `boxinstall-fedora` from `registry.fedoraproject.org/fedora-toolbox:latest`.

For DEBs the same rule is used, with Ubuntu/Debian containers and a default `boxinstall-deb` created from `docker.io/library/ubuntu:24.04`.

If a Fedora-compatible distrobox already exists, RPMs reuse it. Use `--box` if you want a specific container instead:

```bash
boxinstall --box boxinstall-fedora app.rpm
```

Container creation is automatic and only happens once per format. `dnf`/`apt` still need to download the app and its dependencies the first time.

### Overrides

```bash
BOXINSTALL_RPM_IMAGE=registry.fedoraproject.org/fedora-toolbox:latest
BOXINSTALL_DEB_IMAGE=docker.io/library/ubuntu:24.04
BOXINSTALL_APPIMAGE_DIR=$HOME/AppImages
BOXINSTALL_BOX=my-container
BOXINSTALL_REINSTALL=1
BOXINSTALL_LOCK_TIMEOUT=600
BOXINSTALL_NO_DESKTOP=1
BOXINSTALL_NO_GUI=1
```

## What gets exported

- **RPM/DEB:** `boxinstall` asks the package manager which `.desktop` files the package provides, then runs `distrobox-export --app …` for each one. The exported launcher goes into `~/.local/share/applications/` and is copied to `~/Desktop/`.
- **Flatpak:** the desktop file exported by Flatpak is copied to `~/Desktop/`.
- **AppImage:** `boxinstall` creates a launcher in `~/.local/share/applications/`, extracts the embedded `.DirIcon` when available, and copies the launcher to `~/Desktop/`. AppImages live in `~/AppImages/` and use the existing `~/AppImages/.icons/` convention.

Desktop copies are made executable and tagged `metadata::trusted=true`, so GNOME/DING can launch them without an “Untrusted application launcher” prompt.

The application-menu entries are always created. Desktop shortcuts are skipped with `--no-desktop` / `BOXINSTALL_NO_DESKTOP=1`.

## AppImages

AppImages are self-contained, so they are **not** run inside a distrobox. They are copied to `~/AppImages/<name>.appimage` and launched directly. This matches the common `~/AppImages` layout.

## Flatpak

Flatpak packages are installed system-wide with `flatpak install --system`. If the system install fails, `boxinstall` retries in user scope. It detects “already installed” and does not create a duplicate user install.

## Snap and `.run`

Snap does not work well on Fedora Atomic/Bazzite, and self-extracting `.run` installers are not safely containerizable. `boxinstall` rejects both with a message pointing to the Flatpak/AppImage/RPM/DEB alternative.

## Releases

`VERSION` in [`boxinstall`](boxinstall) is the source of truth.

When a push to `main` passes CI, the **Release** workflow:

1. reads `VERSION` (for example `1.0.0`),
2. skips if release `v1.0.0` already exists,
3. otherwise creates tag `v1.0.0` and a GitHub Release with generated notes,
4. attaches `boxinstall-1.0.0.tar.gz` and `boxinstall-1.0.0.zip`.

To publish a new version, bump `VERSION` in `boxinstall`, commit, and push to `main`. You can also run the workflow manually from **Actions → Release → Run workflow**.

## Logs

```bash
~/.local/state/boxinstall/boxinstall.log
```

The GUI error dialog shows the tail of this log. Use `--dry-run` to see what would happen without changing anything:

```bash
boxinstall --dry-run --no-gui ~/Downloads/app.rpm
```

## Uninstall

```bash
cd ~/boxinstall
./uninstall.sh              # remove the tool and restore previous file associations
./uninstall.sh --purge      # also remove logs and cache
```

This does **not** remove installed applications, distroboxes, AppImages, or Flatpaks. It also leaves the Desktop Icons NG extension in place; remove it with:

```bash
gnome-extensions disable ding@rastersoft.com
gnome-extensions uninstall ding@rastersoft.com
```

## Security notes

- You are installing third-party software. Only open packages you trust.
- RPM/DEB installs happen inside a rootless Podman distrobox, not on the immutable host.
- `boxinstall` first tries a normal `dnf` install. If that fails, it retries with `--nogpgcheck` so unsigned/local RPMs can still be installed. Repo packages are not normally affected because the fallback is only used when the first attempt fails.
- Flatpak installs are system-wide. This matches the usual Bazzite setup, where Flathub is configured system-wide.
- Desktop shortcuts run through `distrobox-enter` (or `flatpak run`), so they keep working as long as the container/app exists.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

## Contributing

See [AGENTS.md](AGENTS.md) for the code-quality bar, testing requirements, and AI-assisted contribution rules. Please use the issue and pull-request templates.

## Files installed

| Path | Purpose |
|---|---|
| `~/.local/bin/boxinstall` | the command |
| `~/.local/share/applications/boxinstall.desktop` | app-grid launcher and MIME handler |
| `~/.local/share/applications/boxinstall-manage.desktop` | Manage Installed Apps launcher |
| `~/.local/share/bash-completion/completions/boxinstall` | bash completion |
| `~/.local/state/boxinstall/boxinstall.log` | log |
| `~/.local/state/boxinstall/previous-mime-defaults` | restored by `uninstall.sh` |
| `~/.local/share/gnome-shell/extensions/ding@rastersoft.com` | Desktop Icons NG |
| `~/AppImages/` | AppImage installs |
| `~/.local/share/applications/<name>.desktop` | exported launchers |

## Troubleshooting

**Desktop icons do not appear yet.** `install.sh` normally activates DING in the running Shell. If it printed a warning (for example, a headless install), log out and back in once, or run `./install.sh` again from the graphical session.

**Another boxinstall run is active.** The new run queues automatically. Use `--no-wait` to fail fast, or `--wait SECONDS` / `BOXINSTALL_LOCK_TIMEOUT` to bound the wait.

**`boxinstall: command not found`.** Open a new terminal or run `~/.local/bin/boxinstall`. `~/.local/bin` is on the PATH on Bazzite.

**A package installed but no launcher appeared.** Some packages provide only a CLI binary or install their `.desktop` file outside the standard directories. The log shows what happened; run the app with:

```bash
distrobox enter CONTAINER -- APP
```

**A container is broken or you want a clean slate.**

```bash
distrobox rm -f boxinstall-fedora
distrobox rm -f boxinstall-deb
```

The next install recreates them.
