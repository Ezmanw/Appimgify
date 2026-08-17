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

install_subdir(
  'appimgify',
  install_dir: py_installation.get_install_dir(),
  exclude_directories: [
    '__pycache__',
    'application/__pycache__',
    'appimages/__pycache__',
    'desktop/__pycache__',
    'metadata/__pycache__',
    'models/__pycache__',
    'persistence/__pycache__',
    'services/__pycache__',
    'ui/__pycache__',
    'utils/__pycache__',
  ],
)
