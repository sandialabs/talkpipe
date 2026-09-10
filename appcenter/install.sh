#!/bin/sh
# Open the TalkPipe App Center with one command:
#
#   curl -fsSL https://github.com/sandialabs/talkpipe/releases/latest/download/install.sh | sh
#
# Add arguments after `sh -s --` to skip the screen and act directly, e.g.
#
#   curl -fsSL .../install.sh | sh -s -- install vault
#
# What it does: installs uv (https://docs.astral.sh/uv/) into ~/.local/bin if it
# is missing, then hands over to the App Center itself, one Python file that uv runs
# in its own cached environment:
#
#   uv run https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py
#
# uv is the only thing this script installs. The App Center installs applications
# with `uv tool install`, each into its own environment; nothing else on the
# machine is touched.
set -eu

APPCENTER_URL="https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py"

download() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$1"
    else
        echo "Error: this script needs curl or wget." >&2
        exit 1
    fi
}

main() {
    local_bin="$HOME/.local/bin"
    echo "==> [1/2] Checking for uv, the Python package manager the App Center uses"
    if command -v uv >/dev/null 2>&1; then
        uv="$(command -v uv)"
        echo "Found uv at $uv."
    elif [ -x "$local_bin/uv" ]; then
        uv="$local_bin/uv"
        echo "Found uv at $uv."
    else
        echo "Not found. Downloading it from astral.sh into $local_bin..."
        download https://astral.sh/uv/install.sh | sh -s -- --quiet
        uv="$local_bin/uv"
        if [ ! -x "$uv" ]; then
            echo "Error: uv did not install to $uv; see https://docs.astral.sh/uv/getting-started/installation/" >&2
            exit 1
        fi
        echo "Installed uv."
    fi

    echo "==> [2/2] Starting the TalkPipe App Center"
    echo "(the first run fetches its Python and one library; later runs are quick)"
    # `curl ... | sh` leaves stdin connected to the pipe, not the keyboard; the
    # App Center's screen needs the terminal, so reattach stdin to it when we can.
    if [ ! -t 0 ] && [ -r /dev/tty ]; then
        exec "$uv" run "$APPCENTER_URL" "$@" </dev/tty
    fi
    exec "$uv" run "$APPCENTER_URL" "$@"
}

main "$@"
