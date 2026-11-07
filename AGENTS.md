# AGENTS.md — engineering and quality guidelines

This file is for contributors and AI coding agents working on **boxinstall**. The goal is to keep the tool safe, predictable, testable, and consistent with the existing design.

If you change behavior, you are responsible for testing it and updating the documentation.

## 1. Project scope

`boxinstall` is a Bash installer/manager for desktop applications on Bazzite and Fedora Atomic systems. It:

- installs RPMs in Fedora-compatible distroboxes;
- installs DEBs in Ubuntu/Debian distroboxes;
- installs AppImages under `~/AppImages`;
- installs Flatpaks system-wide (with user-scope fallback);
- exports launchers to the GNOME application menu and `~/Desktop`;
- reviews package details, sizes, dependencies, and duplicate versions before installing;
- queues concurrent UI/CI runs;
- lists, updates, removes, and launches installed apps from the CLI and a Zenity GUI.

Do not add host-level `rpm-ostree` layering, Snap support, `.run` installers, daemons, or background services. Keep the tool user-invoked and rootless except for Flatpak operations that require system authorization.

## 2. Architecture map

`boxinstall` is intentionally one Bash file. Keep the section structure:

| Section | Responsibility |
|---|---|
| Small helpers | logging, status output, command execution, cleanup, locking |
| GUI handling | Zenity progress wrapper, child process, summaries |
| Detection | file type and MIME detection, URL handling |
| Distrobox handling | container discovery/creation, snapshots |
| Shortcuts/exports | `distrobox-export`, trusted Desktop copies |
| RPM / DEB / AppImage / Flatpak | per-format metadata, review, install |
| Management | discovery, `list`/`show`/`update`/`remove`/`launch`, `manage` GUI |
| Dispatch | `install_target`, argument parsing, command routing |

`install.sh` installs the command, desktop launchers, completion, MIME defaults, and Desktop Icons NG. `uninstall.sh` reverses the user-level installation. The release workflow reads `VERSION` from `boxinstall`.

## 3. Non-negotiable quality gates

Every change must pass:

```bash
bash -n boxinstall
bash -n install.sh
bash -n uninstall.sh
bash -n completions/boxinstall.bash
shellcheck boxinstall install.sh uninstall.sh completions/boxinstall.bash
```

Also validate both desktop templates:

```bash
sed 's|@BIN@|/home/runner/.local/bin/boxinstall|g' boxinstall.desktop.in > /tmp/boxinstall.desktop
sed 's|@BIN@|/home/runner/.local/bin/boxinstall|g' boxinstall-manage.desktop.in > /tmp/boxinstall-manage.desktop
desktop-file-validate /tmp/boxinstall.desktop
desktop-file-validate /tmp/boxinstall-manage.desktop
```

CI runs these checks on Ubuntu with **ShellCheck 0.9.0**. Newer local ShellCheck versions are more permissive, so do not rely on them alone. In particular, avoid `A && B || C` patterns (SC2015); use explicit `if` blocks.

## 4. Bash style

- Use Bash 5-compatible code and `set -Eeuo pipefail`.
- Use tabs for indentation, matching the existing script.
- Quote every expansion unless word splitting is intentional.
- Use arrays for argument lists; never build command strings for `eval`.
- Initialize variables that may be referenced before assignment, especially under `set -u`.
- Use the existing helpers:
  - `say` for user-facing status (`#` in GUI-child mode);
  - `warn` / `error` for diagnostics;
  - `run` for commands whose output should be logged/streamed;
  - `run_capture` when output must be inspected;
  - `summary_add` and `skip_add` for result lists;
  - `discover_apps` for management records;
  - `acquire_lock` for mutating operations.
- Do not use `local` arrays/associative arrays incorrectly. Remember that command substitutions run in subshells; state changes inside them do not propagate.
- Do not let child commands consume a `while read` loop's stdin. Use a dedicated FD (`3<file`, `read <&3`) and `</dev/null` for child commands.
- Prefer `mktemp` and add temporary paths to `TMP_DIRS`; cleanup is handled on exit.
- Do not use `rm -rf` on user-owned directories without a narrow, explicit path and a documented reason.
- Preserve idempotency: re-running an install/update/remove must be safe.

## 5. GUI conventions

- Use **Zenity**; do not add YAD, GTK Python, or other runtime GUI dependencies.
- The install GUI is a pulsating progress window fed by `#` status lines from `BOXINSTALL_GUI_CHILD=1`.
- Pre-install review uses `zenity --question` with:
  - OK label = `Install` / `Reinstall` / `Upgrade` / `Downgrade` / `Replace` / `Reinstall / update`;
  - Cancel label = `Cancel`;
  - extra button = `Dependencies`.
- Zenity's extra button prints its label to stdout and exits with status 1. Detect it by capturing stdout (`out == "Dependencies"`), not only by exit code. Handle `rc == 0` (OK) and anything else (cancel/close) explicitly.
- Use `--no-markup` for dynamic package/app text so `&` and `<` cannot break dialogs.
- Long dependency data belongs in a scrollable `zenity --text-info --filename=...` window, not in the main question text.
- The management GUI uses hidden ID columns (`--hide-column=1 --print-column=1`). Keep IDs stable and machine-friendly.
- The manager's update/remove actions must call the CLI subcommands through the waiting queue, not bypass it.
- Do not block the manager with a permanent lock; only mutating child commands take the queue.

## 6. Testing requirements

Testing must cover real behavior, not just syntax.

### Safe isolated tests

- Use **throwaway containers** named `boxinstall-*-test` and remove them afterward.
- Use a temporary `HOME`/`XDG_*` for installer/uninstaller tests when possible.
- Do not test removals or downgrades in the user's real `fedora`/`boxinstall-*` containers.
- Do not commit logs, caches, test containers, or downloaded packages.

### Minimum matrix for install changes

| Area | Requirement |
|---|---|
| RPM | Install a small real RPM in a throwaway Fedora container; verify review fields, install, launcher, duplicate review, `remove` |
| DEB | Install a small real DEB in a throwaway Ubuntu container; verify review fields, install, launcher, duplicate review, `remove` |
| AppImage | Install a real AppImage; verify review, launcher, `list`, `remove` |
| Flatpak | Verify review/list/update where feasible; avoid removing unrelated system apps |
| GUI | Test review/manager flows with a mock Zenity or a real graphical session |
| Queue | Test `--wait`, `--no-wait`, timeout, and stale-lock recovery |
| CI | Test `boxinstall list --json` on a machine without distrobox/flatpak |
| Uninstaller | Test in a fake HOME and verify MIME restoration/removal |

### Mock Zenity

For GUI tests, put a fake `zenity` first in `PATH`. It should log arguments, consume `--progress` stdin, and simulate OK/Cancel/extra-button sequences. This is preferred for automated verification; do not click through real dialogs in CI.

### Management IDs

Test `list`, `show`, `update`, `remove`, and `launch` using IDs from `list --tsv`. Verify that removing an app also removes its exported launcher and Desktop copy.

## 7. Metadata and dependency display

- RPM review: use `rpm -qp` for name/version/arch/size/summary and `rpm -qpR` for raw requirements.
- DEB review: use `dpkg-deb -f` for fields and dependency lists; `Installed-Size` is KiB.
- AppImage review: show file size, architecture, destination, and that libraries are bundled.
- Flatpak review: show app ID, branch, remote, ref file, installed version/size, and runtime when installed.
- Clearly label estimates. Do not present a package's own installed size as the total transaction size; note that the package manager resolves/downloads dependencies.
- Filter RPM `rpmlib(...)` requirements out of the dependency view.

## 8. Security and safety

- Never commit credentials, tokens, logs, personal paths, or user-specific state.
- Keep `digest`/GPG behavior conservative: try normal `dnf` first and only retry with `--nogpgcheck` for the local package when the first attempt fails.
- Do not disable signature checks globally or silently.
- Flatpak operations are system-wide by default; use the existing `sudo -n`/Polkit fallback pattern.
- Confirm destructive removals. CLI `remove` must require `-y` in non-interactive mode.
- Do not remove dependencies with `autoremove`; only remove the selected package/app.
- Do not remove Desktop Icons NG on uninstall; document the manual commands instead.
- Keep the waiting queue for all mutating operations. Never bypass it in GUI actions.

## 9. Documentation and releases

- Update `--help`, `README.md`, and this file for user-visible behavior, flags, IDs, paths, or CI changes.
- Add or update tests/CI when behavior changes.
- `VERSION` in `boxinstall` is the release source of truth. Bump it for user-visible releases only; do not bump for docs/CI-only changes.
- The Release workflow runs after CI succeeds on `main`, reads `VERSION`, skips existing releases, and publishes `vX.Y.Z` with source archives. Do not create release tags manually unless the workflow is broken.
- Keep the README's AI-assisted disclaimer and contribution links current.

## 10. AI-assisted contributions

AI tools are allowed and expected, but the human/agent submitting the change is responsible for it.

- Disclose AI assistance in the PR template and describe which parts were AI-generated or AI-reviewed.
- Do not invent commands, flags, APIs, or dependency behavior. Verify against the actual system or documentation.
- Do not claim testing that was not performed.
- Prefer small, reviewable changes with a clear test plan.
- Treat AI output as a draft: run `shellcheck`, test the real flows, and inspect the diff before committing.
- If an AI-generated change cannot be verified, say so explicitly in the PR.

## 11. Definition of done

A change is done only when:

- [ ] The behavior is implemented with the existing helpers and queue.
- [ ] `bash -n` and `shellcheck` pass.
- [ ] Desktop templates validate.
- [ ] Relevant isolated tests were run and cleaned up.
- [ ] `--help` and README are updated.
- [ ] The diff contains no secrets, logs, caches, or unrelated changes.
- [ ] CI passes.
- [ ] The PR template is filled in, including AI disclosure and testing evidence.
