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

init() {
    PROJECT_DIR="$(
        cd "$(dirname "$SCRIPT_DIR")" >/dev/null
        pwd
    )"
    cd "$PROJECT_DIR"
    ERGOGEN_DIR="$PROJECT_DIR/board/ergogen"
    ERGOGEN_OUTPUT_DIR="$ERGOGEN_DIR/output"
}

h1() {
    echo "
################################################################################
# $*
################################################################################
"
}

build() {
    h1 "Compiling Ergogen config"
    mkdir -p "$ERGOGEN_OUTPUT_DIR"
    touch "$ERGOGEN_OUTPUT_DIR"

    ergogen --output "$ERGOGEN_OUTPUT_DIR" "$ERGOGEN_DIR/config"
    echo ""
}

render_dxf() {
    h1 "Rendering DXF"
    cd "$PROJECT_DIR/tools/dependencies/python"
    for DXF in $(find "$ERGOGEN_OUTPUT_DIR/" -name \*.dxf | sort); do
        IMAGE="${DXF/.dxf/.png}"
        uv run ezdxf draw --force --out "$IMAGE" "$DXF"
    done
    cd - >/dev/null
    echo
}

clean_up() {
    find "$ERGOGEN_OUTPUT_DIR" ! -newer "$ERGOGEN_OUTPUT_DIR" -type f -delete
}

action() {
    build
    render_dxf
    clean_up
}

main() {
    parse_args "$@"
    init
    action
}

if [ "${BASH_SOURCE[0]}" == "$0" ]; then
    main "$@"
fi