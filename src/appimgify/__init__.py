"""Appimgify — a native AppImage manager and launcher for the Linux desktop.

Layering, outermost first::

    ui          GTK 4 / Libadwaita widgets
    services    the façade the UI talks to, plus background-task plumbing
    appimages   validation, the managed store and the import pipeline
    metadata    reading names, descriptions and icons out of AppImages
    desktop     generating and installing .desktop launchers
    persistence the library, settings and preset files
    models      plain data types
    utils       paths, filesystem primitives and error types

Everything below ``services`` is free of GTK, so it can be tested without a
display and used from worker threads.
"""

__version__ = "1.0.0"
