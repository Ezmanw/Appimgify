data_conf = configuration_data()
data_conf.set('APP_ID', application_id)
data_conf.set('VERSION', meson.project_version())

desktop_file = configure_file(
  input: 'io.github.ezmanw.Appimgify.desktop.in',
  output: application_id + '.desktop',
  configuration: data_conf,
  install: true,
  install_dir: datadir / 'applications',
)

metainfo_file = configure_file(
  input: 'io.github.ezmanw.Appimgify.metainfo.xml.in',
  output: application_id + '.metainfo.xml',
  configuration: data_conf,
  install: true,
  install_dir: datadir / 'metainfo',
)

# Validate the files we ship, when the validators are available.
desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test(
    'validate-desktop-file',
    desktop_file_validate,
    args: [desktop_file],
    suite: 'data',
  )
endif

appstream_util = find_program('appstreamcli', required: false)
if appstream_util.found()
  test(
    'validate-metainfo',
    appstream_util,
    args: ['validate', '--no-net', '--explain', metainfo_file],
    suite: 'data',
  )
endif
