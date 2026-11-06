#!/bin/sh
set -eu
example=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
checkout=$(git -C "$example" rev-parse --show-toplevel)
revision=c92cbcaf281bea28e16146c3555d58a2d62edf03
build_context=$(mktemp -d)
trap 'rm -rf "$build_context"' EXIT HUP INT TERM
git -C "$checkout" archive --format=tar -o "$build_context/rea-source.tar" "$revision"
docker build -t rea-forge-recovery-base:v1 -f "$example/containers/Dockerfile.base" "$example/containers"
docker build -t rea-forge-recovery-rea:v1 -f "$example/containers/Dockerfile.rea" "$build_context"
docker build -t rea-forge-recovery-checker:v1 -f "$example/containers/Dockerfile.checker" "$example/containers"
