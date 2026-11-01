#!/bin/sh
# Build Debian trixie arm64 base rootfs on the VM (invoked via systemd-run).
set -e
export DEBIAN_FRONTEND=noninteractive
rm -rf /srv/debport/rootfs
mkdir -p /srv/debport
exec /tmp/mm/ext/usr/bin/mmdebstrap --arch=arm64 --variant=minbase \
  --include="systemd,systemd-sysv,dbus,dbus-user-session,network-manager,openssh-server,sudo,locales,fake-hwclock,ca-certificates,curl,zstd,xz-utils,less,vim-tiny,python3,kmod,udev,procps,iproute2,iputils-ping,apt-utils,debian-archive-keyring" \
  trixie /srv/debport/rootfs \
  "deb [trusted=yes] http://mirrors.aliyun.com/debian trixie main contrib non-free-firmware"
