#!/usr/bin/env bash
# TEST-ONLY: this is NOT an isolation boundary; real operation must use bwrap.
while [ "${1:-}" != -- ]; do [ "$#" -gt 0 ] || exit 90; shift; done
shift
exec "$@"
