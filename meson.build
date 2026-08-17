project(
  'appimgify',
  version: '1.0.0',
  license: 'GPL-3.0-or-later',
  meson_version: '>= 0.62.0',
  default_options: [
    'warning_level=2',
    # Never ship bytecode built here: a .pyc compiled against the build
    # machine's interpreter is wrong for any other Python version. Each
    # distribution's packaging tools byte-compile at the right moment.
    'python.bytecompile=-1',
  ],
)

application_id = 'io.github.ezmanw.Appimgify'

gnome = import('gnome')
python = import('python')

py_installation = python.find_installation('python3')
if not py_installation.found()
  error('python3 is required to build and run Appimgify')
endif

# Runtime dependencies. These are checked at configure time so a missing
# library is reported here rather than as a traceback on first launch.
dependency('glib-2.0', version: '>= 2.72')
dependency('gtk4', version: '>= 4.12')
dependency('libadwaita-1', version: '>= 1.5')
dependency('pygobject-3.0', version: '>= 3.42', required: false)

prefix = get_option('prefix')
bindir = prefix / get_option('bindir')
datadir = prefix / get_option('datadir')

subdir('src')
subdir('data')
subdir('tests')

gnome.post_install(
  update_desktop_database: true,
  gtk_update_icon_cache: false,
)

summary(
  {
    'prefix': prefix,
    'bindir': bindir,
    'python modules': py_installation.get_install_dir(),
    'application id': application_id,
  },
  section: 'Installation',
)
