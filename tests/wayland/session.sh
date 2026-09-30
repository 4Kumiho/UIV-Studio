#!/usr/bin/env bash
# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.
# Start a headless GNOME Wayland session (mutter) with PipeWire, then run "$@" inside it.
set -e
export XDG_RUNTIME_DIR=/tmp/xdg-runtime; mkdir -p -m 700 "$XDG_RUNTIME_DIR"
mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME
# Headless container: no audio/camera/bluetooth hardware -> disable WirePlumber device monitors
mkdir -p "$HOME/.config/wireplumber/main.lua.d" "$HOME/.config/wireplumber/bluetooth.lua.d"
cat > "$HOME/.config/wireplumber/main.lua.d/99-headless.lua" <<'LUA'
alsa_monitor.enabled = false
v4l2_monitor.enabled = false
libcamera_monitor.enabled = false
LUA
echo 'bluez_monitor.enabled = false' > "$HOME/.config/wireplumber/bluetooth.lua.d/99-headless.lua"
exec dbus-run-session -- bash -c '
  pipewire >/tmp/pipewire.log 2>&1 &
  for i in $(seq 1 50); do [ -S "$XDG_RUNTIME_DIR/pipewire-0" ] && break; sleep 0.1; done
  sleep 0.5
  # only the session-manager parts we need (no bluetooth/logind in a container)
  wireplumber -c main.conf >>/tmp/wireplumber.log 2>&1 &
  wireplumber -c policy.conf >>/tmp/wireplumber.log 2>&1 &
  (G_MESSAGES_DEBUG=${UIV_MUTTER_DEBUG:-} mutter --headless --wayland ${UIV_MUTTER_X11:---no-x11} --virtual-monitor ${UIV_MONITOR:-1280x800}; echo "mutter exited with code $?") >/tmp/mutter.log 2>&1 &
  for i in $(seq 1 100); do [ -S "$XDG_RUNTIME_DIR/wayland-0" ] && break; sleep 0.1; done
  export WAYLAND_DISPLAY=wayland-0
  "$@"
' bash "$@"
