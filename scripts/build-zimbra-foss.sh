#!/usr/bin/env bash
# Run in a dedicated build VM with Zimbra's documented build dependencies installed.
set -euo pipefail
version=10.1.21
commit=f40c9007407061e74d48cc19a208b0cbfb9685ec
build_dir=${ZIMBRA_BUILD_DIR:-$PWD/zimbra-foss-build}
mkdir -p "$build_dir"
if [[ ! -d "$build_dir/zm-build/.git" ]]; then
  git clone --branch "$version" https://github.com/Zimbra/zm-build.git "$build_dir/zm-build"
fi
cd "$build_dir/zm-build"
[[ $(git rev-parse HEAD) == "$commit" ]] || { echo 'Unexpected zm-build revision; review it before building.' >&2; exit 1; }
# Component repositories do not all receive a new tag for every patch.
# Resolve the newest available tag at or below the selected release.
tags="$version"
for ((patch=20;patch>=0;patch--)); do tags+=",10.1.$patch"; done
for ((patch=13;patch>=0;patch--)); do tags+=",10.0.$patch"; done
tags+=",10.0.0-GA"
ENV_CACHE_CLEAR_FLAG=true ./build.pl \
  --git-default-tag="$tags" --build-release-no="$version" \
  --build-type=FOSS --build-release=DAFFODIL --build-release-candidate=GA \
  --build-thirdparty-server=files.zimbra.com --no-interactive
