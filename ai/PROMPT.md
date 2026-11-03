# Lanternleaf 0.6.0 — regeneration prompt

You are an expert C++20 / OpenGL / Android engineer working as an autonomous coding agent. Your task is to
re-create **Lanternleaf 0.6.0**, a GPU-rendered FB2/TXT e-book reader, as an **exact copy** of the original — for
every platform the original supports — using only the material in this `ai/` folder. Nobody will answer
questions while you work: everything you need is here, and where something is genuinely left open you decide as
described under *Ground rules* and report it at the end.

The result is published under the **MIT License** (see *Licence* below).

---

## 1. What you are building

Lanternleaf is a quiet book reader for **FB2** (incl. `.fb2.zip`) and **TXT**. Every glyph is a textured quad in
an OpenGL scene; text is shaped with HarfBuzz, rasterised with FreeType into a glyph atlas, broken into lines with
the Knuth–Plass algorithm and hyphenated with Liang's algorithm (English and Russian TeX patterns). Pages turn
with a 3D page curl, a slide, a fade, or instantly from pre-rendered textures. It has science-based night themes,
keeps the reading position per book (by content fingerprint), zooms with reflow around the reading position, and
finds books on disk by file name (with transliteration), FB2 metadata or a phrase from the text.

| Platform | Details |
|---|---|
| **Windows 11 x64** (also Windows 10) | desktop window, keyboard + mouse; OpenGL 4.1 core via glad; static libraries, VC++ runtime DLLs next to the exe |
| **Android 9+** (API 28–36) | phones, tablets, Chromebooks; `arm64-v8a` and `x86_64`; OpenGL ES 3.0; touch gestures; SDL3's Java glue plus a small activity |

One C++20 code base: SDL3 (main callbacks), a portable core without SDL/GL, shaders in the common subset of GLSL
4.10 core and GLSL ES 3.00, Dear ImGui for the panels. CMake + vcpkg build both platforms (Gradle drives CMake on
Android). Non-Windows desktop builds (Linux/macOS) only have the generic fallbacks the platform layer and the
release staging already contain; they are not a supported target and need no extra work.

## 2. The material in `ai/`

| Path | What it is | How to use it |
|---|---|---|
| `PROMPT.md` | this file: mission, rules, plan, definition of done | read first, follow throughout |
| `README.md` | how a human uses this folder | — |
| `LICENSE` | MIT licence of this folder | keep |
| `spec/01-product.md` | the product: features, behaviour, platforms, defaults, controls | read first; the overview every module serves |
| `spec/02-build-and-release.md` | repository layout, toolchain, CMake/vcpkg, versioning, release staging, code conventions | read before writing any file |
| `spec/03-core-foundation.md` | Unicode, encodings, XML reader, document model, file and image helpers | implement `src/core/{Unicode,Encoding,XmlReader,Document,FileUtil,ImageCodec}.cpp` |
| `spec/04-book-formats.md` | FB2 and TXT parsers, zip, book loader, fingerprint | implement `src/core/{Fb2Parser,TxtParser,BookLoader}.cpp` |
| `spec/05-hyphenation-and-line-breaking.md` | Liang hyphenation, Knuth–Plass line breaking | implement `src/core/{Hyphenator,LineBreaker}.cpp` |
| `spec/06-library-search.md` | finding books on disk, transliteration, metadata cache | implement `src/core/LibrarySearch.cpp` |
| `spec/07-fonts-shaping-layout.md` | FreeType faces, HarfBuzz shaping, paragraph and page layout | implement `src/text/{FontLibrary,Shaper,BookLayout}.cpp` |
| `spec/08-rendering.md` | GL helpers, glyph atlas, 2D batch renderer, 3D page turn (shaders verbatim) | implement `src/render/{GlCommon,GlyphAtlas,Renderer2D,PageTurn}.cpp` |
| `spec/09-application.md` | the SDL3 application: start-up, input, navigation, rendering, persistence, automation | implement `src/app/App.cpp` |
| `spec/10-user-interface.md` | toolbar, menu, status bar, panels, pop-ups, file browser (all texts verbatim) | implement `src/app/{AppUi,FileBrowser}.cpp` |
| `spec/11-platform-and-android.md` | platform layer, Android project, SDL Java glue, signing, device checks | Android build |
| `spec/12-assets-and-icons.md` | fonts, hyphenation patterns, licence texts, icons — sources and checksums | fill `assets/`, `res/`, launcher icons |
| `spec/13-tests-and-verification.md` | unit tests and their exact expected output, screenshot mode, visual and device checks | verify every phase |
| `spec/14-docs-and-workflow.md` | README, docs screenshots, change list, bug/feature backlog, release habits | finish the repository |
| `files/01…05-*.md` | **verbatim files**: every header, the entry point, platform/theme/settings code, build scripts, CMake, Gradle, manifest, Java, tests, README and docs | reproduce byte for byte (tool below) |
| `files/checksums.sha256` | SHA-256 of every verbatim file and every asset | verify |
| `reference/` | `sample-book.fb2` (written for these prompts) and 15 screenshots the **original** 0.6.0 rendered from it, with the exact commands | render the same with your build and compare (spec 13 § 2) |
| `tools/unpack_files.py` | writes all verbatim files from `files/*.md` and checks them | `python -I ai/tools/unpack_files.py .` |
| `tools/make_bundles.py` | maintainer tool: regenerates `files/` from a source tree | not needed for the rebuild |

Precedence when two sources seem to disagree: **verbatim files** > **module spec (03–14)** > **product spec (01)**.
A module spec is the authority on its own `.cpp` files; the headers in `files/02-source-interfaces.md` are the
authority on every declaration.

## 3. Ground rules

1. **Exact copy, not a re-design.** Same file names and paths, same classes, functions and members (the
   verbatim headers fix them), same algorithms, constants, strings, defaults, file formats, command-line flags,
   log lines and UI texts as the specs give. Do not add features, options, files, dependencies or abstractions;
   do not rename, "modernise", reformat or "fix" anything the specs describe — odd behaviour that a spec describes
   is part of the copy.
2. **Verbatim means byte for byte.** Write the verbatim files with `ai/tools/unpack_files.py` (or reproduce them
   exactly by hand), then run `python -I ai/tools/unpack_files.py . --check`. Never edit a verbatim file; if
   something does not compile against one, your implementation is wrong, not the file.
3. **Implementation files** (the `.cpp` files listed in section 2) are written by you from their specs. Use the
   code conventions of spec 02 so they read like the rest of the code base. Every behaviour, number and string in
   a spec must be in the code; behaviour that no spec describes must not be.
4. **When something is genuinely unspecified**, choose the simplest behaviour that is consistent with the specs
   and the verbatim headers and comments, keep it local, and list it in your final report under *Decisions*. Do
   not stop to ask.
5. **Text encoding.** Every source and text file is UTF-8 without BOM (line endings as the verbatim files state;
   your own files use LF). Cyrillic, typographic quotes, dashes, arrows and ellipses in strings must survive
   exactly. On Windows never round-trip text through PowerShell 5.1 `Get-Content`/`Set-Content` (it reads BOM-less
   UTF-8 as Windows-1252 and garbles it); use your file tools, or `[IO.File]::ReadAllText/WriteAllText` with UTF-8.
6. **Secrets stay out.** The original Android release key is not part of this folder. Create your own
   (spec 11), keep `android/keystore/` and `android/keystore.properties` out of version control (the verbatim
   `.gitignore` already does), and never print passwords into files you deliver.
7. **Your own scratch files** (downloads, test books, throwaway projects, screenshots for checking) go in a temp
   folder outside the repository, not into it. The repository must end up containing exactly what spec 02 lists.
8. **Test as you go.** Build and run the unit tests after each phase; do not move on with failing checks.

## 4. Reference environment

Exactness is defined against the tool versions 0.6.0 was built with. Newer ones usually work; if you must
deviate (e.g. a version is no longer available), say so in the final report.

| Area | Version |
|---|---|
| OS | Windows 11 x64 |
| C++ toolchain | Visual Studio 2026 (Build Tools 18.10.3 is enough: *Desktop development with C++*), MSVC 14.51.36231, CMake 4.3.1-msvc1 (bundled), generator `Visual Studio 18 2026`, the vcpkg bundled with Visual Studio (tool 2026-07-27) |
| vcpkg baseline | `9a5dfef5d1a0438a7d24856a85bd60f309d355e9` → SDL3 3.4.18, FreeType 2.14.3, HarfBuzz 14.6.0, Dear ImGui 1.93.0, glad 0.1.36 (GL 4.1 core API), miniz 3.1.2, nlohmann-json 3.12.0 (port version 2), stb 2026-08-02 |
| Android | Android Studio (bundled JetBrains Runtime 21.0.10 as the JDK), SDK platform `android-36.1`, build-tools 36.0.0, NDK r28c `28.2.13676358`, SDK CMake 3.22.1, Gradle 9.5.0 (wrapper), Android Gradle Plugin 9.3.2, Java source/target 17 |
| HarfBuzz on Android | 14.6.0 from its single-file `harfbuzz.cc`, archive SHA-256 `eca8581e5ad8e21dbda31556c0363f764b1a754c9c1bb33ca7cd56ca1c07ddc9` (downloaded by `cmake/HarfBuzzAmalgamated.cmake`) |
| Icons | Python 3 with numpy (Blender 5.2's bundled Python 3.13.13 + numpy 2.3.4 + zlib 1.3.1 reproduces the icons byte for byte) |
| Tools in `ai/tools` | any Python 3.8+, standard library only |

## 5. Work plan

Work through the phases in order. Each ends with a check; fix problems before going on.

**Phase 0 — Read.** Read this file, `spec/01-product.md` and `spec/02-build-and-release.md` completely, then skim
the other specs and `files/02-source-interfaces.md` to see how the modules fit together. Before implementing a
module, read its spec completely.

**Phase 1 — Repository skeleton.** In the (empty) target folder that contains `ai/`:
`python -I ai/tools/unpack_files.py .` writes all 65 verbatim files (build system, headers, entry point,
platform/theme/settings code, Android project, tests, README and docs). Create the remaining folders of spec 02.
Check: `python -I ai/tools/unpack_files.py . --check` reports 0 problems.

**Phase 2 — Assets and icons** (spec 12). Download the PT Serif / PT Sans fonts and the hyphenation patterns into
`assets/`, generate the icons with `tools/make_icon.py`. Check: every asset line of `files/checksums.sha256`
matches.

**Phase 3 — Core** (specs 03–06). Implement the twelve `src/core/*.cpp` files. Configure with
`./build.ps1 -Test -CMakeArgs "-DLL_BUILD_TEXT=OFF","-DLL_BUILD_APP=OFF"` (the test program then links
`ll_core` only and skips the layout tests). Check: no failures.

**Phase 4 — Text and layout** (spec 07). Implement `src/text/*.cpp` and reconfigure with `-DLL_BUILD_TEXT=ON`
(cache variables persist, so pass it explicitly). Check: `ll_tests` prints **exactly** the reference output in
spec 13 — the same groups, the same diagnostic numbers (kerning, line/hyphen/page statistics) and
`751 checks, 0 failures`. The diagnostics are produced by the layout engine on the bundled fonts, so a
different number means a behavioural difference: find it.

**Phase 5 — Windows application** (specs 08, 09, 10; platform code is verbatim). Implement `src/render/*.cpp`,
`src/app/App.cpp`, `src/app/AppUi.cpp`, `src/app/FileBrowser.cpp`, reconfigure with `-DLL_BUILD_APP=ON` and
build with `./build.ps1 -Test`. Check: the tests still pass, `release/Windows/` holds `Lanternleaf-0.6.0.exe` +
`assets/` + the three VC++ runtime DLLs + `THIRD-PARTY-NOTICES.txt`, and the screenshot-mode checks of spec 13
pass (look at every image you make and compare it with what the specs describe).

**Phase 6 — Android** (spec 11). Add SDL 3.4.18's Java glue, the Gradle wrapper and a release key, then
`./build-android.ps1`. Check: `release/Android/Lanternleaf-0.6.0.apk` (arm64-v8a + x86_64, signed with your key),
installs and runs on an Android emulator or device, and passes the device checks of spec 13.

**Phase 7 — Documentation and workflow** (spec 14). Regenerate the four README screenshots in `docs/` with
screenshot mode, make sure `README.md`, `PROMPT.md`, `CHANGELIST.md`, `bugs/` and `features/` are in place (they
are verbatim), and run the final checklist below.

**Phase 8 — Report.** Finish with a short report: what was built and where (release paths), test output, the
checks you ran and their results, every *Decision* you had to make (rule 4), and any deviation from the
reference environment.

## 6. Definition of done

- [ ] `python -I ai/tools/unpack_files.py . --check` → 0 problems; every asset checksum matches.
- [ ] All `.cpp` files of spec 02's layout exist; no other source files were added.
- [ ] `./build.ps1 -Test` succeeds; `ll_tests` output equals the reference output of spec 13 line for line.
- [ ] `release/Windows/Lanternleaf-0.6.0.exe` starts, opens FB2, FB2.ZIP and TXT books (cp1251, KOI8-R, UTF-16
      and UTF-8 test files), turns pages in all four page-turn styles, zooms with reflow, switches themes, shows
      every panel, finds books on disk, and reopens the last book at the same place after a restart.
- [ ] The screenshot-mode and interaction checks of spec 13 pass.
- [ ] `release/Android/Lanternleaf-0.6.0.apk` builds, installs and passes the device checks of spec 13
      (gestures, panels, All files access flow, Open with, landscape two pages, Back button behaviour).
- [ ] `docs/` has the four screenshots the README links to; the About panel and the Windows file properties show
      version 0.6.0 and the MIT licence wording below.
- [ ] Nothing secret or machine-specific is in the delivered files (no keystore, no `local.properties`).

## 7. Licence (MIT edition)

The original 0.6.0 said "All rights reserved". This copy is published under the MIT License, © 2026 Vitali
Pinzari. That is the only intended difference from the original, and it shows in exactly four places, all
already applied in the verbatim files and specs:

1. `LICENSE` at the repository root: the MIT License text, "Copyright (c) 2026 Vitali Pinzari" (in
   `files/01-build-system.md`).
2. `README.md`: both places that said "All rights reserved." say "Released under the MIT License (see
   [LICENSE](LICENSE))." (in `files/05-docs-assets-tools.md`).
3. `res/lanternleaf.rc.in`: `LegalCopyright` is "Copyright (C) @LL_COPYRIGHT_YEAR@ @LL_DEVELOPER@. MIT License."
   (in `files/01-build-system.md`).
4. The About panel: its copyright line (after the description paragraph) reads "© 2026 Vitali Pinzari.
   Released under the MIT License." (`ImGui::Text("%s. Released under the MIT License.", LL_COPYRIGHT)`, in
   `spec/10-user-interface.md`).

Third-party components keep their own licences (SDL3 zlib, FreeType FTL, HarfBuzz MIT, Dear ImGui MIT, glad
MIT/Apache-2.0, miniz MIT, nlohmann-json MIT, stb MIT/public domain, PT fonts SIL OFL 1.1, hyphenation patterns
under their own notices), exactly as the bundled notices describe.
