# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

# GNOME Wayland test bench: headless mutter (same compositor as GNOME Shell) + XWayland + PipeWire.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        mutter xwayland dbus dbus-x11 xdg-desktop-portal xdg-desktop-portal-gnome pipewire wireplumber gstreamer1.0-pipewire gstreamer1.0-tools \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good libxkbcommon0 libxkbcommon-x11-0 \
        libgl1 libegl1 libglib2.0-0 libfontconfig1 libdbus-1-3 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 \
        libxcb-xkb1 libx11-xcb1 libxrender1 libxi6 libxtst6 libwayland-cursor0 libwayland-egl1 \
        fonts-dejavu-core python3 python3-venv python3-pip python3-dev build-essential linux-libc-dev ca-certificates kmod \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install -q --upgrade pip \
    && /opt/venv/bin/pip install -q -r /tmp/requirements.txt \
    && /opt/venv/bin/pip uninstall -y -q opencv-python \
    && /opt/venv/bin/pip install -q --force-reinstall --no-deps opencv-python-headless
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/src
