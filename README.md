# Appimgify

[![Build](https://github.com/Ezmanw/Appimgify/actions/workflows/build.yml/badge.svg)](https://github.com/Ezmanw/Appimgify/actions/workflows/build.yml)
[![Package](https://github.com/Ezmanw/Appimgify/actions/workflows/package.yml/badge.svg)](https://github.com/Ezmanw/Appimgify/actions/workflows/package.yml)

A native GTK 4 / Libadwaita AppImage manager for the Linux desktop.

Appimgify turns a downloaded AppImage into a properly integrated desktop
application. It copies the file into a managed folder, makes it executable,
reads the name, description and icon out of the bundle where it can, and writes
a valid `.desktop` launcher so the application shows up in the normal
applications menu — no manual file moving, `chmod`, or hand-written desktop
entries.

Everything happens inside your home directory. Appimgify never needs
administrator privileges.

---

## Features

**Importing**

- Add AppImages through the standard file chooser, by dropping them on the
  window, or by passing a path on the command line (`appimgify Foo.AppImage`).
- Files are validated by reading their ELF and AppImage headers, not by
  trusting the file extension.
- Metadata — name, generic name, description, version, categories, keywords,
  MIME types and the icon — is read out of the bundle where it exists.
- Large copies show progress and can be cancelled; a cancelled or failed import
  leaves nothing behind.
- Duplicates are detected and never silently overwritten.

**Managing**

- A searchable, sortable, category-filterable library of every managed
  application.
- Full launcher editor: name, description, icon, categories, arguments,
  working directory, terminal behaviour, startup notification, and the advanced
  desktop-entry options behind their own section.
- Reusable presets for launcher configuration (four are built in).
- Replace an AppImage with a newer version while keeping its configuration.
- Rebuild a launcher that was deleted or damaged, and repair a lost execute bit.
- Remove the AppImage, its launcher, or both — your original download is never
  touched.
- A "Check for Problems" action that finds missing files and leftover launchers.

**Fitting in**

- System font, system icon theme, standard GTK and Libadwaita widgets
  throughout. Appimgify ships no artwork of its own and never invents an icon
  for an AppImage that does not have one.
- System / Light / Dark appearance via `AdwStyleManager`.
- Adaptive layout, full keyboard navigation, accessible labels on every control.

---

## Supported desktop environments

Appimgify writes standard freedesktop.org desktop entries into
`~/.local/share/applications`, so it works with any standards-compliant desktop.

| Desktop | Status | Notes |
| --- | --- | --- |
| GNOME | Fully supported | New launchers appear within a few seconds |
| COSMIC | Fully supported | Standard XDG launcher directory is read |
| KDE Plasma | Works | Runs under GTK; menu picks entries up normally |
| Xfce, Cinnamon, MATE, Budgie | Works | Standard XDG behaviour |
| Sway, Hyprland, other wlroots | Works | Launcher visibility depends on your launcher (`wofi`, `fuzzel`, …) reading XDG entries |

Honest caveats:

- **When new entries appear varies.** GNOME and COSMIC notice new files in the
  launcher directory quickly. Some environments only rescan on login. If a new
  application does not appear, log out and back in.
- **Icon rendering varies.** Appimgify writes an absolute path in `Icon=`, which
  every major desktop supports. A small number of minimal launchers only accept
  themed icon names and will show a generic icon instead.
- **Sandboxed desktops.** If you run Appimgify inside a strict sandbox without
  access to `~/.local/share/applications`, launchers cannot be installed. Run it
  unsandboxed for full functionality.

---

## Installation

### From a release

Prebuilt packages are attached to every [release](https://github.com/Ezmanw/Appimgify/releases).
They are architecture-independent and take their GTK 4 and Libadwaita bindings
from your distribution.

**Debian, Ubuntu, Pop!\_OS**

```bash
sudo apt install ./appimgify_1.0.0_all.deb
```

**Fedora**

```bash
sudo dnf install ./appimgify-1.0.0-1.fc41.noarch.rpm
```

**Arch Linux**

```bash
sudo pacman -U ./appimgify-1.0.0-1-any.pkg.tar.zst
```

Each release ships a `SHA256SUMS` file:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

Every package is installed and imported inside CI before it is published, so a
package that lands in the wrong path fails the build rather than your machine.

### Dependencies

Runtime and build requirements:

| Component | Minimum version |
| --- | --- |
| Python | 3.10 |
| GTK | 4.12 |
| Libadwaita | 1.5 |
| PyGObject | 3.42 |
| Meson | 0.62 |
| Ninja | any recent |

Optional but recommended: **`squashfs-tools`**. When `unsquashfs` is present,
Appimgify reads metadata straight out of the AppImage's SquashFS payload
without executing anything. Without it, Appimgify falls back to the AppImage's
own `--appimage-extract` mechanism, which means running the bundle's runtime.

**Debian / Ubuntu / Pop!\_OS**

```bash
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-dev libgtk-4-dev meson ninja-build desktop-file-utils squashfs-tools
```

**Fedora**

```bash
sudo dnf install python3 python3-gobject gtk4-devel libadwaita-devel meson ninja-build desktop-file-utils squashfs-tools
```

**Arch Linux**

```bash
sudo pacman -S python python-gobject gtk4 libadwaita meson ninja desktop-file-utils squashfs-tools
```

**openSUSE Tumbleweed**

```bash
sudo zypper install python3 python3-gobject python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 gtk4-devel libadwaita-devel meson ninja desktop-file-utils squashfs
```

### Build and install

```bash
meson setup build --prefix=/usr/local
meson compile -C build
sudo meson install -C build
```

Then run `appimgify`, or launch **Appimgify** from your applications menu.

### Install without root

```bash
meson setup build --prefix="$HOME/.local"
meson install -C build
```

Make sure `~/.local/bin` is on your `PATH`.

### Uninstall

```bash
sudo ninja -C build uninstall
```

---

## Usage

1. Open Appimgify and click **Add**, or drop an AppImage onto the window.
2. Appimgify validates the file and reads what it can out of it.
3. Adjust the name, description, icon, categories and launch options. Applying
   a preset fills in the launcher options in one step.
4. Click **Install**.

The AppImage is copied into the managed folder, made executable, and a
`.desktop` launcher is generated. The application appears in your normal
applications menu.

Selecting an application in the library opens the same editor. Changes are
written when you press **Save**, which regenerates the launcher. The
application's menu (⋮) has **Open Location**, **Rebuild Launcher**, **Replace
AppImage…**, **Save Settings as Preset…** and **Remove…**.

### Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>N</kbd> | Add an AppImage |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> | Search |
| <kbd>Ctrl</kbd>+<kbd>,</kbd> | Preferences |
| <kbd>Ctrl</kbd>+<kbd>?</kbd> | Keyboard shortcuts |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit |

---

## Where things go

### AppImage storage

Managed AppImages live in `~/.local/share/appimages`, one directory per
application:

```text
~/.local/share/appimages/
├── Krita/
│   ├── Krita-5.2.2-x86_64.AppImage
│   └── icon.png
└── Inkscape/
    ├── Inkscape-1.3.AppImage
    └── icon.svg
```

The location is configurable in **Preferences → Storage**. Changing it affects
new imports only; existing applications stay where they are and keep working.

### Launchers

Generated launchers go into `~/.local/share/applications`, the standard
user-local desktop-entry directory. A generated entry looks like this:

```ini
[Desktop Entry]
Type=Application
Version=1.5
Name=Krita
Comment=Digital painting
Exec=/home/you/.local/share/appimages/Krita/Krita-5.2.2-x86_64.AppImage
TryExec=/home/you/.local/share/appimages/Krita/Krita-5.2.2-x86_64.AppImage
Icon=/home/you/.local/share/appimages/Krita/icon.png
Terminal=false
Categories=Graphics;
StartupNotify=true
X-Appimgify-Managed=true
X-Appimgify-Id=…
```

Paths are always the real ones for the current user. Paths containing spaces,
quotes, backslashes and other shell metacharacters are quoted and escaped
according to the Desktop Entry Specification — there are tests for exactly
this.

The `X-Appimgify-Id` key ties a launcher back to its library record. Appimgify
only ever deletes launchers carrying its own id, so a hand-written entry that
happens to share a file name is never removed.

### Configuration and data

| Path | Contents |
| --- | --- |
| `~/.config/appimgify/settings.json` | Preferences |
| `~/.config/appimgify/presets.json` | Your saved launcher presets |
| `~/.local/share/appimgify/library.json` | The record of every managed application |

All three are human-readable JSON and are written atomically. The library —
not the `.desktop` files — is the source of truth, which is what makes
"Rebuild Launcher" possible.

If one of these files is unreadable, Appimgify moves it aside as
`<name>.json.corrupt`, starts with clean state and tells you what happened.
Individual damaged records inside an otherwise valid library are skipped rather
than discarding the whole file.

---

## Troubleshooting

**The application does not appear in my menu.**
Your desktop may only rescan at login. Log out and back in. You can also check
that the entry exists:

```bash
ls ~/.local/share/applications/appimgify-*.desktop
```

**The launcher is there but does nothing.**
Use **Check for Problems** in the main menu. The most common causes are a
missing execute bit or a deleted AppImage; **Rebuild Launcher** fixes the
former, **Replace AppImage…** the latter.

**The AppImage will not start at all.**
Many AppImages need FUSE. Try running it directly to see the real error:

```bash
~/.local/share/appimages/YourApp/YourApp.AppImage
```

If it complains about FUSE, install `libfuse2` (Debian/Ubuntu) or `fuse2`
(Arch), or set `APPIMAGE_EXTRACT_AND_RUN=1` in the application's launch
arguments.

**No name, description or icon was detected.**
Not every AppImage bundles a desktop entry, and type 1 AppImages cannot be read
at all. Install `squashfs-tools` for the most reliable extraction, then fill in
the details yourself — Appimgify will not invent an icon for a bundle that does
not have one.

**Appimgify says the file is not an AppImage.**
It checks for an ELF header and the AppImage signature. A partially downloaded
file, an HTML error page saved with an `.AppImage` name, or an archive that has
not been extracted will all be rejected. Check the file size and re-download.

**I changed the AppImage folder and my applications disappeared from it.**
They did not move — changing the folder only affects new imports. Existing
applications keep pointing at their original location and still work.

---

## Development

### Running from a checkout

```bash
PYTHONPATH=src python3 -c "from appimgify.application import main; main([])"
```

### Debug build

```bash
meson setup build-debug --buildtype=debug --prefix="$PWD/build-debug/install"
meson compile -C build-debug
meson install -C build-debug
```

Useful environment variables while debugging:

```bash
GTK_DEBUG=interactive appimgify   # the GTK inspector
G_MESSAGES_DEBUG=all appimgify    # verbose GLib logging
```

### Release build

```bash
meson setup build --buildtype=release --prefix=/usr
meson compile -C build
DESTDIR=/path/to/staging meson install -C build
```

### Packaging

Packages build on every push, and a `v*` tag additionally publishes them to a
GitHub Release. The tag must match the version in `meson.build` or the workflow
stops before building anything.

To build a `.deb` locally:

```bash
packaging/build-deb.sh 1.0.0 dist
```

The `.rpm` and Arch package are built from `packaging/appimgify.spec.in` and
`packaging/PKGBUILD.in` in Fedora and Arch containers; see
`.github/workflows/package.yml`.

### Tests

```bash
meson test -C build --print-errorlogs
```

or, without Meson:

```bash
python3 tests/run_tests.py
```

The suite covers AppImage validation, metadata and settings serialisation,
import behaviour, duplicate handling, replacement, removal, desktop-entry
generation and escaping, persistence, and recovery from corrupted
configuration. Generated launchers are additionally checked with
`desktop-file-validate` when it is installed. Widget tests skip automatically
when no display is available — the suite skips them rather than failing, which
is what a distribution builder will hit.

### Project layout

```text
src/appimgify/
├── application/   AdwApplication, lifecycle, About
├── ui/            every GTK 4 / Libadwaita widget
├── services/      the façade the UI drives, plus background-task plumbing
├── appimages/     validation, the managed store, the import pipeline
├── metadata/      reading names, descriptions and icons out of AppImages
├── desktop/       .desktop generation and installation
├── persistence/   library, settings and preset files
├── models/        plain data types
└── utils/         paths, filesystem primitives, error types
```

Nothing below `services/` imports GTK, so the whole pipeline is testable
without a display and safe to run on worker threads. `desktop/entry.py` is pure
— it turns a `ManagedApp` into text and touches nothing else — which is why it
can be tested exhaustively.

`desktop/installer.py` defines a `LauncherBackend` protocol. Supporting another
launcher format later means adding a class beside `DesktopEntryInstaller`, not
rewriting the application.

---

## Known limitations

- **Type 1 AppImages cannot be inspected.** They are still imported and
  launched correctly, but the name, description and icon must be entered by
  hand.
- **Extraction without `squashfs-tools` runs the bundle.** The fallback path
  invokes the AppImage's own runtime with `--appimage-extract`. This is the
  format's documented mechanism, but it does execute code from a file you just
  downloaded. Install `squashfs-tools` to avoid it.
- **No update checking.** Appimgify does not query AppImageUpdate, zsync or any
  release feed. Replacing an AppImage is a manual action.
- **No AppStream metadata parsing.** `usr/share/metainfo` is extracted but only
  the desktop entry is read from it.
- **One import at a time.** Dropping several files starts the flow for the
  first one only.
- **Moving the AppImage folder does not migrate existing applications.** This
  is deliberate — moving files out from under running launchers would be worse
  than leaving them.
- **Desktop-menu refresh timing is outside Appimgify's control.** See the
  desktop environment table above.

---

## License

GPL-3.0-or-later.
