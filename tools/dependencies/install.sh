#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

[ -n "${DEBUG:-}" ] && set -x
SCRIPT_DIR="$(
    cd "$(dirname "$0")" >/dev/null
    pwd
)"

usage() {
    echo "Usage:
    ${0##*/} [options]

Optional arguments:
    -d, --debug
        Activate tracing/debug mode.
    -h, --help
        Display this message.

Example:
    ${0##*/}
" >&2
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
        -d | --debug)
            set -x
            DEBUG="--debug"
            export DEBUG
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            usage
            echo "[ERROR] Unknown argument: $1"
            exit 1
            ;;
        esac
        shift
    done
}

npm_deps() {
    npm install --global \
        ergogen \
        shellcheck
}

python_deps() {
    curl -LsSf https://astral.sh/uv/install.sh | sh
    cd "$SCRIPT_DIR/python"
    uv sync
    cd -
}

action() {
    npm_deps
    python_deps
}

main() {
    parse_args "$@"
    action
}

if [ "${BASH_SOURCE[0]}" == "$0" ]; then
    main "$@"
fi