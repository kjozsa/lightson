#!/usr/bin/env fish

uv pip install -e . --quiet
systemctl --user restart lightson
systemctl --user status lightson --no-pager
