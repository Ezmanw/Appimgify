"""Desktop-entry generation.

This module is intentionally free of GTK, filesystem and application state: it
turns a :class:`~appimgify.models.managed_app.ManagedApp` into desktop-entry
text and nothing else, which makes it directly unit testable — including the
awkward cases of paths containing spaces, quotes and backslashes.

Escaping follows the freedesktop.org Desktop Entry Specification, which layers
two rules on top of each other for ``Exec``:

1. *quoting* — arguments containing reserved characters are wrapped in double
   quotes, with ``"``, ``` ` ```, ``$`` and ``\\`` backslash-escaped;
2. *value escaping* — the resulting string is then escaped as a normal value,
   which doubles every backslash again.

Applying them in that order is what makes a literal backslash appear as four
backslashes in the file, exactly as the specification requires.
"""

from __future__ import annotations

from pathlib import Path

from ..models.managed_app import ManagedApp
from ..utils.paths import APP_ID, slugify

#: Characters that force an ``Exec`` argument to be quoted.
RESERVED_EXEC_CHARS = frozenset(' \t\n"\'\\><~|&;$*?#()`')

#: Key used to tie a launcher back to its library record.
TRACKING_KEY = "X-Appimgify-Id"


def escape_value(text: str) -> str:
    """Escape a plain desktop-entry ``string``/``localestring`` value."""
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def quote_exec_argument(argument: str) -> str:
    """Apply the specification's ``Exec`` quoting rule to one argument."""
    if argument and not any(char in RESERVED_EXEC_CHARS for char in argument):
        return argument.replace("%", "%%")
    escaped = "".join(
        "\\" + char if char in ('"', "`", "$", "\\") else char for char in argument
    )
    return '"' + escaped.replace("%", "%%") + '"'


def build_exec(program: str | Path, arguments: list[str] | None = None) -> str:
    """Build a fully quoted ``Exec`` value (before value escaping)."""
    parts = [quote_exec_argument(str(program))]
    parts.extend(quote_exec_argument(argument) for argument in arguments or [])
    return " ".join(parts)


def _format_list(values: list[str]) -> str:
    """Render a desktop-entry list value (semicolon separated, trailing ``;``)."""
    cleaned = [value.replace(";", r"\;") for value in values if value]
    if not cleaned:
        return ""
    return ";".join(cleaned) + ";"


def desktop_file_name(app: ManagedApp) -> str:
    """Stable launcher file name for an application.

    The explicit ``desktop_file_name`` set in the editor wins; otherwise the
    name is derived from the application name and namespaced so Appimgify's
    launchers can never collide with a distribution package's.
    """
    if app.desktop_file_name:
        stem = app.desktop_file_name
        if stem.endswith(".desktop"):
            stem = stem[: -len(".desktop")]
        stem = slugify(stem, fallback=f"appimgify-{app.id[:8]}")
        return f"{stem}.desktop"
    slug = slugify(app.name, fallback=app.id[:8])
    return f"appimgify-{slug}.desktop".lower()


def render(app: ManagedApp) -> str:
    """Render the complete ``.desktop`` file contents for ``app``.

    Raises:
        ValueError: if the application has no name or no AppImage path — the
            two fields without which no valid entry can exist.
    """
    if not app.name.strip():
        raise ValueError("a desktop entry needs a non-empty Name")
    if not app.appimage_path.strip():
        raise ValueError("a desktop entry needs an executable path")

    lines: list[str] = ["[Desktop Entry]", "Type=Application", "Version=1.5"]
    pairs: list[tuple[str, str]] = [
        ("Name", escape_value(app.name.strip())),
        ("GenericName", escape_value(app.generic_name.strip())),
        ("Comment", escape_value(app.description.strip())),
        ("Exec", escape_value(build_exec(app.appimage_path, app.arguments))),
        ("TryExec", escape_value(app.appimage_path)),
        ("Icon", escape_value(_icon_value(app))),
        ("Path", escape_value(app.working_directory.strip())),
        ("Terminal", "true" if app.terminal else "false"),
        ("Categories", escape_value(_format_list(app.categories))),
        ("Keywords", escape_value(_format_list(app.keywords))),
        ("MimeType", escape_value(_format_list(app.mime_types))),
    ]
    for key, value in pairs:
        if value:
            lines.append(f"{key}={value}")

    lines.append("StartupNotify=" + ("true" if app.startup_notify else "false"))
    if app.single_main_window:
        lines.append("SingleMainWindow=true")
    if app.no_display:
        lines.append("NoDisplay=true")
    if app.version.strip():
        lines.append(f"X-AppImage-Version={escape_value(app.version.strip())}")
    lines.append("X-Appimgify-Managed=true")
    lines.append(f"{TRACKING_KEY}={escape_value(app.id)}")
    lines.append(f"X-Appimgify-Source={escape_value(APP_ID)}")
    return "\n".join(lines) + "\n"


def _icon_value(app: ManagedApp) -> str:
    """``Icon`` value: an absolute path when we have one, else a themed name."""
    if app.icon_path:
        return app.icon_path
    return ""
