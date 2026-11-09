# Build system, version, licence, build scripts and installer

The root of the repository: the version file, the MIT licence, CMake (also used by the Android build through Gradle), the vcpkg manifest, the CMake helper modules, the Windows resource and version templates, the three PowerShell build scripts, and the WiX source of the Windows installer with its licence page.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `VERSION` | 5 | `b0cb276cde517779…` |
| `LICENSE` | 1071 | `449ef47f14ac81c0…` |
| `.gitignore` | 321 | `cbf9330a7b5aa718…` |
| `CMakeLists.txt` | 10749 | `133166a6bf5a3bd5…` |
| `CMakePresets.json` | 1374 | `5d1e32518da2127f…` |
| `vcpkg.json` | 744 | `f2efeaec2768fa68…` |
| `cmake/HarfBuzzAmalgamated.cmake` | 1947 | `b691fb67ba525d75…` |
| `cmake/StageRelease.cmake` | 1836 | `f7fda02e96438df8…` |
| `res/lanternleaf.rc.in` | 1076 | `51e0434ed75b7a39…` |
| `src/app/Version.h.in` | 453 | `abb5b9157bbb3323…` |
| `build.ps1` | 2676 | `33146a3b9c52372f…` |
| `build-android.ps1` | 4275 | `83cb53e6f17bd0b7…` |
| `build-msi.ps1` | 2694 | `421d93c4d9b3e9c1…` |
| `installer/Lanternleaf.wxs` | 5337 | `34e3498eeacc2856…` |
| `installer/License.rtf` | 1491 | `3bc2aae819f11a94…` |

## `VERSION`

ASCII, no newline at the end.

```text
0.7.0
```

## `LICENSE`

ASCII, LF line endings, ends with a newline.

```text
MIT License

Copyright (c) 2026 Vitali Pinzari

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## `.gitignore`

ASCII, LF line endings, ends with a newline.

```text
/build/
/out/
/.vs/
/.vscode/
*.user
CMakeUserPresets.json

# Android
/android/.gradle/
/android/.kotlin/
/android/build/
/android/app/build/
/android/app/.cxx/
/android/.idea/
/android/local.properties
*.iml
# release signing key: keep it safe, but out of version control
/android/keystore/
/android/keystore.properties
```

## `CMakeLists.txt`

ASCII, LF line endings, ends with a newline.

```cmake
# 3.22 is the CMake that ships with the Android SDK; the Windows build uses Visual Studio's newer CMake.
cmake_minimum_required(VERSION 3.22)

# ---------------------------------------------------------------------------------------------
# Android: Gradle passes the NDK toolchain and ANDROID_ABI. Dependencies come from vcpkg, so chain-load
# the NDK toolchain through vcpkg's and use the vcpkg triplet that matches the ABI.
# ---------------------------------------------------------------------------------------------
if(ANDROID_ABI)
  if(NOT VCPKG_ROOT AND DEFINED ENV{VCPKG_ROOT})
    set(VCPKG_ROOT "$ENV{VCPKG_ROOT}")
  endif()
  if(VCPKG_ROOT AND NOT CMAKE_TOOLCHAIN_FILE MATCHES "vcpkg\\.cmake$")
    set(VCPKG_CHAINLOAD_TOOLCHAIN_FILE "${CMAKE_TOOLCHAIN_FILE}")
    set(CMAKE_TOOLCHAIN_FILE "${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake")
  endif()
  if(NOT VCPKG_TARGET_TRIPLET)
    if(ANDROID_ABI STREQUAL "arm64-v8a")
      set(VCPKG_TARGET_TRIPLET arm64-android)
    elseif(ANDROID_ABI STREQUAL "x86_64")
      set(VCPKG_TARGET_TRIPLET x64-android)
    elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
      set(VCPKG_TARGET_TRIPLET arm-neon-android)
    elseif(ANDROID_ABI STREQUAL "x86")
      set(VCPKG_TARGET_TRIPLET x86-android)
    endif()
  endif()
  # One tree per ABI: in manifest mode a vcpkg install tree holds a single target triplet.
  if(NOT VCPKG_INSTALLED_DIR AND VCPKG_TARGET_TRIPLET)
    set(VCPKG_INSTALLED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/build/vcpkg_android/${VCPKG_TARGET_TRIPLET}" CACHE PATH "")
  endif()
  # vcpkg's Android triplets find the NDK through this variable.
  if(NOT DEFINED ENV{ANDROID_NDK_HOME} AND ANDROID_NDK)
    set(ENV{ANDROID_NDK_HOME} "${ANDROID_NDK}")
  endif()
endif()

# The version lives in one place, the VERSION file: it names the release files (Lanternleaf-<version>.exe/.apk)
# and is shown in the app's About panel and in the Windows file properties. Bump it for every release.
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" LL_VERSION LIMIT_COUNT 1)
string(STRIP "${LL_VERSION}" LL_VERSION)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION")

project(Lanternleaf
  VERSION ${LL_VERSION}
  DESCRIPTION "Lanternleaf - a GPU (OpenGL) rendered FB2/TXT/PDF book reader"
  LANGUAGES C CXX)

set(LL_DEVELOPER "Vitali Pinzari")
set(LL_COPYRIGHT_YEAR "2026")
configure_file(src/app/Version.h.in "${CMAKE_CURRENT_BINARY_DIR}/generated/app/Version.h" @ONLY)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(LL_BUILD_TESTS "Build the unit tests" ON)
option(LL_BUILD_APP "Build the reader application" ON)

if(MSVC)
  add_compile_options(/utf-8 /W4 /permissive- /Zc:__cplusplus /MP /external:anglebrackets /external:W0)
  add_compile_definitions(NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
endif()

find_package(Freetype REQUIRED)
if(ANDROID)
  include(cmake/HarfBuzzAmalgamated.cmake)
else()
  find_package(harfbuzz CONFIG REQUIRED)
endif()
find_package(miniz CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(Stb REQUIRED)

# ---------------------------------------------------------------------------------------------
# ll_core: portable book model, FB2/TXT/PDF parsing, encodings, hyphenation, line breaking, search.
# No SDL and no OpenGL here, so it can be reused unchanged by the Android port.
# ---------------------------------------------------------------------------------------------
add_library(ll_core STATIC
  src/core/Unicode.cpp
  src/core/Encoding.cpp
  src/core/Document.cpp
  src/core/XmlReader.cpp
  src/core/ImageCodec.cpp
  src/core/Fb2Parser.cpp
  src/core/TxtParser.cpp
  src/core/PdfReader.cpp
  src/core/PdfCrypt.cpp
  src/core/PdfContent.cpp
  src/core/PdfParser.cpp
  src/core/BookLoader.cpp
  src/core/FileUtil.cpp
  src/core/Hyphenator.cpp
  src/core/LineBreaker.cpp
  src/core/LibrarySearch.cpp)
target_include_directories(ll_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src ${Stb_INCLUDE_DIR})
target_link_libraries(ll_core PUBLIC miniz::miniz nlohmann_json::nlohmann_json)

# ---------------------------------------------------------------------------------------------
# ll_text: fonts (FreeType), shaping (HarfBuzz) and the paragraph/page layout engine.
# ---------------------------------------------------------------------------------------------
option(LL_BUILD_TEXT "Build the text/layout library" ON)
if(LL_BUILD_TEXT)
  add_library(ll_text STATIC
    src/text/FontLibrary.cpp
    src/text/Shaper.cpp
    src/text/BookLayout.cpp)
  target_link_libraries(ll_text PUBLIC ll_core Freetype::Freetype harfbuzz::harfbuzz)
endif()

# ---------------------------------------------------------------------------------------------
# The application: SDL3 window + OpenGL 4.1 core (GLES 3.0 compatible shaders) + Dear ImGui.
# ---------------------------------------------------------------------------------------------
if(LL_BUILD_APP)
  find_package(SDL3 CONFIG REQUIRED)
  find_package(imgui CONFIG REQUIRED)
  if(NOT ANDROID)
    find_package(glad CONFIG REQUIRED)
  endif()

  set(LL_APP_SOURCES
    src/main.cpp
    src/app/App.cpp
    src/app/AppUi.cpp
    src/app/FileBrowser.cpp
    src/app/Settings.cpp
    src/app/Themes.cpp
    src/render/GlCommon.cpp
    src/render/GlyphAtlas.cpp
    src/render/Renderer2D.cpp
    src/render/PageTurn.cpp
    src/platform/Platform.cpp)

  if(ANDROID)
    # Android loads the app as libmain.so (see android/), assets are packaged into the APK by Gradle.
    add_library(Lanternleaf SHARED ${LL_APP_SOURCES})
    set_target_properties(Lanternleaf PROPERTIES OUTPUT_NAME main)
    target_compile_definitions(Lanternleaf PRIVATE LL_USE_GLES)
    # SDL3 is linked statically: keep all of it, including its JNI entry points, inside libmain.so.
    target_link_libraries(Lanternleaf PRIVATE -Wl,--whole-archive SDL3::SDL3-static -Wl,--no-whole-archive)
    target_link_libraries(Lanternleaf PRIVATE ll_text SDL3::SDL3-static imgui::imgui GLESv3 EGL android log)
  else()
    add_executable(Lanternleaf WIN32 ${LL_APP_SOURCES})
    if(WIN32)
      # Icon and version information (Explorer > Properties > Details), generated from VERSION.
      set(LL_ICON_PATH "${CMAKE_CURRENT_SOURCE_DIR}/res/lanternleaf.ico")
      configure_file(res/lanternleaf.rc.in "${CMAKE_CURRENT_BINARY_DIR}/generated/lanternleaf.rc" @ONLY)
      target_sources(Lanternleaf PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated/lanternleaf.rc")
    endif()
    target_link_libraries(Lanternleaf PRIVATE ll_text SDL3::SDL3 imgui::imgui glad::glad)
    set_target_properties(Lanternleaf PROPERTIES VS_DEBUGGER_WORKING_DIRECTORY "$<TARGET_FILE_DIR:Lanternleaf>")

    # Fonts, hyphenation patterns and licences next to the executable.
    add_custom_command(TARGET Lanternleaf POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E copy_directory "${CMAKE_CURRENT_SOURCE_DIR}/assets" "$<TARGET_FILE_DIR:Lanternleaf>/assets"
      COMMENT "Copying assets")
  endif()
  target_include_directories(Lanternleaf PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")

  # -------------------------------------------------------------------------------------------
  # Every Release build is also staged, ready to run or ship, in release/<Platform>/:
  #   release/Windows: Lanternleaf-<version>.exe, assets/, the VC++ runtime DLLs, THIRD-PARTY-NOTICES.txt
  # (The Android APK is produced by Gradle and goes to release/Android/Lanternleaf-<version>.apk.)
  # -------------------------------------------------------------------------------------------
  option(LL_STAGE_RELEASE "Copy every Release build to release/<Platform>/" ON)
  if(LL_STAGE_RELEASE AND NOT ANDROID)
    if(WIN32)
      set(LL_RELEASE_PLATFORM Windows)
    elseif(APPLE)
      set(LL_RELEASE_PLATFORM macOS)
    else()
      set(LL_RELEASE_PLATFORM Linux)
    endif()
    set(LL_RELEASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/release/${LL_RELEASE_PLATFORM}")

    # Licence texts of the statically linked libraries, collected from vcpkg.
    set(LL_NOTICES "${CMAKE_CURRENT_BINARY_DIR}/THIRD-PARTY-NOTICES.txt")
    file(WRITE "${LL_NOTICES}"
      "Lanternleaf ${PROJECT_VERSION} - third-party notices\n\n"
      "Fonts: PT Serif and PT Sans by ParaType, SIL Open Font License (assets/fonts/OFL-*.txt).\n"
      "Hyphenation patterns: hyph-utf8 project (assets/hyphenation/README.md).\n"
      "The libraries below are linked into Lanternleaf.exe.\n")
    set(_vcpkg_share "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/share")
    foreach(_pkg sdl3 freetype harfbuzz imgui glad miniz nlohmann-json stb)
      if(EXISTS "${_vcpkg_share}/${_pkg}/copyright")
        file(READ "${_vcpkg_share}/${_pkg}/copyright" _text)
        file(APPEND "${LL_NOTICES}" "\n==================== ${_pkg} ====================\n\n${_text}\n")
      endif()
    endforeach()

    # The Visual C++ runtime DLLs the executable imports, deployed app-locally so the folder runs anywhere.
    set(LL_RUNTIME_DLLS "")
    if(MSVC)
      set(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP TRUE)
      set(CMAKE_INSTALL_UCRT_LIBRARIES FALSE)
      include(InstallRequiredSystemLibraries)
      foreach(_dll IN LISTS CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS)
        get_filename_component(_name "${_dll}" NAME)
        string(TOLOWER "${_name}" _name)
        if(_name MATCHES "^(msvcp140|vcruntime140|vcruntime140_1)\\.dll$")
          list(APPEND LL_RUNTIME_DLLS "${_dll}")
        endif()
      endforeach()
      if(NOT LL_RUNTIME_DLLS)
        message(WARNING "VC++ runtime DLLs not found; release/${LL_RELEASE_PLATFORM} will need the VC++ redistributable.")
      endif()
    endif()

    set(_stage_config "${CMAKE_CURRENT_BINARY_DIR}/stage_release_config.cmake")
    file(WRITE "${_stage_config}"
      "set(DEST \"${LL_RELEASE_DIR}\")\n"
      "set(VERSION \"${PROJECT_VERSION}\")\n"
      "set(ASSETS \"${CMAKE_CURRENT_SOURCE_DIR}/assets\")\n"
      "set(NOTICES \"${LL_NOTICES}\")\n"
      "set(RUNTIME_DLLS \"${LL_RUNTIME_DLLS}\")\n")
    add_custom_target(stage_release ALL
      COMMAND ${CMAKE_COMMAND} -DCONFIG=$<CONFIG> -DEXE=$<TARGET_FILE:Lanternleaf> -DSTAGE_CONFIG=${_stage_config}
              -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/StageRelease.cmake"
      COMMENT "Staging the Release build in release/${LL_RELEASE_PLATFORM}"
      VERBATIM)
    add_dependencies(stage_release Lanternleaf)
  endif()
endif()

if(LL_BUILD_TESTS)
  enable_testing()
  add_executable(ll_tests tests/core_tests.cpp)
  if(LL_BUILD_TEXT)
    target_link_libraries(ll_tests PRIVATE ll_text)
    target_compile_definitions(ll_tests PRIVATE LL_TESTS_WITH_TEXT)
  else()
    target_link_libraries(ll_tests PRIVATE ll_core)
  endif()
  add_test(NAME ll_tests COMMAND ll_tests "${CMAKE_CURRENT_SOURCE_DIR}/assets")
endif()
```

## `CMakePresets.json`

ASCII, LF line endings, ends with a newline.

```json
{
  "version": 6,
  "cmakeMinimumRequired": { "major": 3, "minor": 25, "patch": 0 },
  "configurePresets": [
    {
      "name": "windows-base",
      "hidden": true,
      "binaryDir": "${sourceDir}/build/${presetName}",
      "toolchainFile": "$env{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake",
      "cacheVariables": {
        "VCPKG_TARGET_TRIPLET": "x64-windows-static-md",
        "VCPKG_INSTALLED_DIR": "${sourceDir}/build/vcpkg_installed"
      },
      "condition": { "type": "equals", "lhs": "${hostSystemName}", "rhs": "Windows" }
    },
    {
      "name": "vs2026",
      "displayName": "Visual Studio 2026 (x64)",
      "inherits": "windows-base",
      "generator": "Visual Studio 18 2026",
      "architecture": { "value": "x64", "strategy": "set" }
    },
    {
      "name": "ninja",
      "displayName": "Ninja Multi-Config (from a VS Developer prompt)",
      "inherits": "windows-base",
      "generator": "Ninja Multi-Config"
    }
  ],
  "buildPresets": [
    { "name": "release", "displayName": "Release", "configurePreset": "vs2026", "configuration": "Release" },
    { "name": "debug", "displayName": "Debug", "configurePreset": "vs2026", "configuration": "Debug" }
  ],
  "testPresets": [
    {
      "name": "release",
      "configurePreset": "vs2026",
      "configuration": "Release",
      "output": { "outputOnFailure": true }
    }
  ]
}
```

## `vcpkg.json`

ASCII, LF line endings, ends with a newline.

```json
{
  "$schema": "https://raw.githubusercontent.com/microsoft/vcpkg-tool/main/docs/vcpkg.schema.json",
  "name": "lanternleaf",
  "version-semver": "0.1.0",
  "description": "Lanternleaf - a GPU (OpenGL) rendered FB2/TXT book reader",
  "builtin-baseline": "9a5dfef5d1a0438a7d24856a85bd60f309d355e9",
  "dependencies": [
    "sdl3",
    {
      "name": "freetype",
      "default-features": false
    },
    {
      "name": "harfbuzz",
      "default-features": false,
      "platform": "!android"
    },
    {
      "name": "imgui",
      "features": [ "sdl3-binding", "opengl3-binding" ]
    },
    {
      "name": "glad",
      "features": [ "gl-api-41" ],
      "platform": "!android"
    },
    "miniz",
    "nlohmann-json",
    "stb"
  ]
}
```

## `cmake/HarfBuzzAmalgamated.cmake`

ASCII, LF line endings, ends with a newline.

```cmake
# HarfBuzz for Android, built from its official single-file ("amalgamated") source, harfbuzz.cc.
#
# vcpkg cannot build HarfBuzz for Android on a Windows host: Meson rejects Windows-style install prefixes
# when cross-compiling. The same pinned release as on desktop (14.6.0) is used. The archive is taken
# from build/downloads/ or the vcpkg download cache when present, otherwise downloaded from GitHub and
# verified against its SHA-256.
# Defines the target harfbuzz::harfbuzz.

set(LL_HARFBUZZ_VERSION 14.6.0)
set(_hb_sha256 eca8581e5ad8e21dbda31556c0363f764b1a754c9c1bb33ca7cd56ca1c07ddc9)
set(_hb_root "${CMAKE_BINARY_DIR}/harfbuzz-${LL_HARFBUZZ_VERSION}")

if(NOT EXISTS "${_hb_root}/src/harfbuzz.cc")
  set(_hb_archive "")
  foreach(_candidate
      "${CMAKE_CURRENT_SOURCE_DIR}/build/downloads/harfbuzz-${LL_HARFBUZZ_VERSION}.tar.gz"
      "$ENV{LOCALAPPDATA}/vcpkg/downloads/harfbuzz-harfbuzz-${LL_HARFBUZZ_VERSION}.tar.gz")
    if(EXISTS "${_candidate}")
      file(SHA256 "${_candidate}" _hash)
      if(_hash STREQUAL _hb_sha256)
        set(_hb_archive "${_candidate}")
        break()
      endif()
    endif()
  endforeach()
  if(NOT _hb_archive)
    set(_hb_archive "${CMAKE_BINARY_DIR}/harfbuzz-${LL_HARFBUZZ_VERSION}.tar.gz")
    message(STATUS "Downloading HarfBuzz ${LL_HARFBUZZ_VERSION}")
    file(DOWNLOAD "https://github.com/harfbuzz/harfbuzz/archive/${LL_HARFBUZZ_VERSION}.tar.gz" "${_hb_archive}"
         EXPECTED_HASH SHA256=${_hb_sha256})
  endif()
  file(ARCHIVE_EXTRACT INPUT "${_hb_archive}" DESTINATION "${CMAKE_BINARY_DIR}"
       PATTERNS "harfbuzz-${LL_HARFBUZZ_VERSION}/src/*")
endif()

add_library(ll_harfbuzz STATIC "${_hb_root}/src/harfbuzz.cc")
target_include_directories(ll_harfbuzz SYSTEM PUBLIC "${_hb_root}/src")
target_compile_definitions(ll_harfbuzz PRIVATE HAVE_PTHREAD=1)
set_target_properties(ll_harfbuzz PROPERTIES POSITION_INDEPENDENT_CODE ON)
add_library(harfbuzz::harfbuzz ALIAS ll_harfbuzz)
```

## `cmake/StageRelease.cmake`

ASCII, LF line endings, ends with a newline.

```cmake
# Copies a finished Release build into release/<Platform>/ (run by the `stage_release` target after every build).
#
#   cmake -DCONFIG=<config> -DEXE=<path to the executable> -DSTAGE_CONFIG=<generated settings> -P StageRelease.cmake
#
# STAGE_CONFIG (written at configure time) defines DEST, VERSION, ASSETS, NOTICES and RUNTIME_DLLS.
# Only the Release configuration is staged. The executable is named after the version (Lanternleaf-0.2.0.exe), so
# earlier versions stay next to it. A file that is in use (that version is running) is reported as a warning
# instead of failing the build; close the app and build again to refresh the folder.

if(NOT CONFIG STREQUAL "Release")
  return()
endif()
include("${STAGE_CONFIG}")

file(MAKE_DIRECTORY "${DEST}")
get_filename_component(exe_stem "${EXE}" NAME_WE)
get_filename_component(exe_ext "${EXE}" EXT)
set(exe_name "${exe_stem}-${VERSION}${exe_ext}")
file(COPY_FILE "${EXE}" "${DEST}/${exe_name}" RESULT copy_result ONLY_IF_DIFFERENT)
if(copy_result)
  message(WARNING "release folder not updated: ${DEST}/${exe_name} could not be replaced (${copy_result}). "
                  "Is that version still running? Close it and build again.")
  return()
endif()

foreach(dll IN LISTS RUNTIME_DLLS)
  get_filename_component(dll_name "${dll}" NAME)
  file(COPY_FILE "${dll}" "${DEST}/${dll_name}" RESULT dll_result ONLY_IF_DIFFERENT)
  if(dll_result)
    message(WARNING "could not copy ${dll_name}: ${dll_result}")
  endif()
endforeach()

# Assets are read into memory at start-up, so they can be replaced even while the app runs.
file(REMOVE_RECURSE "${DEST}/assets")
file(COPY "${ASSETS}" DESTINATION "${DEST}")

if(EXISTS "${NOTICES}")
  file(COPY_FILE "${NOTICES}" "${DEST}/THIRD-PARTY-NOTICES.txt" ONLY_IF_DIFFERENT)
endif()

message(STATUS "Release build staged in ${DEST}/${exe_name}")
```

## `res/lanternleaf.rc.in`

ASCII, LF line endings, ends with a newline.

```c
// Generated by CMake (configure_file) from res/lanternleaf.rc.in: version and copyright come from VERSION.
#include <winver.h>

1 ICON "@LL_ICON_PATH@"

VS_VERSION_INFO VERSIONINFO
 FILEVERSION @PROJECT_VERSION_MAJOR@,@PROJECT_VERSION_MINOR@,@PROJECT_VERSION_PATCH@,0
 PRODUCTVERSION @PROJECT_VERSION_MAJOR@,@PROJECT_VERSION_MINOR@,@PROJECT_VERSION_PATCH@,0
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x0L
 FILEOS VOS_NT_WINDOWS32
 FILETYPE VFT_APP
 FILESUBTYPE 0x0L
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "CompanyName", "@LL_DEVELOPER@"
      VALUE "FileDescription", "Lanternleaf - FB2/TXT/PDF book reader"
      VALUE "FileVersion", "@PROJECT_VERSION@"
      VALUE "InternalName", "Lanternleaf"
      VALUE "LegalCopyright", "Copyright (C) @LL_COPYRIGHT_YEAR@ @LL_DEVELOPER@. MIT License."
      VALUE "OriginalFilename", "Lanternleaf-@PROJECT_VERSION@.exe"
      VALUE "ProductName", "Lanternleaf"
      VALUE "ProductVersion", "@PROJECT_VERSION@"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
```

## `src/app/Version.h.in`

ASCII, LF line endings, ends with a newline.

```cpp
// Generated by CMake from VERSION and CMakeLists.txt: do not edit (edit the VERSION file instead).
#pragma once

#define LL_VERSION "@PROJECT_VERSION@"
#define LL_VERSION_MAJOR @PROJECT_VERSION_MAJOR@
#define LL_VERSION_MINOR @PROJECT_VERSION_MINOR@
#define LL_VERSION_PATCH @PROJECT_VERSION_PATCH@
#define LL_DEVELOPER "@LL_DEVELOPER@"
#define LL_COPYRIGHT_YEAR "@LL_COPYRIGHT_YEAR@"
#define LL_COPYRIGHT "\xC2\xA9 @LL_COPYRIGHT_YEAR@ @LL_DEVELOPER@"
```

## `build.ps1`

ASCII, LF line endings, ends with a newline.

```powershell
<#
.SYNOPSIS
  Configures and builds Lanternleaf with the CMake, vcpkg and MSVC that ship with Visual Studio 2026.

.EXAMPLE
  ./build.ps1                 # Release build
  ./build.ps1 -Config Debug
  ./build.ps1 -Test           # build and run the unit tests
  ./build.ps1 -Run            # build and start the reader
#>
param(
  [ValidateSet("Release", "Debug", "RelWithDebInfo")]
  [string]$Config = "Release",
  [switch]$Test,
  [switch]$Run,
  [switch]$Clean,
  [string[]]$CMakeArgs = @()
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Build tools print notes and warnings on stderr, which Windows PowerShell 5.1 turns into terminating errors
# when the output is redirected. Run them with "Continue" and judge them by their exit code instead.
function Invoke-Tool([string]$What, [scriptblock]$Command) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $Command } finally { $ErrorActionPreference = $saved }
  if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { throw "vswhere.exe not found - install Visual Studio 2026 with the C++ workload." }
$vs = & $vswhere -latest -prerelease -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "Visual Studio with the C++ x64 tools was not found." }

$cmake = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$ctest = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe"
if (-not $env:VCPKG_ROOT) { $env:VCPKG_ROOT = Join-Path $vs "VC\vcpkg" }
$git = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd"
if (Test-Path $git) { $env:PATH = "$git;$env:PATH" }

$buildDir = Join-Path $PSScriptRoot "build\vs2026"
if ($Clean -and (Test-Path $buildDir)) { Remove-Item -Recurse -Force $buildDir }

Invoke-Tool "CMake configure" { & $cmake --preset vs2026 @CMakeArgs }
Invoke-Tool "Build" { & $cmake --build $buildDir --config $Config --parallel }

if ($Test) {
  Invoke-Tool "Tests" { & $ctest --test-dir $buildDir -C $Config --output-on-failure }
}

$exe = Join-Path $buildDir "$Config\Lanternleaf.exe"
if (Test-Path $exe) { Write-Host "Built: $exe" }
# Release builds are also staged (by the stage_release target) in release\Windows, ready to run or ship.
$release = Join-Path $PSScriptRoot "release\Windows"
if ($Config -eq "Release" -and (Test-Path (Join-Path $release "Lanternleaf.exe"))) { Write-Host "Release: $release" }
if ($Run) { Start-Process $exe }
```

## `build-android.ps1`

ASCII, LF line endings, ends with a newline.

```powershell
<#
.SYNOPSIS
  Builds the Lanternleaf Android app (APK) and copies it to release\Android\Lanternleaf-<version>.apk
  (the version comes from the VERSION file).

  Uses the Android SDK/NDK and JDK that come with Android Studio, and the vcpkg that comes with
  Visual Studio 2026 (for SDL3, FreeType, Dear ImGui, miniz ...).

.EXAMPLE
  ./build-android.ps1                 # release APK -> release\Android\Lanternleaf-<version>.apk
  ./build-android.ps1 -Install -Run   # ... and install + start it on the connected device / emulator
  ./build-android.ps1 -Config Debug
#>
param(
  [ValidateSet("Release", "Debug")]
  [string]$Config = "Release",
  [switch]$Install,
  [switch]$Run,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Gradle, javac and vcpkg print notes and warnings on stderr, which Windows PowerShell 5.1 turns into
# terminating errors when the output is redirected. Run them with "Continue" and judge them by their exit code.
function Invoke-Tool([string]$What, [scriptblock]$Command) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $Command } finally { $ErrorActionPreference = $saved }
  if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function First-Existing([string[]]$paths) {
  foreach ($p in $paths) { if ($p -and (Test-Path $p)) { return $p } }
  return $null
}

$sdk = First-Existing @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, "$env:LOCALAPPDATA\Android\Sdk")
if (-not $sdk) { throw "Android SDK not found: install Android Studio (or set ANDROID_HOME)." }
$ndkVersion = "28.2.13676358"
$ndk = Join-Path $sdk "ndk\$ndkVersion"
if (-not (Test-Path $ndk)) { throw "NDK $ndkVersion not found: install it from Android Studio > SDK Manager > SDK Tools." }
$jdk = First-Existing @($env:JAVA_HOME, "D:\Program Files\Android Studio\jbr", "C:\Program Files\Android\Android Studio\jbr",
                        "$env:LOCALAPPDATA\Programs\Android Studio\jbr")
if (-not $jdk) { throw "No JDK found: set JAVA_HOME (Android Studio's bundled JDK in <Android Studio>\jbr works)." }

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
$vs = if (Test-Path $vswhere) { & $vswhere -latest -prerelease -products * -property installationPath } else { $null }
$vcpkg = First-Existing @($env:VCPKG_ROOT, $(if ($vs) { Join-Path $vs "VC\vcpkg" }))
if (-not $vcpkg) { throw "vcpkg not found: install Visual Studio 2026 (C++ workload) or set VCPKG_ROOT." }
if ($vs) {
  $git = Join-Path $vs "Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\cmd"
  if (Test-Path $git) { $env:PATH = "$git;$env:PATH" }
}

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_NDK_HOME = $ndk
$env:VCPKG_ROOT = $vcpkg

# Dependencies for both ABIs (instant after the first build thanks to vcpkg's binary cache).
foreach ($triplet in @("arm64-android", "x64-android")) {
  Write-Host "vcpkg: $triplet"
  Invoke-Tool "vcpkg install ($triplet)" {
    & (Join-Path $vcpkg "vcpkg.exe") install --triplet $triplet --x-install-root="$PSScriptRoot\build\vcpkg_android\$triplet" --no-print-usage
  }
}

# Machine-specific paths for Gradle (and Android Studio, if you open the android folder there).
$local = "sdk.dir=$($sdk -replace '\\', '\\')`nvcpkg.dir=$($vcpkg -replace '\\', '\\')"
Set-Content -Path "android\local.properties" -Value $local -Encoding ascii

Push-Location android
try {
  if ($Clean) { Invoke-Tool "gradle clean" { & .\gradlew.bat clean --console=plain } }
  Invoke-Tool "Gradle build" { & .\gradlew.bat "assemble$Config" --console=plain }
} finally {
  Pop-Location
}

$version = (Get-Content (Join-Path $PSScriptRoot "VERSION") -TotalCount 1).Trim()
$apk = if ($Config -eq "Release") { Join-Path $PSScriptRoot "release\Android\Lanternleaf-$version.apk" }
       else { Join-Path $PSScriptRoot "android\app\build\outputs\apk\debug\app-debug.apk" }
if (-not (Test-Path $apk)) { throw "APK not found: $apk" }
Write-Host "APK: $apk"

$adb = Join-Path $sdk "platform-tools\adb.exe"
if ($Install -or $Run) {
  Invoke-Tool "adb install (is a device or emulator connected?)" { & $adb install -r $apk }
}
if ($Run) {
  Invoke-Tool "adb start" { & $adb shell am start -n app.lanternleaf.reader/.LanternleafActivity }
}
```

## `build-msi.ps1`

ASCII, LF line endings, ends with a newline.

```powershell
<#
.SYNOPSIS
  Packages the staged Windows release (release\Windows) into an MSI installer with the WiX Toolset.

.DESCRIPTION
  Run ./build.ps1 first so release\Windows holds the current build. The first run downloads WiX 6 and its UI
  extension from NuGet into build\tools (ignored by git); later runs reuse them.
  Output: release\Installer\Lanternleaf-<version>-x64.msi

.EXAMPLE
  ./build-msi.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$wixVersion = "6.0.2"

function Invoke-Tool([string]$What, [scriptblock]$Command) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $Command } finally { $ErrorActionPreference = $saved }
  if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

$version = (Get-Content (Join-Path $PSScriptRoot "VERSION") -Raw).Trim()
$releaseDir = Join-Path $PSScriptRoot "release\Windows"
$exeName = "Lanternleaf-$version.exe"
if (-not (Test-Path (Join-Path $releaseDir $exeName))) {
  throw "$releaseDir\$exeName not found - run ./build.ps1 first."
}

# WiX CLI and UI extension, installed locally under build\tools
$toolsDir = Join-Path $PSScriptRoot "build\tools"
$wix = Join-Path $toolsDir "wix\wix.exe"
if (-not (Test-Path $wix)) {
  if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw "The .NET SDK (dotnet) is needed to install WiX." }
  Invoke-Tool "Installing WiX" { dotnet tool install wix --version $wixVersion --tool-path (Join-Path $toolsDir "wix") }
}
$uiExt = Join-Path $toolsDir ".wix\extensions\WixToolset.UI.wixext\$wixVersion\wixext6\WixToolset.UI.wixext.dll"
if (-not (Test-Path $uiExt)) {
  Push-Location $toolsDir
  try { Invoke-Tool "Installing the WiX UI extension" { & $wix extension add "WixToolset.UI.wixext/$wixVersion" } }
  finally { Pop-Location }
}

$outDir = Join-Path $PSScriptRoot "release\Installer"
New-Item -ItemType Directory -Force $outDir | Out-Null
$msi = Join-Path $outDir "Lanternleaf-$version-x64.msi"

$installerDir = Join-Path $PSScriptRoot "installer"
Push-Location $installerDir
try {
  Invoke-Tool "MSI build" {
    & $wix build "Lanternleaf.wxs" -arch x64 -ext $uiExt `
      -d "Version=$version" -d "ReleaseDir=$releaseDir" -d "ExeName=$exeName" `
      -intermediatefolder (Join-Path $PSScriptRoot "build\msi") -o $msi
  }
} finally { Pop-Location }

Remove-Item (Join-Path $outDir "*.wixpdb") -ErrorAction SilentlyContinue

# Windows Installer consistency checks (ICE). ICE60 is skipped: it flags the bundled .ttf fonts, which are
# private files read by the app, not system fonts installed into C:\Windows\Fonts.
Invoke-Tool "MSI validation" { & $wix msi validate $msi -sice ICE60 }
Write-Host "Installer: $msi"
```

## `installer/Lanternleaf.wxs`

ASCII, CRLF line endings, ends with a newline.

```text
<?xml version="1.0" encoding="utf-8"?>
<!--
  Windows installer (MSI) for Lanternleaf, built from the staged release\Windows folder by build-msi.ps1.

  Preprocessor variables (passed by build-msi.ps1):
    Version     product version, from the VERSION file (e.g. 0.6.0)
    ReleaseDir  absolute path of release\Windows
    ExeName     file name of the staged program (e.g. Lanternleaf-0.6.0.exe)

  The program is installed as "Lanternleaf.exe" so that shortcuts and file associations keep the same path
  across upgrades. UpgradeCode must never change: it is what lets a newer MSI replace an older one.
-->
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">

  <Package Name="Lanternleaf"
           Manufacturer="Vitali Pinzari"
           Version="$(var.Version)"
           UpgradeCode="bf8bade1-142d-4d22-91f4-658f940f8a21"
           Scope="perMachine"
           Language="1033">

    <SummaryInformation Description="Lanternleaf $(var.Version) - FB2, TXT and PDF book reader" />

    <MajorUpgrade DowngradeErrorMessage="A newer version of [ProductName] is already installed." />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />

    <!-- Add/Remove Programs entry -->
    <Icon Id="AppIcon.ico" SourceFile="..\res\lanternleaf.ico" />
    <Property Id="ARPPRODUCTICON" Value="AppIcon.ico" />
    <Property Id="ARPCONTACT" Value="Vitali Pinzari" />

    <!-- Wizard: welcome, MIT licence, install folder, progress, finish -->
    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />
    <WixVariable Id="WixUILicenseRtf" Value="License.rtf" />

    <StandardDirectory Id="ProgramFiles64Folder">
      <Directory Id="INSTALLFOLDER" Name="Lanternleaf" />
    </StandardDirectory>

    <Feature Id="Main" Title="Lanternleaf" Level="1" AllowAbsent="no">
      <ComponentGroupRef Id="ProgramFiles" />
      <ComponentRef Id="Program" />
      <ComponentRef Id="StartMenuShortcut" />
    </Feature>

    <!-- Start menu shortcut. Windows Installer wants a shortcut that is not advertised to sit in its own
         component with an HKCU key path (ICE43/ICE57); the shortcut shows the exe's own icon. -->
    <StandardDirectory Id="ProgramMenuFolder">
      <Component Id="StartMenuShortcut">
        <Shortcut Id="StartMenuShortcut" Name="Lanternleaf" Description="Read FB2, TXT and PDF books"
                  Target="[INSTALLFOLDER]Lanternleaf.exe" WorkingDirectory="INSTALLFOLDER" />
        <RegistryValue Root="HKCU" Key="Software\Lanternleaf\Installer" Name="StartMenuShortcut" Type="integer"
                       Value="1" KeyPath="yes" />
      </Component>
    </StandardDirectory>

    <!-- The program itself and its file associations -->
    <DirectoryRef Id="INSTALLFOLDER">
      <Component Id="Program" Bitness="always64">
        <File Id="LanternleafExe" Name="Lanternleaf.exe" Source="$(var.ReleaseDir)\$(var.ExeName)" KeyPath="yes" />

        <!-- .fb2 opens in Lanternleaf; Windows still lets the user pick another default -->
        <ProgId Id="Lanternleaf.Book" Description="FictionBook book" Icon="LanternleafExe" IconIndex="0"
                Advertise="no">
          <Extension Id="fb2" ContentType="application/x-fictionbook+xml">
            <Verb Id="open" Command="Open" TargetFile="LanternleafExe" Argument="&quot;%1&quot;" />
          </Extension>
        </ProgId>

        <!-- "Open with > Lanternleaf" for .fb2, .txt, .pdf and zipped books, without taking over .txt, .pdf or .zip -->
        <RegistryKey Root="HKLM" Key="Software\Classes\Applications\Lanternleaf.exe">
          <RegistryValue Name="FriendlyAppName" Value="Lanternleaf" Type="string" />
          <RegistryValue Key="shell\open\command" Value="&quot;[#LanternleafExe]&quot; &quot;%1&quot;" Type="string" />
          <RegistryValue Key="SupportedTypes" Name=".fb2" Value="" Type="string" />
          <RegistryValue Key="SupportedTypes" Name=".txt" Value="" Type="string" />
          <RegistryValue Key="SupportedTypes" Name=".pdf" Value="" Type="string" />
          <RegistryValue Key="SupportedTypes" Name=".zip" Value="" Type="string" />
        </RegistryKey>
        <RegistryValue Root="HKLM" Key="Software\Classes\.fb2\OpenWithProgids" Name="Lanternleaf.Book" Value=""
                       Type="string" />
        <RegistryValue Root="HKLM" Key="Software\Classes\.txt\OpenWithList\Lanternleaf.exe" Value=""
                       Type="string" />
        <RegistryValue Root="HKLM" Key="Software\Classes\.pdf\OpenWithList\Lanternleaf.exe" Value=""
                       Type="string" />
        <RegistryValue Root="HKLM" Key="Software\Classes\.zip\OpenWithList\Lanternleaf.exe" Value=""
                       Type="string" />
      </Component>
    </DirectoryRef>

    <!-- Everything else in release\Windows: VC++ runtime DLLs, notices, assets\ (fonts, hyphenation, licences).
         Program files of every version are left out: older ones stay in the release folder after a version bump. -->
    <ComponentGroup Id="ProgramFiles" Directory="INSTALLFOLDER">
      <Files Include="$(var.ReleaseDir)\**">
        <Exclude Files="$(var.ReleaseDir)\Lanternleaf*.exe" />
      </Files>
    </ComponentGroup>
  </Package>
</Wix>
```

## `installer/License.rtf`

ASCII, LF line endings, ends with a newline.

```text
{\rtf1\ansi\ansicpg1252\deff0{\fonttbl{\f0\fswiss\fcharset0 Segoe UI;}}
\viewkind4\uc1\pard\sa120\f0\fs18
\b MIT License\b0\par
Copyright (c) 2026 Vitali Pinzari\par
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\par
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\par
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\par
\b Third-party components\b0\par
Lanternleaf includes third-party software and fonts (SDL3, PT Sans and PT Serif under the SIL Open Font License, hyphenation patterns and others). Their licences are installed with the program in THIRD-PARTY-NOTICES.txt and the assets\\licenses folder.\par
}
```
