cmake_minimum_required(VERSION 3.21)

# macOS: one universal app for Apple silicon and Intel Macs. Set before project().
set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Oldest macOS FastGH runs on")
set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "Architectures to build for")

project(FastGH LANGUAGES C CXX)
if(APPLE)
    enable_language(OBJCXX)  # the macOS platform file is Objective-C++
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
    add_compile_options(/utf-8 /MP /W3)
    # WIN32_LEAN_AND_MEAN is deliberately not set: it hides shellapi.h, which wxWidgets needs.
    add_compile_definitions(NOMINMAX UNICODE _UNICODE _CRT_SECURE_NO_WARNINGS)
    # Statically link the C runtime so FastGH.exe needs no redistributable.
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

include(FetchContent)
set(FETCHCONTENT_QUIET OFF)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "Floor for old dependencies")
set(CMAKE_SKIP_INSTALL_RULES ON)

# ---------------------------------------------------------------------------
# wxWidgets, from master
# ---------------------------------------------------------------------------
# Pinned to a master commit (as FastPlay is): master carries the screen reader
# fixes made since the last 3.3 release, most of them for VoiceOver. Move the
# pin forward to pick up newer ones.
FetchContent_Declare(wxWidgets
    GIT_REPOSITORY https://github.com/wxWidgets/wxWidgets.git
    GIT_TAG d751cb5b814bfc404293922191ea1f9f1038d503
)
set(wxBUILD_SHARED OFF CACHE INTERNAL "")
if(UNIX AND NOT APPLE)
    # The C++ runtime inside the program, so a build from an older distribution
    # runs on newer ones (needs the static libstdc++, e.g. Fedora's libstdc++-static).
    option(FASTGH_STATIC_RUNTIME "Link the C++ runtime statically (Linux)" ON)
    set(wxBUILD_USE_STATIC_RUNTIME ${FASTGH_STATIC_RUNTIME} CACHE INTERNAL "")
else()
    set(wxBUILD_USE_STATIC_RUNTIME ON CACHE INTERNAL "")
endif()
set(wxBUILD_TESTS OFF CACHE INTERNAL "")
set(wxBUILD_SAMPLES OFF CACHE INTERNAL "")
set(wxBUILD_DEMOS OFF CACHE INTERNAL "")
if(APPLE)
    # A precompiled header is built for one architecture; the app is universal.
    set(wxBUILD_PRECOMP OFF CACHE INTERNAL "")
else()
    set(wxBUILD_PRECOMP ON CACHE INTERNAL "")
endif()
set(wxUSE_STL ON CACHE INTERNAL "")
# FastGH links core, base and adv; the rest of wxWidgets is most of the build
# for code that is never called.
set(wxUSE_STC OFF CACHE INTERNAL "")
set(wxUSE_WEBVIEW OFF CACHE INTERNAL "")
set(wxUSE_MEDIACTRL OFF CACHE INTERNAL "")
set(wxUSE_RICHTEXT OFF CACHE INTERNAL "")
set(wxUSE_PROPGRID OFF CACHE INTERNAL "")
set(wxUSE_RIBBON OFF CACHE INTERNAL "")
set(wxUSE_AUI OFF CACHE INTERNAL "")
set(wxUSE_XRC OFF CACHE INTERNAL "")
set(wxUSE_GL OFF CACHE INTERNAL "")
set(wxUSE_LIBJPEG OFF CACHE INTERNAL "")
set(wxUSE_LIBTIFF OFF CACHE INTERNAL "")
set(wxUSE_LIBWEBP OFF CACHE INTERNAL "")
# SetAccessibleName() on Windows needs MSAA support compiled in.
if(WIN32)
    set(wxUSE_ACCESSIBILITY ON CACHE INTERNAL "")
endif()
if(UNIX AND NOT APPLE)
    # One FastGH binary for every distribution: wxWidgets' own copies of these
    # libraries, and none of the optional ones a desktop may not have installed.
    set(wxUSE_REGEX builtin CACHE INTERNAL "")
    set(wxUSE_ZLIB builtin CACHE INTERNAL "")
    set(wxUSE_LIBPNG builtin CACHE INTERNAL "")
    set(wxUSE_EXPAT builtin CACHE INTERNAL "")
    set(wxUSE_SECRETSTORE OFF CACHE INTERNAL "")
    set(wxUSE_WEBREQUEST OFF CACHE INTERNAL "")
    set(wxUSE_UIACTIONSIMULATOR OFF CACHE INTERNAL "")
    set(wxUSE_LIBMSPACK OFF CACHE INTERNAL "")
    set(wxUSE_SPELLCHECK OFF CACHE INTERNAL "")
    # The tray icon through StatusNotifierItem (KDE, GNOME with the AppIndicator
    # extension, Wayland) needs libayatana-appindicator, which not every desktop
    # has, so the release build leaves it out: FastGH then uses the X11 tray where
    # there is one and minimizes where there isn't.
    option(FASTGH_APPINDICATOR "Tray icon through libayatana-appindicator (Linux)" OFF)
    set(wxUSE_APPINDICATOR ${FASTGH_APPINDICATOR} CACHE INTERNAL "")
endif()
FetchContent_MakeAvailable(wxWidgets)

# --- JSON ---
FetchContent_Declare(nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(nlohmann_json)

# Configure only the dependencies (to start the long wxWidgets build early).
option(FASTGH_DEPS_ONLY "Configure the fetched dependencies without FastGH itself" OFF)
if(FASTGH_DEPS_ONLY)
    return()
endif()

# ---------------------------------------------------------------------------
# FastGH
# ---------------------------------------------------------------------------
file(GLOB FASTGH_SOURCES CONFIGURE_DEPENDS
    src/core/*.cpp
    src/ui/*.cpp
)

if(WIN32)
    list(APPEND FASTGH_SOURCES src/platform/http_windows.cpp src/platform/platform_windows.cpp res/fastgh.rc)
elseif(APPLE)
    list(APPEND FASTGH_SOURCES src/platform/http_curl.cpp src/platform/platform_mac.mm res/mac/FastGH.icns)
    set_source_files_properties(res/mac/FastGH.icns PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
else()
    list(APPEND FASTGH_SOURCES src/platform/http_curl.cpp src/platform/curl_dynamic.cpp src/platform/platform_gtk.cpp)
endif()

add_executable(FastGH WIN32 MACOSX_BUNDLE ${FASTGH_SOURCES})
target_include_directories(FastGH PRIVATE src)
target_link_libraries(FastGH PRIVATE wx::core wx::base wx::adv nlohmann_json::nlohmann_json)

file(STRINGS src/version.h FASTGH_VERSION_LINE REGEX "#define APP_VERSION ")
string(REGEX REPLACE ".*\"([^\"]+)\".*" "\\1" FASTGH_VERSION "${FASTGH_VERSION_LINE}")

# The commit this was built from, for the update check.
execute_process(COMMAND git rev-parse HEAD
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    OUTPUT_VARIABLE FASTGH_BUILD_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(FASTGH_BUILD_COMMIT)
    target_compile_definitions(FastGH PRIVATE BUILD_COMMIT="${FASTGH_BUILD_COMMIT}")
endif()

if(WIN32)
    target_link_libraries(FastGH PRIVATE winhttp shell32 ole32 user32)
    set_target_properties(FastGH PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/out
        RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_CURRENT_BINARY_DIR}/out
        RUNTIME_OUTPUT_DIRECTORY_DEBUG ${CMAKE_CURRENT_BINARY_DIR}/out)
elseif(APPLE)
    find_package(CURL REQUIRED)
    target_link_libraries(FastGH PRIVATE CURL::libcurl)
else()
    # libcurl's headers only: curl_dynamic.cpp loads the library at run time.
    find_package(CURL REQUIRED)
    target_include_directories(FastGH PRIVATE ${CURL_INCLUDE_DIRS})
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(GTK3 REQUIRED IMPORTED_TARGET gtk+-3.0)
    find_package(X11 REQUIRED)
    find_package(Threads REQUIRED)
    if(NOT X11_Xi_FOUND)
        message(FATAL_ERROR "FastGH needs XInput 2 (libXi) headers: libxi-dev / libXi-devel")
    endif()
    target_link_libraries(FastGH PRIVATE PkgConfig::GTK3 X11::X11 X11::Xi Threads::Threads ${CMAKE_DL_LIBS})
    if(FASTGH_STATIC_RUNTIME AND CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        target_link_options(FastGH PRIVATE -static-libstdc++ -static-libgcc)
    endif()

    # The icon, built in (the window's and the tray's).
    file(READ res/linux/FastGH.png FASTGH_ICON_HEX HEX)
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," FASTGH_ICON_BYTES "${FASTGH_ICON_HEX}")
    file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/generated/fastgh_icon_png.h
        "// Generated by CMake from res/linux/FastGH.png\n"
        "static const unsigned char fastgh_icon_png[] = {${FASTGH_ICON_BYTES}};\n")
    target_include_directories(FastGH PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/generated)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS res/linux/FastGH.png)

    # Put together what the Linux download holds, in build/out/FastGH.
    set_target_properties(FastGH PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/out/FastGH)
    foreach(f FastGH.png FastGH.desktop install.sh)
        configure_file(res/linux/${f} ${CMAKE_CURRENT_BINARY_DIR}/out/FastGH/${f} COPYONLY)
    endforeach()
endif()

# The activity feed's wording against the fixture shared with the Android app.
add_executable(fastgh_tests EXCLUDE_FROM_ALL tests/event_parity.cpp src/core/models.cpp src/core/util.cpp)
target_include_directories(fastgh_tests PRIVATE src)
target_link_libraries(fastgh_tests PRIVATE nlohmann_json::nlohmann_json)

if(APPLE)
    target_link_libraries(FastGH PRIVATE "-framework AppKit" "-framework Carbon" "-framework UserNotifications")
    set_source_files_properties(src/platform/platform_mac.mm PROPERTIES COMPILE_OPTIONS -fobjc-arc)
    configure_file(res/mac/Info.plist.in ${CMAKE_CURRENT_BINARY_DIR}/Info.plist @ONLY)
    set_target_properties(FastGH PROPERTIES
        MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_BINARY_DIR}/Info.plist)
endif()
