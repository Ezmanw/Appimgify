launcher_conf = configuration_data()
launcher_conf.set('PYTHON', py_installation.full_path())
launcher_conf.set('PYTHON_DIR', py_installation.get_install_dir())
launcher_conf.set('VERSION', meson.project_version())

configure_file(
  input: 'appimgify.in',
  output: 'appimgify',
  configuration: launcher_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

# Sources are listed explicitly rather than installed with install_subdir.
# Globbing a directory would sweep up whatever happens to be sitting in the
# tree — most obviously __pycache__ — and ship bytecode compiled for the build
# machine's interpreter inside every distribution package.
python_sources = {
  'appimgify': files(
    'appimgify/__init__.py',
    'appimgify/gi_versions.py',
  ),
  'appimgify/appimages': files(
    'appimgify/appimages/__init__.py',
    'appimgify/appimages/importer.py',
    'appimgify/appimages/storage.py',
    'appimgify/appimages/validator.py',
  ),
  'appimgify/application': files(
    'appimgify/application/__init__.py',
    'appimgify/application/about.py',
    'appimgify/application/application.py',
  ),
  'appimgify/desktop': files(
    'appimgify/desktop/__init__.py',
    'appimgify/desktop/entry.py',
    'appimgify/desktop/installer.py',
  ),
  'appimgify/metadata': files(
    'appimgify/metadata/__init__.py',
    'appimgify/metadata/desktop_parser.py',
    'appimgify/metadata/extractor.py',
    'appimgify/metadata/icons.py',
  ),
  'appimgify/models': files(
    'appimgify/models/__init__.py',
    'appimgify/models/categories.py',
    'appimgify/models/managed_app.py',
    'appimgify/models/metadata.py',
    'appimgify/models/preset.py',
  ),
  'appimgify/persistence': files(
    'appimgify/persistence/__init__.py',
    'appimgify/persistence/config.py',
    'appimgify/persistence/library.py',
    'appimgify/persistence/presets_store.py',
  ),
  'appimgify/services': files(
    'appimgify/services/__init__.py',
    'appimgify/services/library_service.py',
    'appimgify/services/tasks.py',
  ),
  'appimgify/ui': files(
    'appimgify/ui/__init__.py',
    'appimgify/ui/app_row.py',
    'appimgify/ui/detail.py',
    'appimgify/ui/dialogs.py',
    'appimgify/ui/editor.py',
    'appimgify/ui/iconview.py',
    'appimgify/ui/import_dialog.py',
    'appimgify/ui/preferences.py',
    'appimgify/ui/shortcuts.py',
    'appimgify/ui/window.py',
  ),
  'appimgify/utils': files(
    'appimgify/utils/__init__.py',
    'appimgify/utils/errors.py',
    'appimgify/utils/fileutils.py',
    'appimgify/utils/paths.py',
  ),
}

foreach module_path, module_sources : python_sources
  py_installation.install_sources(module_sources, subdir: module_path)
endforeach
