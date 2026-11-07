## Summary

<!-- What does this PR change, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] CI / release workflow
- [ ] Refactor / cleanup

## Testing performed

- [ ] `bash -n boxinstall install.sh uninstall.sh completions/boxinstall.bash`
- [ ] `shellcheck boxinstall install.sh uninstall.sh completions/boxinstall.bash`
- [ ] `desktop-file-validate` on both desktop templates (with `@BIN@` substituted)
- [ ] RPM flow tested in a throwaway distrobox
- [ ] DEB flow tested in a throwaway distrobox
- [ ] AppImage flow tested
- [ ] Flatpak flow tested (or explained why not)
- [ ] Package review / Dependencies dialog tested (mock Zenity or real GUI)
- [ ] Duplicate detection / reinstall prompt tested
- [ ] `list` / `show` / `update` / `remove` / `launch` tested
- [ ] `manage` GUI tested (mock Zenity or real GUI)
- [ ] Queue / concurrent-run behavior tested

## Checklist

- [ ] I read `AGENTS.md` and followed the project guidelines.
- [ ] Help text and `README.md` are updated for user-visible changes.
- [ ] No new runtime dependencies were introduced without discussion.
- [ ] No secrets, logs, caches, or personal paths are committed.
- [ ] Destructive tests were run in throwaway containers/home directories and cleaned up.
- [ ] The change is shellcheck-clean (including ShellCheck 0.9 / SC2015).
- [ ] `VERSION` was bumped only for a user-visible release.

## AI assistance

<!-- Disclose any AI-assisted development. Say which parts were AI-generated or AI-reviewed. -->

## Related issues

<!-- Fixes #... / Relates to #... -->
