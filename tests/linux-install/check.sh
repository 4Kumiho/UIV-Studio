#!/usr/bin/env bash
# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.
# Runs inside a clean distro container: installs the baseline every desktop has
# (X11 client libs, OpenGL, fontconfig, glib, dbus), then installs UIV Studio
# exactly like a user does, under a virtual display, and checks it starts.
set -u
. /etc/os-release
echo "=== $PRETTY_NAME (glibc $(ldd --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+$'))"
case "$ID ${ID_LIKE:-}" in
  *debian*|*ubuntu*)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null && apt-get install -y -qq curl ca-certificates xvfb procps libgl1 libegl1 \
      libfontconfig1 libglib2.0-0 libdbus-1-3 libx11-6 libx11-xcb1 libxkbcommon0 libxkbcommon-x11-0 libxrender1 \
      libxi6 libxext6 libxtst6 libxcb-randr0 libxcb-shape0 libxcb-xfixes0 libxcb-sync1 libxcb-shm0 >/dev/null ;;
  *fedora*|*rhel*|*centos*)
    dnf -y -q --setopt=sslverify=False install curl xorg-x11-server-Xvfb procps-ng mesa-libGL mesa-libEGL fontconfig glib2 dbus-libs \
      libX11 libX11-xcb libxkbcommon libxkbcommon-x11 libXrender libXi libXext libXtst >/dev/null ;;
  *suse*)
    zypper -n -q install curl xvfb-run xorg-x11-server-Xvfb procps Mesa-libGL1 Mesa-libEGL1 fontconfig \
      libglib-2_0-0 libdbus-1-3 libX11-6 libX11-xcb1 libxkbcommon0 libxkbcommon-x11-0 libXrender1 libXi6 libXext6 libXtst6 >/dev/null ;;
  *arch*)
    pacman -Syu --noconfirm --needed -q curl xorg-server-xvfb procps-ng mesa fontconfig glib2 dbus libx11 \
      libxkbcommon libxkbcommon-x11 libxrender libxi libxext libxtst >/dev/null ;;
esac
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
export DISPLAY=:99
sleep 2
mkdir -p /home/user/UIV && cp /src/installa-uiv-studio.sh /home/user/UIV/ && cd /home/user/UIV
[ -f "/src/build/linux-test/UIV Studio" ] && export UIV_URL="file:///src/build/linux-test/UIV%20Studio" && echo "(testing local build)"
if ! sh installa-uiv-studio.sh >/tmp/install.log 2>&1; then echo "RESULT FAIL: installer script"; tail -5 /tmp/install.log; exit 1; fi
[ -x "UIV Studio" ] && echo "ok  executable downloaded ($(du -m 'UIV Studio' | cut -f1) MB)" || { echo "RESULT FAIL: no executable"; exit 1; }
for i in $(seq 1 120); do ls .uivstudio/*/.complete >/dev/null 2>&1 && break; sleep 1; done
ls .uivstudio/*/.complete >/dev/null 2>&1 && echo "ok  first-run install done (${i}s)" || { echo "RESULT FAIL: first-run extraction"; ls -la .uivstudio 2>&1 | head; exit 1; }
sleep 15
if pgrep -f ".uivstudio/.*/UIV Studio" >/dev/null; then
  echo "RESULT PASS: UIV Studio is running"
else
  echo "RESULT FAIL: app not running"
  APP=$(ls -d .uivstudio/*/ | head -1)
  timeout 20 "$APP/UIV Studio" 2>&1 | grep -v "^$" | tail -12
fi
