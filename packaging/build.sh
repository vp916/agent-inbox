#!/bin/sh
# Build the release files into dist/ from the committed HEAD:
#   agent-inbox-<v>.tar.gz              source, any distro (python3 install.py install)
#   agent-inbox-<v>-1-any.pkg.tar.zst   Arch       (makepkg, run on an Arch host)
#   agent-inbox-<v>-1.noarch.rpm        Fedora     (built in a fedora container)
#   agent-inbox_<v>-1_all.deb           Debian / Ubuntu (built in a debian container)
# Needs git, makepkg and docker. The version is pkgver in packaging/aur/PKGBUILD.
set -eu
cd "$(dirname "$0")/.."
V=$(sed -n 's/^pkgver=//p' packaging/aur/PKGBUILD)
grep -q "^Version: *$V\$" packaging/rpm/agent-inbox.spec || { echo "spec version is not $V" >&2; exit 1; }
grep -q "download/v$V/agent-inbox_$V-1_all.deb" README.md || echo "note: the README install links are not at $V yet" >&2
[ -z "$(git status --porcelain -- bin daemon hook ui install.py)" ] || { echo "commit your changes first" >&2; exit 1; }

D=$PWD/dist
rm -rf "$D" && mkdir -p "$D"
TAR=agent-inbox-$V.tar.gz
git archive --format=tar.gz --prefix="agent-inbox-$V/" -o "$D/$TAR" HEAD

# Arch: the PKGBUILD downloads the tag's tarball; hand it the local one instead
B=$(mktemp -d)
cp packaging/aur/PKGBUILD packaging/aur/agent-inbox.install "$D/$TAR" "$B/"
(cd "$B" && PKGDEST="$D" makepkg -f --skipchecksums --noconfirm >/dev/null)
rm -rf "$B"

# Fedora
docker run --rm -v "$D:/out" -v "$PWD/packaging/rpm:/spec:ro" fedora:latest sh -ec "
  dnf -q -y install rpm-build >/dev/null
  mkdir -p /root/rpmbuild/SOURCES && cp /out/$TAR /root/rpmbuild/SOURCES/
  rpmbuild -bb --quiet /spec/agent-inbox.spec
  cp /root/rpmbuild/RPMS/noarch/*.rpm /out/
  chown $(id -u):$(id -g) /out/*.rpm"
R=$(sed -n 's/^Release: *\([0-9]*\).*/\1/p' packaging/rpm/agent-inbox.spec)
for f in "$D"/*.fc*.noarch.rpm; do mv "$f" "$D/agent-inbox-$V-$R.noarch.rpm"; done

# Debian / Ubuntu
docker run --rm -v "$D:/out" -v "$PWD/packaging/deb:/deb:ro" debian:trixie sh -ec "
  R=/tmp/root; mkdir -p \$R/DEBIAN \$R/usr/share/agent-inbox \$R/usr/bin \$R/usr/share/doc/agent-inbox
  tar -xzf /out/$TAR -C /tmp
  S=/tmp/agent-inbox-$V
  cp -r \$S/bin \$S/daemon \$S/hook \$S/ui \$S/install.py \$R/usr/share/agent-inbox/
  ln -s /usr/share/agent-inbox/bin/agent-inbox \$R/usr/bin/agent-inbox
  ln -s /usr/share/agent-inbox/install.py \$R/usr/bin/agent-inbox-setup
  cp \$S/README.md \$S/CHANGELOG.md \$R/usr/share/doc/agent-inbox/
  cp \$S/LICENSE \$R/usr/share/doc/agent-inbox/copyright
  sed 's/@VERSION@/$V/' /deb/control > \$R/DEBIAN/control
  install -m755 /deb/postinst \$R/DEBIAN/postinst
  dpkg-deb --root-owner-group --build \$R /out/agent-inbox_${V}-1_all.deb >/dev/null
  chown $(id -u):$(id -g) /out/*.deb"

ls -l "$D"
