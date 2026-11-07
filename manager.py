#!/usr/bin/env python3
"""GTK4/Libadwaita manager for boxinstall.

The Bash script owns package discovery and the actual package-manager
operations. This app is a front-end: it reads `boxinstall list --tsv`,
renders the list, and shells out to `boxinstall list/show/update/remove/launch`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

APP_ID = "io.github.iacobionut01.Boxinstall"
BIN = os.environ.get("BOXINSTALL_BIN") or shutil.which("boxinstall")
FALLBACK_ICON = "emblem-system-symbolic"
GENERIC_ICONS = {
    "application-x-executable",
    "application-x-executable-symbolic",
    "text-x-generic",
    "text-x-generic-symbolic",
    "application-x-generic",
}

CSS = b"""
.drop-zone {
    background-color: alpha(@accent_bg_color, 0.94);
    border: 3px dashed @accent_color;
    border-radius: 24px;
}
.drop-zone-title {
    font-size: 1.6em;
    font-weight: 800;
}
"""


def parse_size(text: str) -> int:
    """Parse human sizes like 5.1 MB, 452MiB, 1.2 GiB into bytes."""
    if not text:
        return 0
    text = re.sub(r"\s+", " ", text.strip())
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTP]?)(i?)B?", text, re.I)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    binary = match.group(3).lower() == "i"
    base = 1024 if binary else 1000
    power = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5}.get(unit, 0)
    return int(value * (base**power))


def desktop_icon(desktop_file: str) -> str | None:
    if not desktop_file or not os.path.isfile(desktop_file):
        return None
    try:
        with open(desktop_file, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("Icon="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


class AppItem(GObject.Object):
    __gtype_name__ = "BoxinstallAppItem"

    def __init__(self, fields: list[str]):
        super().__init__()
        (self.id, self.name, self.version, self.type, self.container,
         self.location, self.desktop, self.source, self.size) = fields[:9]
        self.size_bytes = parse_size(self.size)

    @property
    def search_text(self) -> str:
        return " ".join(
            (self.name, self.version, self.type, self.container, self.id)
        ).casefold()


class ManagerWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(
            application=application,
            title="Manage Installed Apps",
            default_width=1180,
            default_height=760,
        )
        self.set_icon_name("system-software-install")

        self.icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        self._icon_cache: dict[str, tuple[str | None, str | None]] = {}
        self.current_items: list[AppItem] = []
        self.sort_key = "name"
        self.sort_desc = False
        self.loading = False

        # Data model -----------------------------------------------------
        self.store = Gio.ListStore.new(AppItem)
        self.filter = Gtk.CustomFilter.new(self._filter_func)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self.filter)
        self.sorter = Gtk.CustomSorter.new(self._sort_compare, None)
        self.sort_model = Gtk.SortListModel(model=self.filter_model, sorter=self.sorter)
        self.selection = Gtk.MultiSelection(model=self.sort_model)

        # List -----------------------------------------------------------
        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.set_show_row_separators(True)
        self.column_view.set_show_column_separators(False)
        self.column_view.set_vexpand(True)

        self.columns = {}
        self.columns["name"] = self._make_column(
            "App", self._make_name_factory(), expand=True
        )
        self.columns["version"] = self._make_text_column("Version", "version", 135)
        self.columns["type"] = self._make_text_column("Package type", "type", 120)
        self.columns["container"] = self._make_text_column("Container", "container", 140)
        self.columns["size"] = self._make_text_column("Size", "size", 105)
        for column in self.columns.values():
            self.column_view.append_column(column)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroll.set_child(self.column_view)
        list_scroll.set_vexpand(True)

        # Side panel -----------------------------------------------------
        self.side_stack = Gtk.Stack()
        self.side_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.side_stack.add_named(self._build_empty_page(), "empty")
        self.side_stack.add_named(self._build_single_page(), "single")
        self.side_stack.add_named(self._build_multi_page(), "multi")
        self.side_stack.set_visible_child_name("empty")
        self.side_stack.set_size_request(370, -1)

        # Layout ---------------------------------------------------------
        self.paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self.paned.set_start_child(list_scroll)
        self.paned.set_end_child(self.side_stack)
        self.paned.set_position(780)
        self.paned.set_resize_start_child(True)
        self.paned.set_resize_end_child(False)
        self.paned.set_shrink_start_child(False)
        self.paned.set_shrink_end_child(False)

        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.paned)
        self.drop_box = self._build_drop_overlay()
        self.overlay.add_overlay(self.drop_box)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.overlay)

        header = self._build_header()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.toast_overlay)
        self.set_content(toolbar)

        self._install_css()
        self._install_drop_target()
        self.selection.connect("selection-changed", self._on_selection_changed)
        self.search.connect("search-changed", self._on_search_changed)

        self.reload()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _make_column(self, title, factory, expand=False):
        column = Gtk.ColumnViewColumn.new(title, factory)
        column.set_expand(expand)
        column.set_resizable(True)
        return column

    def _make_text_column(self, title, attr, width):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_text)
        factory.connect(
            "bind",
            lambda _factory, item: item.get_child().set_text(
                getattr(item.get_item(), attr) or "-"
            ),
        )
        column = self._make_column(title, factory)
        column.set_fixed_width(width)
        return column

    def _setup_text(self, _factory, list_item):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_halign(Gtk.Align.START)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)

    def _make_name_factory(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_name)
        factory.connect("bind", self._bind_name)
        return factory

    def _setup_name(self, _factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        image = Gtk.Image()
        image.set_pixel_size(28)
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_halign(Gtk.Align.START)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        box.append(image)
        box.append(label)
        list_item.set_child(box)

    def _bind_name(self, _factory, list_item):
        item = list_item.get_item()
        box = list_item.get_child()
        image = box.get_first_child()
        label = image.get_next_sibling()
        self._set_icon(image, item, 28)
        label.set_text(item.name or "-")

    def _build_header(self):
        self.window_title = Adw.WindowTitle(
            title="Manage Installed Apps", subtitle="Loading…"
        )
        header = Adw.HeaderBar()
        header.set_title_widget(self.window_title)

        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh")
        self.refresh_button.connect("clicked", lambda _b: self.reload())
        header.pack_start(self.refresh_button)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search apps")
        self.search.set_size_request(230, -1)
        header.pack_start(self.search)

        self.sort_dropdown = Gtk.DropDown.new_from_strings(
            ["Name", "Version", "Package type", "Container", "Size"]
        )
        self.sort_dropdown.set_tooltip_text("Sort by")
        self.sort_dropdown.connect("notify::selected", self._on_sort_changed)
        header.pack_end(self.sort_dropdown)

        self.sort_desc_button = Gtk.ToggleButton()
        self.sort_desc_button.set_icon_name("view-sort-ascending-symbolic")
        self.sort_desc_button.set_tooltip_text("Toggle sort direction")
        self.sort_desc_button.connect("toggled", self._on_sort_direction)
        header.pack_end(self.sort_desc_button)

        self.select_all_button = Gtk.Button.new_from_icon_name(
            "edit-select-all-symbolic"
        )
        self.select_all_button.set_tooltip_text("Select all")
        self.select_all_button.connect(
            "clicked", lambda _b: self.selection.select_all()
        )
        header.pack_end(self.select_all_button)

        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        header.pack_end(self.spinner)
        return header

    def _build_empty_page(self):
        self.empty_page = Adw.StatusPage(
            icon_name=FALLBACK_ICON,
            title="Select an app",
            description="Details and quick actions appear here.",
        )
        return self.empty_page

    def _build_single_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        self.side_icon = Gtk.Image()
        self.side_icon.set_pixel_size(96)
        self.side_icon.set_halign(Gtk.Align.CENTER)
        box.append(self.side_icon)

        self.side_name = Gtk.Label()
        self.side_name.set_wrap(True)
        self.side_name.set_justify(Gtk.Justification.CENTER)
        self.side_name.add_css_class("title-2")
        box.append(self.side_name)

        self.side_version = Gtk.Label()
        self.side_version.add_css_class("dim-label")
        box.append(self.side_version)

        self.side_type = Gtk.Label()
        self.side_type.add_css_class("dim-label")
        box.append(self.side_type)

        group = Adw.PreferencesGroup()
        self.rows = {}
        for key, title in (
            ("container", "Container"),
            ("size", "Size"),
            ("location", "Location"),
            ("desktop", "Desktop file"),
            ("source", "Source"),
        ):
            row = Adw.ActionRow(title=title)
            row.set_subtitle_selectable(True)
            row.set_subtitle_lines(2)
            group.add(row)
            self.rows[key] = row
        box.append(group)

        self.btn_launch = Gtk.Button(label="Launch")
        self.btn_update = Gtk.Button(label="Update")
        self.btn_update.add_css_class("suggested-action")
        self.btn_remove = Gtk.Button(label="Remove")
        self.btn_remove.add_css_class("destructive-action")
        self.btn_launch.connect("clicked", lambda _b: self._launch_selected())
        self.btn_update.connect("clicked", lambda _b: self._update_selected())
        self.btn_remove.connect("clicked", lambda _b: self._remove_selected())

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_homogeneous(True)
        actions.append(self.btn_launch)
        actions.append(self.btn_update)
        actions.append(self.btn_remove)
        box.append(actions)

        scroll.set_child(box)
        return scroll

    def _build_multi_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(18)
        box.set_margin_end(18)

        icon = Gtk.Image.new_from_icon_name("edit-select-all-symbolic")
        icon.set_pixel_size(72)
        box.append(icon)

        self.multi_title = Gtk.Label()
        self.multi_title.add_css_class("title-2")
        self.multi_title.set_wrap(True)
        self.multi_title.set_justify(Gtk.Justification.CENTER)
        box.append(self.multi_title)

        description = Gtk.Label(
            label="Apply an action to the selected apps."
        )
        description.add_css_class("dim-label")
        description.set_wrap(True)
        description.set_justify(Gtk.Justification.CENTER)
        box.append(description)

        self.btn_bulk_update = Gtk.Button(label="Update selected")
        self.btn_bulk_update.add_css_class("suggested-action")
        self.btn_bulk_remove = Gtk.Button(label="Remove selected")
        self.btn_bulk_remove.add_css_class("destructive-action")
        self.btn_bulk_clear = Gtk.Button(label="Clear selection")
        self.btn_bulk_update.connect("clicked", lambda _b: self._update_selected())
        self.btn_bulk_remove.connect("clicked", lambda _b: self._remove_selected())
        self.btn_bulk_clear.connect(
            "clicked", lambda _b: self.selection.unselect_all()
        )
        for button in (
            self.btn_bulk_update,
            self.btn_bulk_remove,
            self.btn_bulk_clear,
        ):
            button.set_hexpand(True)
            box.append(button)

        return box

    def _build_drop_overlay(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.add_css_class("drop-zone")
        box.set_halign(Gtk.Align.FILL)
        box.set_valign(Gtk.Align.FILL)
        box.set_hexpand(True)
        box.set_vexpand(True)
        box.set_margin_top(28)
        box.set_margin_bottom(28)
        box.set_margin_start(28)
        box.set_margin_end(28)
        box.set_can_target(False)
        box.set_visible(False)

        icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        icon.set_pixel_size(96)
        icon.set_halign(Gtk.Align.CENTER)
        box.append(icon)

        title = Gtk.Label(label="Drop packages to install")
        title.add_css_class("drop-zone-title")
        title.set_justify(Gtk.Justification.CENTER)
        box.append(title)

        subtitle = Gtk.Label(
            label="RPM · DEB · AppImage · tar.gz · Flatpakref · Flatpak"
        )
        subtitle.add_css_class("dim-label")
        subtitle.set_justify(Gtk.Justification.CENTER)
        box.append(subtitle)
        return box

    def _install_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _install_drop_target(self):
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("enter", self._on_drag_enter)
        target.connect("motion", self._on_drag_motion)
        target.connect("leave", self._on_drag_leave)
        target.connect("drop", self._on_drop)
        self.add_controller(target)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def reload(self):
        if self.loading:
            return
        if not BIN:
            self._show_error("boxinstall not found", "Set BOXINSTALL_BIN or install boxinstall first.")
            return
        self.loading = True
        self.refresh_button.set_sensitive(False)
        self.spinner.set_visible(True)
        self.spinner.start()
        thread = threading.Thread(target=self._load_worker, daemon=True)
        thread.start()

    def _load_worker(self):
        try:
            result = subprocess.run(
                [BIN, "list", "--tsv"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "boxinstall list failed")
            records = []
            for line in result.stdout.splitlines():
                fields = line.split("\t")
                if len(fields) >= 9:
                    records.append(fields[:9])
            GLib.idle_add(self._populate, records, None)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._populate, [], str(exc))

    def _populate(self, records, error):
        self.loading = False
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.refresh_button.set_sensitive(True)

        if error:
            self._show_error("Could not load installed apps", str(error))

        self.store.remove_all()
        for fields in records:
            self.store.append(AppItem(fields))
        self.selection.unselect_all()
        self.side_stack.set_visible_child_name("empty")
        self.empty_page.set_title("Select an app" if records else "No apps found")
        self.empty_page.set_description(
            "Details and quick actions appear here."
            if records
            else "Install a package or drop one here, then refresh."
        )
        self._update_subtitle()
        return GLib.SOURCE_REMOVE

    def _update_subtitle(self, selected: int | None = None):
        total = self.store.get_n_items()
        if selected is None:
            selected = len(self.current_items)
        text = f"{total} app{'s' if total != 1 else ''}"
        if selected:
            text += f" • {selected} selected"
        self.window_title.set_subtitle(text)

    # ------------------------------------------------------------------
    # Selection and side panel
    # ------------------------------------------------------------------
    def _selected_items(self) -> list[AppItem]:
        items = []
        bitset = self.selection.get_selection()
        for index in range(bitset.get_size()):
            item = self.selection.get_item(bitset.get_nth(index))
            if item is not None:
                items.append(item)
        return items

    def _on_selection_changed(self, _selection, _position, _n_items):
        items = self._selected_items()
        self.current_items = items
        self._update_subtitle(len(items))

        if not items:
            self.side_stack.set_visible_child_name("empty")
        elif len(items) == 1:
            self._show_single(items[0])
            self.side_stack.set_visible_child_name("single")
        else:
            self._show_multi(items)
            self.side_stack.set_visible_child_name("multi")

    def _show_single(self, item: AppItem):
        self._set_icon(self.side_icon, item, 96)
        self.side_name.set_text(item.name or item.id)
        self.side_version.set_text(item.version or "unknown version")
        self.side_type.set_text(item.type or "unknown type")
        self.rows["container"].set_subtitle(item.container or "-")
        self.rows["size"].set_subtitle(item.size or "-")
        self.rows["location"].set_subtitle(item.location or "-")
        self.rows["desktop"].set_subtitle(item.desktop or "-")
        self.rows["source"].set_subtitle(item.source or "-")

        if item.type in ("AppImage", "Tarball"):
            self.btn_update.set_label("Reinstall from file…")
            self.btn_update.set_sensitive(True)
        elif item.type == "Distrobox":
            self.btn_update.set_label("Update unavailable")
            self.btn_update.set_sensitive(False)
        else:
            self.btn_update.set_label("Update")
            self.btn_update.set_sensitive(True)

    def _show_multi(self, items: list[AppItem]):
        self.multi_title.set_text(f"{len(items)} apps selected")
        # AppImage and tarball updates need a replacement file. If the
        # selection is all file-based apps, make that explicit.
        if all(item.type in ("AppImage", "Tarball") for item in items):
            self.btn_bulk_update.set_sensitive(False)
            self.btn_bulk_update.set_tooltip_text(
                "AppImage and tarball updates require selecting a replacement file individually."
            )
        else:
            self.btn_bulk_update.set_sensitive(True)
            self.btn_bulk_update.set_tooltip_text(None)

    # ------------------------------------------------------------------
    # Icons
    # ------------------------------------------------------------------
    def _set_icon(self, image: Gtk.Image, item: AppItem, size: int):
        name, path = self._resolve_icon(item)
        image.set_pixel_size(size)
        if path:
            try:
                texture = Gdk.Texture.new_from_filename(path)
                image.set_from_paintable(texture)
                return
            except GLib.Error:
                pass
        image.set_from_icon_name(name or FALLBACK_ICON)

    def _resolve_icon(self, item: AppItem):
        desktop_file = item.desktop
        if item.source and item.source.endswith(".desktop") and os.path.isfile(item.source):
            desktop_file = item.source
        cache_key = desktop_file or ""
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        icon = desktop_icon(desktop_file)
        result = (FALLBACK_ICON, None)
        if icon:
            icon = os.path.expanduser(icon)
            if os.path.isabs(icon):
                if os.path.isfile(icon):
                    result = (None, icon)
            elif icon not in GENERIC_ICONS and self.icon_theme.has_icon(icon):
                result = (icon, None)
        self._icon_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # Filtering and sorting
    # ------------------------------------------------------------------
    def _filter_func(self, item: AppItem) -> bool:
        query = self.search.get_text().strip().casefold()
        return not query or query in item.search_text

    def _on_search_changed(self, _entry):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_sort_changed(self, dropdown, _pspec):
        keys = ["name", "version", "type", "container", "size"]
        index = dropdown.get_selected()
        if 0 <= index < len(keys):
            self.sort_key = keys[index]
            self._resort()

    def _on_sort_direction(self, button):
        self.sort_desc = button.get_active()
        button.set_icon_name(
            "view-sort-descending-symbolic"
            if self.sort_desc
            else "view-sort-ascending-symbolic"
        )
        self._resort()

    def _resort(self):
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def _sort_compare(self, a: AppItem, b: AppItem, _data) -> int:
        if self.sort_key == "size":
            va, vb = a.size_bytes, b.size_bytes
        else:
            va, vb = getattr(a, self.sort_key, ""), getattr(b, self.sort_key, "")
            va, vb = (va or "").casefold(), (vb or "").casefold()
        if va < vb:
            result = -1
        elif va > vb:
            result = 1
        else:
            result = 0
        return -result if self.sort_desc else result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _launch_selected(self):
        if len(self.current_items) != 1:
            return
        item = self.current_items[0]
        try:
            subprocess.Popen(
                [BIN, "launch", item.id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._toast(f"Launching {item.name}…")
        except OSError as exc:
            self._show_error("Could not launch app", str(exc))

    def _update_selected(self):
        items = list(self.current_items)
        if not items:
            return
        if len(items) == 1 and items[0].type in ("AppImage", "Tarball"):
            self._choose_source_file(items[0])
            return

        updatable = [
            item for item in items
            if item.type in ("RPM", "DEB", "Flatpak")
        ]
        skipped = len(items) - len(updatable)
        if not updatable:
            self._toast("No updatable packages selected.")
            return
        if skipped:
            self._toast(f"Skipped {skipped} AppImage/Tarball/Distrobox item(s).")
        self._run_action("update", updatable)

    def _remove_selected(self):
        items = list(self.current_items)
        if not items:
            return
        names = ", ".join(item.name for item in items[:8])
        if len(items) > 8:
            names += f", and {len(items) - 8} more"
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"Remove {len(items)} app{'s' if len(items) != 1 else ''}?",
            body=f"{names}\n\nThis removes the package/Flatpak/AppImage/tarball and its launcher.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            dlg.destroy()
            if response == "remove":
                self._run_action("remove", items)

        dialog.connect("response", on_response)
        dialog.present()

    def _run_action(self, action: str, items: list[AppItem]):
        if not BIN or not items:
            return
        ids = [item.id for item in items]
        command = [BIN, action, "-y", *ids]
        self._set_busy(True)
        verb = "Updating" if action == "update" else "Removing"
        self._toast(f"{verb} {len(items)} app{'s' if len(items) != 1 else ''}…")

        def worker():
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                GLib.idle_add(self._action_done, action, result)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._action_done, action, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _action_done(self, action: str, result):
        self._set_busy(False)
        if isinstance(result, Exception):
            self._show_error(f"{'Update' if action == 'update' else 'Remove'} failed", str(result))
            self.reload()
            return
        if result.returncode != 0:
            details = (result.stdout or "") + (result.stderr or "")
            self._show_error(
                f"{'Update' if action == 'update' else 'Remove'} failed",
                details.strip()[-4000:] or "The command failed without output.",
            )
        else:
            self._toast(f"{'Updated' if action == 'update' else 'Removed'}.")
        self.reload()

    def _choose_source_file(self, item: AppItem):
        if item.type == "Tarball":
            title = f"Choose the new package for {item.name}"
            filter_name = "Tarball packages"
            patterns = [
                "*.tar.gz", "*.tgz", "*.tar.xz", "*.txz",
                "*.tar.zst", "*.tzst", "*.tar.bz2", "*.tbz2", "*.tar",
            ]
        else:
            title = f"Choose a new AppImage for {item.name}"
            filter_name = "AppImage packages"
            patterns = ["*.AppImage", "*.appimage"]

        dialog = Gtk.FileDialog(title=title)
        file_filter = Gtk.FileFilter()
        file_filter.set_name(filter_name)
        for pattern in patterns:
            file_filter.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)
        self._file_dialog = dialog

        def on_chosen(dlg, result):
            try:
                gfile = dlg.open_finish(result)
            except GLib.Error:
                return
            path = gfile.get_path() if gfile else None
            if path:
                self._install_paths([path])

        dialog.open(self, None, on_chosen)

    def _install_paths(self, paths: list[str]):
        if not BIN or not paths:
            return
        self._toast(f"Installing {len(paths)} package{'s' if len(paths) != 1 else ''}…")

        def worker():
            env = dict(os.environ)
            env["BOXINSTALL_GUI"] = "1"
            try:
                subprocess.run([BIN, *paths], env=env)
            finally:
                GLib.idle_add(self.reload)

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool):
        for widget in (
            self.refresh_button,
            self.select_all_button,
            self.btn_launch,
            self.btn_update,
            self.btn_remove,
            self.btn_bulk_update,
            self.btn_bulk_remove,
            self.btn_bulk_clear,
        ):
            widget.set_sensitive(not busy)
        if busy:
            self.spinner.set_visible(True)
            self.spinner.start()
        else:
            self.spinner.stop()
            self.spinner.set_visible(False)
            # Re-apply per-selection sensitivity.
            self._on_selection_changed(self.selection, 0, 0)

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------
    def _on_drag_enter(self, _target, _x, _y):
        self.drop_box.set_visible(True)
        return Gdk.DragAction.COPY

    def _on_drag_motion(self, _target, _x, _y):
        self.drop_box.set_visible(True)
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, _target):
        self.drop_box.set_visible(False)

    def _on_drop(self, _target, value, _x, _y):
        self.drop_box.set_visible(False)
        paths = []
        try:
            if isinstance(value, Gdk.FileList):
                paths = [
                    f.get_path() for f in value.get_files() if f.get_path()
                ]
            elif isinstance(value, Gio.File):
                path = value.get_path()
                if path:
                    paths = [path]
        except Exception:  # noqa: BLE001
            paths = []
        if paths:
            self._install_paths(paths)
        return True

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _toast(self, text: str):
        self.toast_overlay.add_toast(Adw.Toast.new(text))

    def _show_error(self, heading: str, body: str):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=heading,
            body=body[:4000],
        )
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.connect("response", lambda dlg, _r: dlg.destroy())
        dialog.present()


class ManagerApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.props.active_window
        if not window:
            window = ManagerWindow(application=self)
        window.present()


def main() -> int:
    app = ManagerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
