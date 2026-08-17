test_files = files(
  'helpers.py',
  'run_tests.py',
  'test_desktop_entry.py',
  'test_import.py',
  'test_models.py',
  'test_persistence.py',
  'test_service.py',
  'test_ui.py',
)

test(
  'unit',
  py_installation,
  args: [files('run_tests.py')],
  depends: [],
  env: {
    'PYTHONPATH': meson.project_source_root() / 'src',
    'PYTHONDONTWRITEBYTECODE': '1',
  },
  suite: 'appimgify',
  timeout: 120,
)
