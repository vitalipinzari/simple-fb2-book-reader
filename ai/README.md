# Lanternleaf regeneration prompts

This folder lets an AI coding agent rebuild **Lanternleaf 0.7.0** — the GPU-rendered FB2/TXT/PDF book reader for
Windows 11 x64 and Android 9+ (arm64-v8a, x86_64) — as an exact copy, from nothing but what is in here: the same
features, behaviour, look, texts, file layout, build system, tests and release folders. It is published under the
MIT License (`LICENSE`), and so is the application it regenerates (see `PROMPT.md` § 7 for the four places where
that shows).

## How to use it

1. Create an empty folder and copy this `ai/` folder into it.
2. Install the tools of `PROMPT.md` § 4: Visual Studio 2026 (or its Build Tools) with *Desktop development with
   C++*; Android Studio with SDK platform 36.1, NDK 28.2.13676358 and CMake 3.22.1; Python 3 (with numpy for the
   icons — Blender's bundled Python works); the .NET SDK for the WiX Toolset that builds the MSI installer; internet
   access for vcpkg, the fonts, the hyphenation patterns, SDL's Java glue and Gradle.
3. Start a coding agent with file, shell and build access in that folder (for example Claude Code) and give it
   this prompt:

   > Read `ai/PROMPT.md` and follow it to the end.

The agent works through eight phases (skeleton, assets, core, layout, Windows app, Android, docs, report), checks
each against the unit tests' exact expected output and the reference renders, and finishes with a report of what
it built and every decision it had to make. A full run is long — the original is about 20 000 lines of C++ — so
it can also be split over several sessions: give each session `ai/PROMPT.md` plus the phase to do, in order.

Without an agent that can run tools, paste `PROMPT.md`, then the spec and the bundle of the part you want, into a
chat and save the files it writes; the verbatim bundles can always be unpacked with
`python -I ai/tools/unpack_files.py <target folder>`.

## What is inside

```
PROMPT.md                 the master prompt: mission, ground rules, reference environment, work plan, definition of done
LICENSE                   MIT
spec/01-product.md        what the app is and does, controls, defaults, data files, command line
spec/02-build-and-release.md   repository layout, CMake/vcpkg, version, release staging, code conventions
spec/03 … 10, 15          implementation specs of every .cpp file that is not verbatim:
                            03 Unicode, encodings, XML, document model, files, images
                            04 FB2, TXT, zip, book loader          05 Liang hyphenation, Knuth–Plass line breaking
                            06 library search, transliteration      07 FreeType, HarfBuzz, book layout
                            08 GL helpers, glyph atlas, renderer, 3D page turn (shaders verbatim)
                            09 the SDL application                  10 the Dear ImGui user interface (texts verbatim)
                            15 PDF: file structure, filters, encryption, fonts, content streams, reflow
spec/11-platform-and-android.md   platform layer, Gradle project, Java, SDL glue, signing, emulator procedures
spec/12-assets-and-icons.md       fonts, patterns, licence texts, icons: sources and SHA-256
spec/13-tests-and-verification.md exact expected test output, screenshot mode, desktop and device checks
spec/14-docs-and-workflow.md      README screenshots, change list, backlog, release habits
files/01 … 05-*.md        72 files reproduced byte for byte (headers, entry point, platform/theme/settings code,
                          CMake, scripts, installer source, Gradle, manifest, Java, tests, README and docs)
files/checksums.sha256    SHA-256 of every verbatim file and asset
reference/                a sample book written for these prompts and 15 screenshots the original rendered from it
tools/unpack_files.py     writes the verbatim files into a folder and checks them
tools/make_bundles.py     maintainer tool: regenerates files/ from the Lanternleaf repository
```

## What is not included, on purpose

- **The original Android signing key.** The copy is signed with a key you create (spec 11 § 5).
- **Third-party files with their own licences:** the PT Serif / PT Sans fonts (SIL OFL), the hyph-utf8
  hyphenation patterns, SDL's Java glue (zlib) and the Gradle wrapper are downloaded or generated, then checked
  against the checksums.
- **The original's private test books and older release binaries** (0.1.0–0.6.0); a copy starts at 0.7.0.
- **Implementation source of the algorithms and the UI.** Headers, glue, data, build files and tests are verbatim;
  the 26 algorithm and UI `.cpp` files are specified (every constant, string and branch) and written by the agent.
  The result is the same program, file by file and function by function, but these `.cpp` files are not
  byte-identical to the original's.

## Keeping it up to date

When Lanternleaf changes, run `python -I ai/tools/make_bundles.py` in the repository: it rewrites `files/` and the
checksums from the current sources and warns about any new file that no bundle or spec
covers. Then update the specs of the changed `.cpp` files, the expected test output (spec 13 § 1), the reference
renders (`reference/README.md` lists the commands) and the version in `PROMPT.md`.

## Licence

MIT, © 2026 Vitali Pinzari — see `LICENSE`. Third-party components keep their own licences, as listed in
`spec/12-assets-and-icons.md` and in the app's notices.
