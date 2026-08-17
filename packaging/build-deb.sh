#!/usr/bin/env bash
#
# Build a binary .deb from a Meson install.
#
# The package is architecture-independent: Appimgify is pure Python plus data
# files, and the GTK bindings come from the distribution's own packages.
#
# Usage: packaging/build-deb.sh <version> <output-directory>

set -euo pipefail

VERSION="${1:?usage: build-deb.sh <version> <output-directory>}"
OUTPUT_DIR="${2:?usage: build-deb.sh <version> <output-directory>}"

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$(mktemp -d)"
STAGE_DIR="${BUILD_DIR}/stage"
trap 'rm -rf "${BUILD_DIR}"' EXIT

echo "==> Building Appimgify ${VERSION} for Debian"
meson setup "${BUILD_DIR}/meson" "${SOURCE_ROOT}" \
  --prefix=/usr \
  --buildtype=release
meson compile -C "${BUILD_DIR}/meson"
DESTDIR="${STAGE_DIR}" meson install -C "${BUILD_DIR}/meson"

# Meson's post-install hook updates the *build machine's* desktop database.
# Anything it leaves in the staging tree belongs to the distribution, not us.
rm -rf "${STAGE_DIR}/usr/share/applications/mimeinfo.cache"

install -Dm644 "${SOURCE_ROOT}/LICENSE" \
  "${STAGE_DIR}/usr/share/doc/appimgify/copyright"
install -Dm644 "${SOURCE_ROOT}/README.md" \
  "${STAGE_DIR}/usr/share/doc/appimgify/README.md"

INSTALLED_SIZE="$(du -ks "${STAGE_DIR}" | cut -f1)"

mkdir -p "${STAGE_DIR}/DEBIAN"
cat > "${STAGE_DIR}/DEBIAN/control" <<EOF
Package: appimgify
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: The Appimgify Contributors <noreply@github.com>
Installed-Size: ${INSTALLED_SIZE}
Depends: python3 (>= 3.10), python3-gi (>= 3.42), gir1.2-gtk-4.0 (>= 4.12), gir1.2-adw-1 (>= 1.5)
Recommends: squashfs-tools, desktop-file-utils
Homepage: https://github.com/Ezmanw/Appimgify
Description: Manage AppImages and their application menu launchers
 Appimgify turns a downloaded AppImage into a properly integrated desktop
 application. It copies the file into a managed folder, makes it executable,
 reads the name, description and icon out of the bundle where it can, and
 writes a valid desktop entry so the application appears in the normal
 applications menu.
 .
 Everything happens inside the user's home directory; no administrator
 privileges are required.
EOF

# Bytecode is generated on the target machine, against the interpreter that
# will actually import it, rather than being baked into the package.
cat > "${STAGE_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ] && command -v py3compile >/dev/null 2>&1; then
    py3compile /usr/lib/python3/dist-packages/appimgify || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF

cat > "${STAGE_DIR}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if command -v py3clean >/dev/null 2>&1; then
    py3clean /usr/lib/python3/dist-packages/appimgify || true
fi
exit 0
EOF

chmod 0755 "${STAGE_DIR}/DEBIAN/postinst" "${STAGE_DIR}/DEBIAN/prerm"

mkdir -p "${OUTPUT_DIR}"
PACKAGE="${OUTPUT_DIR}/appimgify_${VERSION}_all.deb"
fakeroot dpkg-deb --build --root-owner-group "${STAGE_DIR}" "${PACKAGE}"

echo "==> Built ${PACKAGE}"
dpkg-deb --info "${PACKAGE}"
dpkg-deb --contents "${PACKAGE}"
