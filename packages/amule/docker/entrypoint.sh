#!/bin/sh
set -eu

python -m p2pwatch_amule.adapters.driving.boot

exec s6-svscan /etc/services.d
