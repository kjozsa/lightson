#!/usr/bin/env fish

set HOST "pi@rpi5"
set PROJECT_DIR "/srv/lightson"

set HOSTNAME (hostname)
if test "$HOSTNAME" = "rpi5"
    echo "Running locally on $HOSTNAME - deploying..."

    git stash
    git pull
    uv sync --frozen

    systemctl --user restart lightson
    systemctl --user status lightson --no-pager
else
    echo "Running remotely - deploying to $HOST..."

    ssh $HOST "cd $PROJECT_DIR && git pull"
    ssh $HOST "cd $PROJECT_DIR && uv sync --frozen"
    ssh $HOST "systemctl --user restart lightson && systemctl --user status lightson --no-pager"
end

echo "Done."
