common_deps = [gobject_dep, gio_dep, wp_dep, pipewire_dep]
common_env = common_test_env
common_env.set('G_TEST_SRCDIR', meson.current_source_dir())
common_env.set('G_TEST_BUILDDIR', meson.current_build_dir())

if get_option('dbus-tests')
  test(
    'test-dbus-connection',
    executable('test-dbus-connection', 'dbus-connection.c',
        dependencies: common_deps),
    env: common_env,
  )

  test(
    'test-reserve-device',
    executable('test-reserve-device', 'reserve-device.c',
      dependencies: common_deps),
    env: common_env,
  )
endif

test(
  'test-file-monitor',
  executable('test-file-monitor', 'file-monitor.c',
    dependencies: common_deps),
  env: common_env,
)

test(
  'test-si-node',
  executable('test-si-node', 'si-node.c',
      dependencies: common_deps),
  env: common_env,
)

test(
  'test-si-audio-adapter',
  executable('test-si-audio-adapter', 'si-audio-adapter.c',
      dependencies: common_deps),
  env: common_env,
)

test(
  'test-si-standard-link',
  executable('test-si-standard-link', 'si-standard-link.c',
      dependencies: common_deps),
  env: common_env,
)
