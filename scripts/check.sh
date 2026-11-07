#!/bin/bash
# Syntax-check FastGH sources against the wxWidgets in build/ without linking:
#   scripts/check.sh src/ui/issues_dialog.cpp [more files...]
# Needs build/ configured once (cmake -S . -B build -DCMAKE_BUILD_TYPE=Release).
cd "$(dirname "$0")/.."
WX_SRC=build/_deps/wxwidgets-src/include
WX_SETUP=$(dirname "$(dirname "$(find build/_deps/wxwidgets-build/lib/wx/include -name setup.h -path '*wx/setup.h' | head -1)")")
JSON=build/_deps/nlohmann_json-src/include
status=0
for f in "$@"; do
    lang=c++
    case "$f" in *.mm) lang=objective-c++ ;; esac
    xcrun clang++ -x "$lang" -std=c++17 -fsyntax-only -fobjc-arc \
        -D__WXOSX_COCOA__ -D__WXMAC__ -D__WXOSX__ -D_FILE_OFFSET_BITS=64 -DwxDEBUG_LEVEL=0 \
        -I src -I "$WX_SRC" -I "$WX_SETUP" -I "$JSON" \
        -Wall -Wno-unused-parameter -Wno-deprecated-declarations "$f" || status=1
done
exit $status
