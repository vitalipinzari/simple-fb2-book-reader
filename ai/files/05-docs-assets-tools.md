# Documentation, project workflow files, asset texts and the icon generator

The README (MIT edition), the original build prompt, the change list, the bug and feature backlog files, the texts that ship in assets/ (hyphenation notes and the third-party notices shown in the About panel) and the icon generator.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `README.md` | 23223 | `b8a04f4208753cb5…` |
| `PROMPT.md` | 1796 | `c02071ce80a8f273…` |
| `CHANGELIST.md` | 2596 | `519a47fe61899f1c…` |
| `bugs/prompt.md` | 648 | `45586d612cd635bb…` |
| `bugs/report.md` | 964 | `07f3c687257f1e62…` |
| `features/prompt.md` | 644 | `d36d5c139fc6575f…` |
| `features/features.md` | 2685 | `8699dd93d0441fcd…` |
| `assets/hyphenation/README.md` | 868 | `a928eb8c68d9ac3b…` |
| `assets/licenses/THIRD-PARTY-NOTICES.txt` | 27755 | `b82c1746735fb68e…` |
| `tools/make_icon.py` | 6426 | `5544ee73ceb98367…` |

## `README.md`

UTF-8 without BOM, CRLF line endings, ends with a newline.

````markdown
# Lanternleaf

A quiet book reader for **FB2**, **TXT** and **PDF**, drawn entirely on the GPU. It reflows text with TeX-quality line
breaking and hyphenation for English and Russian, turns pages with a 3D page curl, has science-based night
themes, and can dig books out of an unsorted *Downloads* folder by file name, title, author or a phrase from
the text.

It runs on **Windows 11 x64** and **Android** (phones, tablets, Chromebooks) from one C++20 code base:
SDL3, a portable core, and shaders written for both OpenGL 4.1 core and OpenGL ES 3.0.

Version 0.7.0 · © 2026 Vitali Pinzari. Released under the MIT License (see [LICENSE](LICENSE)).

| Day, two pages | Night amber | 3D page curl | Two-page turn |
|---|---|---|---|
| ![day](docs/day-two-pages.png) | ![amber](docs/night-amber.png) | ![curl](docs/page-curl.png) | ![spread](docs/spread-turn.png) |

> **About the name:** "Lanternleaf" means a leaf (page) read by lantern light. A web search in November 2026
> found no book reader with this name; only similar names came up (*Leaf e-Reader*, *OpenLeaf*, the
> *Lantern* Bible app).

## Features

- **GPU text rendering.** Every glyph is a textured quad in an OpenGL scene. A FreeType glyph atlas uses
  light hinting and 4 sub-pixel positions, and HarfBuzz does shaping (kerning, ligatures, combining stress
  marks) with per-character font fallback. Pictures, video, backgrounds and other scripts can be added to the
  same pipeline later.
- **One page or an open book.** *1 page* / *2 pages* on the toolbar (B on the keyboard; under *Menu* when the toolbar is short of room)
  switches between a single page and two pages side by side with a spine. One page is the default;
  *Automatic* shows two pages when the window is wide. Book mode also works on a narrow screen as long as each
  page stays readable (about 18 characters a line); otherwise Lanternleaf says the screen is too narrow.
- **Four ways to turn a page** (*Settings → Page turning*):
  - **3D page curl:** the page is a mesh bent around a moving cylinder in a perspective camera, with
    lighting, a see-through paper back side and a cast shadow. In book mode the right page flips over the
    spine and lands carrying the next left page.
  - **Slide:** the page (both pages in book mode) slides away to the left when going forward, and to the
    right when going back.
  - **Fade out and in:** the old page fades to the bare paper, then the new one appears.
  - **Instant** (the default): no animation and no flicker. The next and previous pages are drawn ahead, in idle
    time, into textures, so a turn only puts a finished picture on screen.
- **Toolbar.** The same toolbar on every screen: it shows the buttons that fit, and whatever does not fit a phone
  (upright or sideways) or a narrow window is under **Menu** at its right end, together with *About*. The desktop
  window cannot be made smaller than 10 % of its monitor's width and height.
- **Menu and status bar.** The toolbar at the top and a status bar at the bottom come and go together (pointer at
  the top or bottom edge, a tap in the middle of the page on phones). The status bar shows the chapter, a progress
  bar with chapter marks, the page and the percentage, and each of them works: the chapter opens the contents, a
  click or drag on the bar jumps there, and the page number or the percentage can be typed in. While the bars show,
  the page is laid out between them, so they never cover the text; hidden, the text fills the whole screen.
- **Panels** (contents, settings, library, help ...) open one at a time in the top left corner of the page and
  cover half of it: the left half on a wide screen, the top half on a tall one.
- **Three formats:**
  - **FB2:** sections, titles, epigraphs, poems and stanzas, citations, subtitles, emphasis, strong,
    strikethrough, sup/sub, footnotes (click a note number to see it in a pop-up), cover and embedded
    pictures. The parser is tolerant of broken files. `.fb2.zip` archives (common in Russian libraries) open
    directly.
  - **TXT:** paragraphs are rebuilt from hard-wrapped, indented or blank-line separated text, and chapter
    headings (Chapter, Глава, Часть, roman numerals…) go into the contents. `--` and spaced hyphens become
    em dashes, and Project Gutenberg boilerplate and `_italic_` markup are handled.
  - **PDF:** read by Lanternleaf's own PDF reader (no PDF library is used). The text of every page is put back
    into reflowable paragraphs, so a PDF gets the same fonts, themes, zoom and hyphenation as any other book:
    running heads, page numbers and decorations are removed, hyphenated line ends are joined, and headings,
    lists, tables (rows with `|` between the cells), code, footnotes and drop caps are recognised. Pictures stay in
    reading order, two-column pages are read column by column, the PDF outline becomes the contents and the first
    page's picture the cover. Damaged files (the cross-reference table is rebuilt) and encrypted files that open
    without a password (RC4, AES-128, AES-256) open too.
- **Zoom with reflow.** Ctrl + mouse wheel, Ctrl +/-, or a two-finger pinch. Text reflows around the reading
  position: the line you were reading stays on screen, and the same applies to window resizing.
- **Hyphenation and line breaking.** Lines are broken with the Knuth–Plass "total fit" algorithm (TeX) and
  hyphenated with Liang's algorithm using the TeX `hyph-utf8` patterns for American English and Russian. A
  greedy fallback and emergency splitting handle URLs and other unbreakable strings. Russian typographic
  rules apply: a dash never starts a line, and a dialogue dash stays with its first word.
- **Colour themes:**
  - Day (black on white)
  - Sepia
  - Dusk (warm, almost no blue)
  - Night amber (~600 nm)
  - Night red (>610 nm, keeps eyes dark-adapted)

  A brightness slider dims the text or the paper, and an optional clock-based day/night switch is
  available. Themes colour the text only:
  - Pictures always keep their own colours.
  - Web addresses are always blue and underlined, and open in the browser. That includes addresses written as
    plain text, such as the Project Gutenberg licence.

  See [the science notes](#why-these-night-themes) below.
- **Start where you left off.** The last book reopens at the same place, together with the window, the font
  and the theme. Positions are stored per book with a content fingerprint, so a book that was renamed or
  moved still resumes.
- **Finding books on disk** (Ctrl+F) searches chosen folders or all drives in the background, with results
  streaming in:
  - **File name:** includes transliteration, so *Толстой*, *Tolstoy* and *Tolstoj* all find
    `Tolstoy_Voyna-i-mir.fb2.zip`.
  - **Title, author, series:** read from FB2 and PDF metadata and cached, so repeated searches are instant.
  - **Text inside books:** finds a whole phrase, ignoring case, *ё/е* and typographic quotes.
  - **Empty query:** lists every book found, which is useful for sorting out a Downloads mess.

  System folders, licence and readme files, and OneDrive online-only placeholders are skipped.
- **Encodings and languages.** UTF-8, UTF-16 and the Russian legacy encodings Windows-1251, KOI8-R, CP866 and
  ISO-8859-5 are detected automatically by letter-frequency analysis; the FB2 XML declaration is honoured,
  and a wrong declaration is detected. English and Russian are fully supported. Other Latin and Cyrillic
  languages render correctly but are not hyphenated.
- **Also included:**
  - Table of contents
  - Find in the current book, with highlighting
  - Go to a page or percentage
  - Page numbers counted in the background while the status bar shows
  - Click or tap outside a menu or panel to close it and return to the page
  - Full screen
  - Recent books list
  - Drag and drop, file association friendly (`Lanternleaf.exe book.fb2`)
  - Idle CPU use is zero: the loop sleeps until something happens

## Building

Requires **Visual Studio 2026** with the *Desktop development with C++* workload. It already contains MSVC,
CMake, Ninja and vcpkg; nothing else needs to be installed.

```powershell
./build.ps1            # Release build. The first run builds the dependencies with vcpkg (about 7 min).
./build.ps1 -Test      # build and run the unit tests
./build.ps1 -Run       # build and start the reader
./build.ps1 -Config Debug
```

### Release folder

Every Release build, however it is started (`build.ps1`, Visual Studio or plain CMake), is also copied into
`release/<Platform>/`, ready to run or ship. File names carry the version:

```
release/
  Windows/   Lanternleaf-0.2.0.exe, assets/, msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll,
             THIRD-PARTY-NOTICES.txt
  Android/   Lanternleaf-0.2.0.apk
```

**Version.** The single source is the `VERSION` file in the repository root. CMake and Gradle read it. It
appears in:

- the release file names;
- the app's *About* panel (and *Help*);
- the Windows file properties (version, copyright);
- the Android version name, with the version code as major·10000 + minor·100 + patch.

Bump it for every release. Earlier versions stay in the release folders next to the new one.

**Windows installer.** `./build-msi.ps1` packages `release\Windows` into
`release\Installer\Lanternleaf-<version>-x64.msi` with the WiX Toolset (downloaded into `build\tools` on the
first run; needs the .NET SDK). It installs per machine into `Program Files\Lanternleaf`, adds a Start menu
shortcut, makes `.fb2` open in Lanternleaf and adds it to *Open with* for `.txt`, `.pdf` and `.zip`. A newer MSI
replaces the installed version; reader settings in `%APPDATA%\Lanternleaf` are kept on uninstall. The source
is in `installer/`.

The Windows folder is self-contained. Libraries are linked statically and the Visual C++ runtime DLLs are
placed next to the exe, so you can copy the folder to any 64-bit Windows 10/11 PC and run it. If the staged
app is running while you build, the folder is left unchanged and the build prints a warning; close the app and
build again. Debug builds are never staged. Turn staging off with `-DLL_STAGE_RELEASE=OFF`.

The build itself lives in `build\vs2026\<Config>\Lanternleaf.exe`, with `assets` next to it.

You can also open the folder in Visual Studio (*File → Open → Folder*) and pick the *Visual Studio 2026
(x64)* preset, or run `cmake --preset vs2026` yourself with `VCPKG_ROOT` pointing at a vcpkg installation.

Dependencies (vcpkg manifest, pinned baseline): SDL3, FreeType, HarfBuzz, Dear ImGui (SDL3 + OpenGL3
backends), glad, miniz, stb, nlohmann-json.

## Android

The same C++ code runs on Android 9+ (phones, tablets, Chromebooks): OpenGL ES 3.0 renderer, SDL3, and the
same layout, hyphenation, FB2/TXT/PDF readers and library search.

```powershell
./build-android.ps1                 # -> release\Android\Lanternleaf-<version>.apk (arm64-v8a + x86_64, signed)
./build-android.ps1 -Install -Run   # ... and install + start it on a connected phone or emulator
```

The build needs:

- **Android Studio** for the SDK, NDK 28.2.13676358, CMake 3.22.1 and its bundled JDK.
- **Visual Studio 2026** for vcpkg.

The script finds both. You can also open the `android` folder in Android Studio once the script has written
`android/local.properties`.

**Signing:** release APKs are signed with `android/keystore/lanternleaf-release.jks`, and its passwords are
in `android/keystore.properties`. Both are excluded from version control. Back them up: updates of an
installed app must be signed with the same key. Without them, Gradle falls back to the debug key.

What is different on a phone:

| | |
|---|---|
| Turn pages | tap the right part / left third of the page, or swipe |
| Bigger / smaller text | two-finger pinch (reflows, keeps your place) or A+ / A- |
| Menu and status bar | tap the middle of the page; buttons that do not fit the toolbar are under **Menu** at its right end; any tap on the page outside them hides them again |
| Screen brightness | swipe up or down on the left part of the page (Lanternleaf's own brightness; *Settings → Screen* has the slider and *Use the system brightness*) |
| One page / book | the **1 page** / **2 pages** buttons, or **Menu → One page** / **Two pages, like a book** when they do not fit |
| Panels | open in the top left half of the page over the dimmed page and stay in place; tap the page beside them (or Back) to return to reading |
| Back button | closes the open panel; on the page it leaves the app (the position is saved) |
| Finding books | **Find books** searches Download, Documents, Books and Telegram folders, or the whole device and SD cards. Android 11+ asks once for *All files access*, needed to read books outside the app's own folder |
| Opening books | **Open a book** browses folders; FB2/TXT/PDF/ZIP files can also be opened *with Lanternleaf* from file managers and messengers |
| Screen | immersive full screen and kept on while reading (both in Settings); text and buttons stay clear of the camera notch; turned sideways, two pages side by side |
| Keyboard | search fields get no auto-capitalisation or autocorrect flags; the page number field gets a number pad |

**If no books show up** (*Open a book* lists only folders, *Find books* finds "0 files"): Android hides
other apps' files from Lanternleaf until it has **All files access**.

1. On the first start Lanternleaf asks for it; the notices in *Find books* and *Open a book* have the same
   **Allow access** button.
2. Switch on *Allow access to manage all files* and come back. The list and the last search refresh on their
   own.
3. If the switch is greyed out (Android 13+ restricts some settings for apps installed from an APK file): go
   to *Settings → Apps → Lanternleaf → ⋮ → Allow restricted settings* and try again.

You can check the state in *Menu → About Lanternleaf*.

## Using it

| What | How |
|---|---|
| Next / previous page | → ↓ PgDn Space, mouse wheel, click the right part of the page / ← ↑ PgUp Shift+Space Backspace, click the left third |
| First / last page | Home / End |
| Bigger / smaller text | Ctrl + wheel, Ctrl+Plus / Ctrl+Minus, pinch; Ctrl+0 resets |
| Open a book | Ctrl+O or drag a file onto the window |
| Find books on disk / in this book | Ctrl+F / Ctrl+Shift+F |
| Recent books | Ctrl+L |
| Contents, Go to, Settings, Help | T, Ctrl+G, Ctrl+Comma, F1 |
| Colour theme | C / Shift+C, Ctrl+1 … Ctrl+5 |
| Toolbar and status bar | move the pointer to the top or bottom edge; right click or F10 pins them |
| Status bar | click the chapter (contents), the bar (jump, or drag), the page number or percentage (type one in) |
| Full screen | F11 or Alt+Enter |
| Footnote | click the note number |

Settings, reading positions, the search cache and a log file are stored in `%APPDATA%\Lanternleaf\`.

## Why these night themes

- **Day and Sepia.** Dark text on a light page (positive polarity) gives the best legibility in a lit room
  (Piepenbrock et al., *Ergonomics* 2013).
- **Why blue light matters at night.** Short-wavelength light, around 460–480 nm, suppresses melatonin most
  strongly, through the melanopsin cells of the retina (Brainard et al., *J Neurosci* 2001; Thapan et al.,
  *J Physiol* 2001). Reading on a light-emitting e-reader before bed delays sleep and circadian timing, and
  lowers next-morning alertness (Chang et al., *PNAS* 2015).
- **Dusk** keeps a warm, low-contrast palette with almost no blue for the evening.
- **Night amber** emits only long-wavelength light (~600 nm). Blocking blue with amber filters improved
  sleep in a randomised trial (Burkhart & Phelps, *Chronobiol Int* 2009).
- **Night red** stays above ~610 nm, where rods are almost blind, so your eyes remain dark-adapted. This is
  the reason astronomers, pilots and ship crews use red light at night. Combine it with the Brightness
  slider.

## Architecture

```
src/core      portable C++20, no SDL/GL: document model, FB2, TXT and PDF readers, encodings, zip,
              Liang hyphenation, Knuth–Plass line breaking, library search and metadata cache
src/text      FreeType + HarfBuzz: fonts, shaping cache, paragraph and page layout (BookLayout)
src/render    OpenGL 4.1 core / ES 3.0: glyph atlas, batched 2D renderer, 3D page turn
src/app       SDL3 application (main callbacks), settings, themes, Dear ImGui panels
src/platform  OS specifics: folders, drives, system fonts, cloud placeholders
tests         unit tests for the core and the layout engine (840 checks)
assets        PT Serif / PT Sans (OFL) and the hyphenation patterns
tools         make_icon.py (generates the application icon)
cmake         StageRelease.cmake (copies each Release build to release/<Platform>)
release       ready-to-run builds per platform (generated by the build)
```

Key design decisions:

- **Shaping is resolution independent.** Words are shaped once into em units and cached, so changing the font
  size only re-breaks lines and never reshapes text.
- **The reading position is a position in the text,** (paragraph, byte offset), not a page number. Pages are
  built on demand forwards or backwards from any line, so a zoom on a 3 MB book shows the new page in about
  1 ms. Page numbers come from a background pass that paginates the whole book in small time slices (about
  0.4 s of work for 1600 pages).
- **Going backwards matches going forwards.** At chapter starts the previous chapter is paginated forwards
  from its beginning, so going back shows exactly the pages you saw.

### How the Android build is put together

- **App model:** `android/` is a Gradle project, Android Gradle Plugin 9.3 with SDK 36. Its Java side is
  SDL3's glue (`org.libsdl.app`, from SDL 3.4.18) plus `LanternleafActivity`, which handles "Open with"
  intents (`content://` books are copied into app storage so they can be reopened after a restart), the
  *All files access* permission and the list of storage volumes. Native code calls these through JNI from
  `src/platform/Platform.cpp`.
- **Safe area:** `LanternleafSurface` reports only what covers content, the system bars and the camera
  cutout. SDL's own safe area also excludes the 30 dp back-gesture zones at both edges.
- **Native code:** Gradle builds the same root `CMakeLists.txt` with the SDK's CMake 3.22 into `libmain.so`.
  SDL3 is linked statically in its entirety, including its JNI entry points. Dependencies come from vcpkg
  (`arm64-android` and `x64-android`, with one install tree per ABI under `build/vcpkg_android/`).
  vcpkg cannot cross-build HarfBuzz for Android on a Windows host (its Meson build rejects Windows
  paths), so on Android HarfBuzz 14.6.0 is compiled from its official single-file `harfbuzz.cc`, pinned by
  SHA-256 (`cmake/HarfBuzzAmalgamated.cmake`).
- **Graphics:** shaders use the GLSL 4.10 / ES 3.00 common subset, and `render/Gl.h` switches to
  `<GLES3/gl3.h>`, so no glad is needed on Android.
- **Assets** are packaged from the shared `assets` folder and loaded with `SDL_LoadFile`.
- **Touch input:** gestures come from SDL finger events: tap zones, swipes and two-finger pinch.
  Touch-synthesised mouse clicks are ignored for page turning. Dear ImGui gets finger scrolling, and a
  scrolling drag never activates the item it ends on.

## Testing

- `ll_tests` covers the core and the layout engine:
  - UTF-8 and case folding
  - Encoding detection (cp1251, KOI8-R, CP866, UTF-16, cp1252)
  - The tolerant XML reader
  - FB2: structure, styles, footnotes, cover, broken markup
  - TXT paragraph heuristics and typography
  - PDF: the lexer, the stream filters (Flate, LZW, ASCIIHex, ASCII85, RunLength, PNG predictors),
    cross-reference tables and streams, object streams, repairing damaged files, composite fonts with
    ToUnicode maps, pictures, the security handler (MD5, SHA-2, RC4 and AES checked against their standard
    test vectors), and the paragraphs, headings, hyphenated line ends and outline of a generated book
  - Hyphenation
  - Line breaking
  - Transliteration matching
  - Library search on a temporary folder tree, including zip
  - Layout:
    - no overflow, justified edges;
    - pagination forwards and backwards, page counting;
    - zoom anchoring, unbreakable URLs;
    - headings taller than a page, and headings never ending a page.
  - Web addresses found in plain text: trailing punctuation and brackets, Cyrillic paths, existing links left
    alone, styles kept around the new link.
- **Screenshot mode** renders off-screen and writes a PNG. It is used for visual checks and never touches your
  settings unless `--allow-save` is given:

```powershell
Lanternleaf.exe --settings-dir <dir> --screenshot out.png --size 1280x820 [--theme night-amber]
  [--font-size 24] [--columns auto|1|2] [--page-turn curl|slide|fade|none] [--goto 37] [--next 3] [--turn 0.4]
  [--panel toc|settings|help|about|library|goto|browser|folders|storage]
  [--search "query" --search-root <dir> [--search-content]] [--find "phrase" [--find-go]]
  [--click x,y ...] [--allow-save] book.fb2
```

`--click x,y` (repeatable) sends a left click at window coordinates through the normal event path, one step
per frame: move, press, release. It is used to check that a click outside a menu or panel closes it.

- **Log:** `lanternleaf.log` in the settings folder. On quitting it also says how many Instant page turns were
  served from the pages prepared ahead.

## Known limitations

- Right-to-left and vertical scripts are shaped but not laid out right to left.
- Pictures placed inside a running paragraph are skipped; block pictures and the cover are shown.
- FB2 and PDF tables are simplified to rows with `|` separators.
- PDF pages are reflowed, not shown as printed. Drawings made of vector graphics are not shown (their
  pictures and text are), and scanned pages need a text layer or JPEG pictures: JPEG 2000, JBIG2 and CCITT
  fax pictures are skipped. Files that need a password to open are not supported.
- There is no text selection, copying, bookmarks or annotations yet.

## Credits and licences

**Lanternleaf** © 2026 Vitali Pinzari (developer). Released under the MIT License (see [LICENSE](LICENSE)). The app's *About* panel shows the
version, the credits and the full licence texts of the components below
(`assets/licenses/THIRD-PARTY-NOTICES.txt`).

- **Fonts:** PT Serif and PT Sans by ParaType, under the SIL Open Font License (`assets/fonts/OFL-*.txt`).
- **Hyphenation patterns** from [hyph-utf8](https://github.com/hyphenation/tex-hyphen):
  - American English by Gerard D.C. Kuiken (permissive notice)
  - Russian by Alexander I. Lebedev (LPPL 1.2+)

  See `assets/hyphenation/README.md`.
- **Libraries:** SDL3 (zlib), FreeType (FTL), HarfBuzz (MIT), Dear ImGui (MIT), glad (MIT), miniz (MIT),
  stb (public domain / MIT), nlohmann-json (MIT).
````

## `PROMPT.md`

UTF-8 without BOM, LF line endings, ends with a newline.

```markdown
# Book Reader — Build Prompt

## TARGET
- **Platform:** Windows 11 (x64) desktop. Keep the code portable (and as much as possible shareable between platforms) for a later Android port (OpenGL ES 3.0, touch).
- **Language and stack:** C++20, CMake + vcpkg, SDL3, OpenGL 4.1 core (GLSL kept compatible with GLSL ES 3.00).
- **Input:** keyboard + mouse.
- **Title:** Suggest a uniq one, that not in current market.

## 1. Your task

Build **Title from TARGET section**, Simple book reader from screen.

## 2. Hard rules
**3D** reader should use 3d graphics to display text, this will allow easy integration in future any complex fonts, images, videos, backgrounds and so on.
**Format.** reader should understand only 2 formats, fb2 and txt.
**Scale** user should be able easily scale text/font ctrl+mouse scroll, etc (in future for Android port in's just simple 2 finger gesture) - text rearrages automatically, keep a same reading position in the book.
**word hyphenation** if last word in line does not fit, move it to next line or use any proven tactics that exist with current readers.
**Colors** initially lets add several color schema, standard: black text, white background; night friendly: Amber / Warm Orange text, black background (with science proven Extended evening reading; reading color-coded material.) - you can add more night friendly schema that science recommed.
**Start where last left** application starts from same point user closed it.
**Search** application should be able to search books on local drive/s by file name, by file content: like title, author or text inside book (it could be slow but it most important feature to find a book in unsorted mess in download folder/folders).
**Language** at least English and Russian language text in books should be supported. 
```

## `CHANGELIST.md`

ASCII, LF line endings, ends with a newline.

```markdown
# Application Change List
Any confirmed/verifyed bug fixes and feature short summary goes here.

## 0.6.0 (2026-11-02)
- Fixed: search results (and other lists under controls) were out of reach in short panels on landscape phones and small desktop windows, because the list only got the height left below the controls. The list now takes most of the panel and the panel scrolls; on touch screens a list at its top or bottom passes the drag on to the panel.

## 0.5.0 (2026-11-02)
- Fixed: the toolbar was cut off on landscape phones and narrow desktop windows. Phones (both orientations) and the desktop now share one toolbar: buttons that do not fit (the least used first) go into a Menu at its right end, which always has About. Back/Esc with the menu open now closes only the menu.
- Added (desktop): the window cannot be made smaller than 10 % of its monitor's width and height (recomputed when it moves to another monitor or the resolution changes).

## 0.4.0 (2026-11-02)
- Fixed: the Settings panel moved while its list was scrolled on Android (finger scrolling and Dear ImGui's window dragging ran at once). Panels now move only by their title bar and stay fixed on touch screens; an up/down drag always scrolls, also when it starts on a slider or check box, and a sideways drag moves a slider.
- Added (Android): screen brightness by swiping up/down on the left third of the page. It sets the brightness of Lanternleaf's own window (no permission, other apps unaffected), is saved, and Settings > Screen has a slider and "Use the system brightness".
- Changed: first-start defaults are the Day theme, one page and instant page turns.
- Changed: panels (library, contents, settings, go to, help, about, file browser) open in the top left corner of the reading area and cover half of it: the left half on wide screens, the top half on tall ones.
- Changed: opening a panel closes any other open panel, on all platforms.
- Added: a status bar with the chapter, a progress bar with chapter marks, the page and the percentage. It shows and hides with the toolbar and replaces the footer that was always drawn under the text.
- Added: the status bar is interactive: the chapter opens Contents, a click or drag on the progress bar jumps there, and the page number or percentage can be typed in (on phones in a box below the toolbar, above the keyboard).
- Changed: while the toolbar and status bar show, the page is laid out between them; hidden, the text fills the screen. Only the page breaks are redone (lines are kept) and the page count of both heights is cached, so switching is instant.
```

## `bugs/prompt.md`

ASCII, CRLF line endings, ends with a newline.

```markdown
## this folder contains
file prompt.md that contains structure of this folder with description, rules of how agent needs to work with files and items inside of this folder.
file report.md that conatains list of discovered bugs with attached screentshots
bug screenshot files.

## rules
after successful fixing a bug, mark bug inside of report.md file as fixed.
after developer mark fixed bug as confirmed/verified in next iteration remove this bug from report.md and assotiated screenshots with this bug.
short summary of a fixed bug with steps to fix should be added to CHANGELIST.md after bug removal due it's verified/confirmed status.
```

## `bugs/report.md`

ASCII, CRLF line endings except LF after line 13, ends with a newline.

```markdown
# structure
This file conatins list of bugs
Each bug can have following but not limited sections:
Platform: - platform name where bug has been found, we optional data about platform version, device, etc.
Description: - actual description of a bug, with/whithout repro steps, analysis, developer/tester thoughts about root cause, etc
Screenshot: file names of screenshots assotiated with this bug if any.
AppVersionFound: application version where bug is found
Status: bug status, can have meaningful values like, fixed (set by AI/Developer who fixed this bug), verified/confirmed (bug fix has been tested and confirmed that it's not repro anymore)

Any bugs with verified/confirmed status should be removed on next iteration (new claude session started, developer prompt, bug fix, feature request, etc)
Removed bugs and ther fix description should be added as items in CHANGELIST.md - short summary of a bug and fix is preffered option there. 

##bugs
```

## `features/prompt.md`

ASCII, CRLF line endings, ends with a newline.

```markdown
## this folder contains
file prompt.md that contains structure of this folder with description, rules of how agent needs to work with files and items inside of this folder.
file features.md that conatains list of requested features.

## rules
after successful feature implementation, mark bug inside of features.md file as implemented.
after developer mark implemented feature as confirmed/verified, in next iteration remove this feature from features.md.
short summary of a implemented feature with steps/way of implementation should be added to CHANGELIST.md after feature removal from features.md due it's verified/confirmed status.
```

## `features/features.md`

ASCII, CRLF line endings, ends with a newline.

```markdown
# structure
This file conatins list of requested features
Each feature can have following but not limited sections:
Platform: - platform/s name/s where feature should be implemented, in case if this section is missed implementation should be on all supported by app platforms.
Description: - actual description of a feature request.
Status: feature status, can have meaningful values like, implemented (set by AI/Developer who implemented requested featue), verified/confirmed (feature implementation has been tested and confirmed that it's working as intended)

Any features with verified/confirmed status should be removed on next iteration (new claude session started, developer prompt, bug fix, feature request, etc)
Removed features and their implementation description should be added as items in CHANGELIST.md - short summary of a feature and implementation is preffered option there. 

## features

### PDF books
Description: Add PDF support without depending on a PDF reader library: a minimal implementation of the PDF standard
that reads and shows at least the books in the `test-books` folder (Alex Xu - System Design Interview, Second Edition;
Bhardwaj R. - System Design with AI Interview Guide - 2026; Sellers M. - Advanced Game Design. A Systems Approach - 2017).
Implementation: four new core modules, no new dependencies (miniz inflates, stb_image decodes JPEG as before).
`PdfReader` reads the file structure: objects, cross-reference tables and streams, object streams, the stream filters
(Flate, LZW, ASCIIHex, ASCII85, RunLength, PNG/TIFF predictors) and rebuilds a damaged cross-reference table by
scanning. `PdfCrypt` is the standard security handler for files that open without a password (RC4, AES-128,
AES-256). `PdfContent` walks the page tree, loads fonts (standard encodings, Differences, glyph names, ToUnicode
maps, composite fonts, widths) and interprets content streams into positioned characters and placed pictures,
skipping /Artifact content (running heads, page numbers) and applying ActualText. `PdfParser` turns the pages into a
reflowable book: lines, columns, running heads and page numbers removed, paragraphs joined across lines and pages,
hyphenated line ends joined, headings, lists, tables, code, footnotes and drop caps recognised, pictures in reading
order (still compressed in memory, decoded when shown), the outline as the contents and the first page's picture as
the cover. PDF files open from the Open dialog, drag and drop, the file browser, Find books (title and author from the
PDF metadata, text search inside PDFs), Android "Open with" and the installer's "Open with".
Status: implemented (0.7.0)
```

## `assets/hyphenation/README.md`

ASCII, LF line endings, ends with a newline.

```markdown
# Hyphenation patterns

The `*.pat.txt` (patterns) and `*.hyp.txt` (exceptions) files come unmodified from the
[hyph-utf8](https://github.com/hyphenation/tex-hyphen) project (`hyph-utf8/tex/generic/hyph-utf8/patterns/txt`).
Lanternleaf applies them with Frank Liang's algorithm, the same one TeX uses.

| File | Language | Author | Licence | Hyphen mins (left, right) |
|------|----------|--------|---------|---------------------------|
| `hyph-en-us.*` | American English | Copyright (C) 1990, 2004, 2005 Gerard D.C. Kuiken | Copying and distribution of this file, with or without modification, are permitted in any medium without royalty provided the copyright notice and this notice are preserved. | 2, 3 |
| `hyph-ru.*` | Russian | Copyright (C) 1999-2003 Alexander I. Lebedev | LaTeX Project Public License 1.2 or later (https://latex-project.org/lppl/) | 2, 2 |
```

## `assets/licenses/THIRD-PARTY-NOTICES.txt`

UTF-8 without BOM, CRLF line endings, ends with a newline.

```text
Lanternleaf - third-party notices
==================================

Lanternleaf includes the following open-source components. Their licences are reproduced below.

Fonts: PT Serif and PT Sans, Copyright (c) 2010-2011 ParaType Inc. - SIL Open Font License 1.1
  (full text: assets/fonts/OFL-PTSerif.txt and assets/fonts/OFL-PTSans.txt).
Hyphenation patterns: the hyph-utf8 project - American English by Gerard D.C. Kuiken,
  Russian by Alexander I. Lebedev and others (LaTeX Project Public License / MIT; see
  assets/hyphenation/README.md).

==================== SDL 3 (zlib licence; parts under the BSD licence) ====================

LICENSE.txt:

Copyright (C) 1997-2026 Sam Lantinga <slouken@libsdl.org>
  
This software is provided 'as-is', without any express or implied
warranty.  In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:
  
1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required. 
2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.



LICENSE-bsd.txt:

Copyright (c) 2010, Alan Ott, Signal 11 Software
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of Signal 11 Software nor the names of its
      contributors may be used to endorse or promote products derived from
      this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.



SDL also contains small components under other permissive licences; see https://github.com/libsdl-org/SDL.

==================== FreeType (used under the FreeType License, FTL) ====================

LICENSE.TXT:

FREETYPE LICENSES
-----------------

The FreeType  2 font  engine is  copyrighted work  and cannot  be used
legally without  a software  license.  In order  to make  this project
usable to  a vast majority of  developers, we distribute it  under two
mutually exclusive open-source licenses.

This means that *you* must choose  *one* of the two licenses described
below, then obey all its terms and conditions when using FreeType 2 in
any of your projects or products.

  - The FreeType License,  found in the file  `docs/FTL.TXT`, which is
    similar to the  original BSD license *with*  an advertising clause
    that forces  you to explicitly  cite the FreeType project  in your
    product's  documentation.  All  details are  in the  license file.
    This license is suited to products which don't use the GNU General
    Public License.

    Note that  this license  is compatible to  the GNU  General Public
    License version 3, but not version 2.

  - The   GNU   General   Public   License   version   2,   found   in
    `docs/GPLv2.TXT`  (any  later  version  can  be  used  also),  for
    programs  which  already  use  the  GPL.  Note  that  the  FTL  is
    incompatible with GPLv2 due to its advertisement clause.

The contributed  BDF and PCF  drivers come  with a license  similar to
that  of the  X Window  System.   It is  compatible to  the above  two
licenses (see files `src/bdf/README`  and `src/pcf/README`).  The same
holds   for   the   source    code   files   `src/base/fthash.c`   and
`include/freetype/internal/fthash.h`; they were part of the BDF driver
in earlier FreeType versions.

The gzip  module uses the  zlib license (see  `src/gzip/zlib.h`) which
too is compatible to the above two licenses.

The   files   `src/autofit/ft-hb-ft.c`,   `src/autofit/ft-hb-decls.h`,
`src/autofit/ft-hb-types.h`,     and    `src/autofit/hb-script-list.h`
contain code taken (almost) verbatim  from the HarfBuzz library, which
uses the 'Old MIT' license compatible to the above two licenses.

The  MD5 checksum  support  (only used  for  debugging in  development
builds) is in the public domain.


--- end of LICENSE.TXT ---


FTL.TXT:

                    The FreeType Project LICENSE
                    ----------------------------

                            2006-Jan-27

                    Copyright 1996-2002, 2006 by
          David Turner, Robert Wilhelm, and Werner Lemberg



Introduction
============

  The FreeType  Project is distributed in  several archive packages;
  some of them may contain, in addition to the FreeType font engine,
  various tools and  contributions which rely on, or  relate to, the
  FreeType Project.

  This  license applies  to all  files found  in such  packages, and
  which do not  fall under their own explicit  license.  The license
  affects  thus  the  FreeType   font  engine,  the  test  programs,
  documentation and makefiles, at the very least.

  This  license   was  inspired  by  the  BSD,   Artistic,  and  IJG
  (Independent JPEG  Group) licenses, which  all encourage inclusion
  and  use of  free  software in  commercial  and freeware  products
  alike.  As a consequence, its main points are that:

    o We don't promise that this software works. However, we will be
      interested in any kind of bug reports. (`as is' distribution)

    o You can  use this software for whatever you  want, in parts or
      full form, without having to pay us. (`royalty-free' usage)

    o You may not pretend that  you wrote this software.  If you use
      it, or  only parts of it,  in a program,  you must acknowledge
      somewhere  in  your  documentation  that  you  have  used  the
      FreeType code. (`credits')

  We  specifically  permit  and  encourage  the  inclusion  of  this
  software, with  or without modifications,  in commercial products.
  We  disclaim  all warranties  covering  The  FreeType Project  and
  assume no liability related to The FreeType Project.


  Finally,  many  people  asked  us  for  a  preferred  form  for  a
  credit/disclaimer to use in compliance with this license.  We thus
  encourage you to use the following text:

   """
    Portions of this software are copyright © <year> The FreeType
    Project (https://freetype.org).  All rights reserved.
   """

  Please replace <year> with the value from the FreeType version you
  actually use.


Legal Terms
===========

0. Definitions
--------------

  Throughout this license,  the terms `package', `FreeType Project',
  and  `FreeType  archive' refer  to  the  set  of files  originally
  distributed  by the  authors  (David Turner,  Robert Wilhelm,  and
  Werner Lemberg) as the `FreeType Project', be they named as alpha,
  beta or final release.

  `You' refers to  the licensee, or person using  the project, where
  `using' is a generic term including compiling the project's source
  code as  well as linking it  to form a  `program' or `executable'.
  This  program is  referred to  as  `a program  using the  FreeType
  engine'.

  This  license applies  to all  files distributed  in  the original
  FreeType  Project,   including  all  source   code,  binaries  and
  documentation,  unless  otherwise  stated   in  the  file  in  its
  original, unmodified form as  distributed in the original archive.
  If you are  unsure whether or not a particular  file is covered by
  this license, you must contact us to verify this.

  The FreeType  Project is copyright (C) 1996-2000  by David Turner,
  Robert Wilhelm, and Werner Lemberg.  All rights reserved except as
  specified below.

1. No Warranty
--------------

  THE FREETYPE PROJECT  IS PROVIDED `AS IS' WITHOUT  WARRANTY OF ANY
  KIND, EITHER  EXPRESS OR IMPLIED,  INCLUDING, BUT NOT  LIMITED TO,
  WARRANTIES  OF  MERCHANTABILITY   AND  FITNESS  FOR  A  PARTICULAR
  PURPOSE.  IN NO EVENT WILL ANY OF THE AUTHORS OR COPYRIGHT HOLDERS
  BE LIABLE  FOR ANY DAMAGES CAUSED  BY THE USE OR  THE INABILITY TO
  USE, OF THE FREETYPE PROJECT.

2. Redistribution
-----------------

  This  license  grants  a  worldwide, royalty-free,  perpetual  and
  irrevocable right  and license to use,  execute, perform, compile,
  display,  copy,   create  derivative  works   of,  distribute  and
  sublicense the  FreeType Project (in  both source and  object code
  forms)  and  derivative works  thereof  for  any  purpose; and  to
  authorize others  to exercise  some or all  of the  rights granted
  herein, subject to the following conditions:

    o Redistribution of  source code  must retain this  license file
      (`FTL.TXT') unaltered; any  additions, deletions or changes to
      the original  files must be clearly  indicated in accompanying
      documentation.   The  copyright   notices  of  the  unaltered,
      original  files must  be  preserved in  all  copies of  source
      files.

    o Redistribution in binary form must provide a  disclaimer  that
      states  that  the software is based in part of the work of the
      FreeType Team,  in  the  distribution  documentation.  We also
      encourage you to put an URL to the FreeType web page  in  your
      documentation, though this isn't mandatory.

  These conditions  apply to any  software derived from or  based on
  the FreeType Project,  not just the unmodified files.   If you use
  our work, you  must acknowledge us.  However, no  fee need be paid
  to us.

3. Advertising
--------------

  Neither the  FreeType authors and  contributors nor you  shall use
  the name of the  other for commercial, advertising, or promotional
  purposes without specific prior written permission.

  We suggest,  but do not require, that  you use one or  more of the
  following phrases to refer  to this software in your documentation
  or advertising  materials: `FreeType Project',  `FreeType Engine',
  `FreeType library', or `FreeType Distribution'.

  As  you have  not signed  this license,  you are  not  required to
  accept  it.   However,  as  the FreeType  Project  is  copyrighted
  material, only  this license, or  another one contracted  with the
  authors, grants you  the right to use, distribute,  and modify it.
  Therefore,  by  using,  distributing,  or modifying  the  FreeType
  Project, you indicate that you understand and accept all the terms
  of this license.

4. Contacts
-----------

  There are two mailing lists related to FreeType:

    o freetype@nongnu.org

      Discusses general use and applications of FreeType, as well as
      future and  wanted additions to the  library and distribution.
      If  you are looking  for support,  start in  this list  if you
      haven't found anything to help you in the documentation.

    o freetype-devel@nongnu.org

      Discusses bugs,  as well  as engine internals,  design issues,
      specific licenses, porting, etc.

  Our home page can be found at

    https://freetype.org


--- end of FTL.TXT ---

==================== HarfBuzz (Old MIT licence) ====================

COPYING:

HarfBuzz is licensed under the so-called "Old MIT" license.  Details follow.
For parts of HarfBuzz that are licensed under different licenses see individual
files names COPYING in subdirectories where applicable.

Copyright © 2010-2022  Google, Inc.
Copyright © 2015-2020  Ebrahim Byagowi
Copyright © 2019,2020  Facebook, Inc.
Copyright © 2012,2015  Mozilla Foundation
Copyright © 2011  Codethink Limited
Copyright © 2008,2010  Nokia Corporation and/or its subsidiary(-ies)
Copyright © 2009  Keith Stribley
Copyright © 2011  Martin Hosken and SIL International
Copyright © 2007  Chris Wilson
Copyright © 2005,2006,2020,2021,2022,2023  Behdad Esfahbod
Copyright © 2004,2007,2008,2009,2010,2013,2021,2022,2023  Red Hat, Inc.
Copyright © 1998-2005  David Turner and Werner Lemberg
Copyright © 2016  Igalia S.L.
Copyright © 2022  Matthias Clasen
Copyright © 2018,2021  Khaled Hosny
Copyright © 2018,2019,2020  Adobe, Inc
Copyright © 2013-2015  Alexei Podtelezhnikov

For full copyright notices consult the individual files in the package.


Permission is hereby granted, without written agreement and without
license or royalty fees, to use, copy, modify, and distribute this
software and its documentation for any purpose, provided that the
above copyright notice and the following two paragraphs appear in
all copies of this software.

IN NO EVENT SHALL THE COPYRIGHT HOLDER BE LIABLE TO ANY PARTY FOR
DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES
ARISING OUT OF THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN
IF THE COPYRIGHT HOLDER HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH
DAMAGE.

THE COPYRIGHT HOLDER SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING,
BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE.  THE SOFTWARE PROVIDED HEREUNDER IS
ON AN "AS IS" BASIS, AND THE COPYRIGHT HOLDER HAS NO OBLIGATION TO
PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.


COPYING:

    MIT License

    Copyright (c) Microsoft Corporation.

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
    SOFTWARE



==================== Dear ImGui (MIT licence) ====================

LICENSE.txt:

The MIT License (MIT)

Copyright (c) 2014-2026 Omar Cornut

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


imgui-proggyclean-license-139ec08a38096161291792313ef5803fc4f0e37b.txt:

MIT License

Copyright (c) 2004, 2005 Tristan Grimmer

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


imgui-proggyforever-license-f8868ba43bb42c4d88454d03ad81cbd139789f72.txt:

The MIT License (MIT)

Copyright (c) 2026 Disco Hello
Copyright (c) 2019,2023 Tristan Grimmer

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



==================== miniz (MIT licence) ====================

Copyright 2013-2014 RAD Game Tools and Valve Software
Copyright 2010-2014 Rich Geldreich and Tenacious Software LLC

All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

==================== JSON for Modern C++ by Niels Lohmann (MIT licence) ====================

MIT License 

Copyright (c) 2013-2025 Niels Lohmann

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

==================== stb by Sean Barrett (MIT licence / public domain) ====================

stb libraries are single files and licensed individually, please refer comments in each individual file for licensing.

This software is available under 2 licenses -- choose whichever you prefer.
------------------------------------------------------------------------------
ALTERNATIVE A - MIT License
Copyright (c) 2017 Sean Barrett
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
------------------------------------------------------------------------------
ALTERNATIVE B - Public Domain (www.unlicense.org)
This is free and unencumbered software released into the public domain.
Anyone is free to copy, modify, publish, use, compile, sell, or distribute this
software, either in source code form or as a compiled binary, for any purpose,
commercial or non-commercial, and by any means.
In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain. We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors. We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

==================== glad (Windows build; MIT / Apache-2.0) ====================

The glad source code:

    The MIT License (MIT)

    Copyright (c) 2013-2021 David Herberth

    Permission is hereby granted, free of charge, to any person obtaining a copy of
    this software and associated documentation files (the "Software"), to deal in
    the Software without restriction, including without limitation the rights to
    use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
    the Software, and to permit persons to whom the Software is furnished to do so,
    subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
    FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
    COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
    IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


The Khronos Specifications:

    Copyright (c) 2013-2020 The Khronos Group Inc.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.


The EGL Specification and various headers:

    Copyright (c) 2007-2016 The Khronos Group Inc.

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and/or associated documentation files (the
    "Materials"), to deal in the Materials without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Materials, and to
    permit persons to whom the Materials are furnished to do so, subject to
    the following conditions:

    The above copyright notice and this permission notice shall be included
    in all copies or substantial portions of the Materials.

    THE MATERIALS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
    TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
    MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.

```

## `tools/make_icon.py`

ASCII, LF line endings, ends with a newline.

```python
"""Generates the Lanternleaf icons: an amber leaf glowing on a dark page.

Outputs
  <res>/lanternleaf.ico, <res>/lanternleaf.png              Windows icon (16..256 px) and a 256 px PNG
  <android>/mipmap-*/ic_launcher.png                        legacy launcher icons (48..192 px)
  <android>/mipmap-*/ic_launcher_foreground.png             adaptive icon foreground (108 dp, transparent)

Needs numpy only. Run e.g. with Blender's bundled Python:
  "<blender>/5.2/python/bin/python.exe" -I tools/make_icon.py res android/app/src/main/res
"""
import struct
import sys
import zlib
from pathlib import Path

import numpy as np


def over(dst_rgb, dst_a, src_rgb, src_a):
    """Porter-Duff 'over' with straight (non-premultiplied) colours."""
    out_a = src_a + dst_a * (1.0 - src_a)
    num = src_rgb * src_a[..., None] + dst_rgb * (dst_a * (1.0 - src_a))[..., None]
    out_rgb = np.where(out_a[..., None] > 1e-6, num / np.maximum(out_a[..., None], 1e-6), 0.0)
    return out_rgb, out_a


def render(size: int, background: bool = True, zoom: float = 1.0) -> np.ndarray:
    """RGBA float image (size x size). `zoom` < 1 shrinks the artwork (adaptive icon safe zone)."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    x = ((xs + 0.5) / size * 2.0 - 1.0) / zoom
    y = (1.0 - (ys + 0.5) / size * 2.0) / zoom
    px = 2.0 / size / zoom

    def smooth_mask(d):
        return np.clip(0.5 - d / px, 0.0, 1.0)

    rgb = np.zeros((size, size, 3))
    alpha = np.zeros((size, size))

    if background:
        half, radius = 0.94, 0.24
        qx = np.maximum(np.abs(x) - (half - radius), 0.0)
        qy = np.maximum(np.abs(y) - (half - radius), 0.0)
        bg_a = smooth_mask(np.sqrt(qx * qx + qy * qy) - radius)
        t = (y + 1.0) * 0.5
        top = np.array([0.13, 0.10, 0.075])
        bottom = np.array([0.045, 0.035, 0.028])
        bg_rgb = bottom[None, None, :] * (1 - t[..., None]) + top[None, None, :] * t[..., None]
        rgb, alpha = over(rgb, alpha, bg_rgb, bg_a)
        clip = bg_a
    else:
        clip = np.ones((size, size))

    # warm glow behind the leaf
    r2 = x * x + (y - 0.02) ** 2
    glow = 0.56 * np.exp(-r2 / 0.30) * clip
    amber = np.broadcast_to(np.array([1.0, 0.62, 0.18]), (size, size, 3))
    rgb, alpha = over(rgb, alpha, amber, glow)

    # leaf: a lens (intersection of two circles) rotated by 45 degrees
    c, s = np.cos(np.pi / 4), np.sin(np.pi / 4)
    u = c * x + s * y
    v = -s * x + c * y
    R, a = 0.80, 0.50
    d1 = np.sqrt(u * u + (v - a) ** 2) - R
    d2 = np.sqrt(u * u + (v + a) ** 2) - R
    d_leaf = np.maximum(d1, d2)
    leaf_a = smooth_mask(d_leaf)
    k = np.clip((u + v * 0.3 + 0.7) / 1.4, 0, 1)
    leaf_lo = np.array([0.90, 0.42, 0.08])
    leaf_hi = np.array([1.00, 0.80, 0.32])
    leaf_rgb = leaf_lo[None, None, :] * (1 - k[..., None]) + leaf_hi[None, None, :] * k[..., None]
    rim = np.clip(1.0 - np.abs(d_leaf) / (px * 3 + 0.02), 0, 1) * 0.25
    leaf_rgb = np.clip(leaf_rgb + rim[..., None] * np.array([1.0, 0.9, 0.6])[None, None, :], 0, 1)
    rgb, alpha = over(rgb, alpha, leaf_rgb, leaf_a)

    # side veins (chevrons pointing to the tip), clipped to the leaf
    vein_rgb = np.broadcast_to(np.array([0.45, 0.20, 0.04]), (size, size, 3))
    side = np.zeros_like(x)
    for off in (-0.36, -0.12, 0.12, 0.36):
        line = np.abs((u - off) * 0.55 - np.abs(v)) * 0.9
        seg = np.maximum(line - 0.012, np.abs(v) - 0.24)
        side = np.maximum(side, smooth_mask(seg))
    rgb, alpha = over(rgb, alpha, vein_rgb, side * leaf_a * 0.55)

    # central vein and stem
    half_len = np.sqrt(R * R - a * a)
    d_vein = np.maximum(np.abs(v) - 0.022 * (1.0 - 0.6 * (u + half_len) / (2 * half_len)), np.abs(u) - half_len * 0.92)
    stem = np.maximum(np.abs(v + 0.015 * (u + half_len)) - 0.03, np.maximum(-(u + half_len) - 0.17, u + half_len - 0.06))
    vein_a = smooth_mask(np.minimum(d_vein, stem)) * np.maximum(leaf_a, smooth_mask(stem))
    rgb, alpha = over(rgb, alpha, vein_rgb, vein_a)

    return np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=-1)


def downsample(img: np.ndarray, size: int) -> np.ndarray:
    f = img.shape[0] // size
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    pm = pm.reshape(size, f, size, f, 4).mean(axis=(1, 3))
    a = pm[..., 3:4]
    rgb = np.where(a > 1e-6, pm[..., :3] / np.maximum(a, 1e-6), 0)
    return np.concatenate([rgb, a], axis=-1)


def png_bytes(img: np.ndarray) -> bytes:
    h, w, _ = img.shape
    data = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    raw = b"".join(b"\x00" + data[row].tobytes() for row in range(h))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def icon(size: int, background: bool = True, zoom: float = 1.0) -> bytes:
    return png_bytes(downsample(render(size * 4, background, zoom), size))  # 4x4 supersampling


def main() -> None:
    res = Path(sys.argv[1] if len(sys.argv) > 1 else "res")
    res.mkdir(parents=True, exist_ok=True)
    sizes = [256, 128, 64, 48, 32, 24, 16]
    images = [icon(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    offset = 6 + 16 * len(sizes)
    for s, png in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    (res / "lanternleaf.ico").write_bytes(header + entries + b"".join(images))
    (res / "lanternleaf.png").write_bytes(images[0])
    print("wrote", res / "lanternleaf.ico")

    if len(sys.argv) > 2:
        android = Path(sys.argv[2])
        densities = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
        for name, k in densities.items():
            d = android / f"mipmap-{name}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "ic_launcher.png").write_bytes(icon(int(48 * k)))
            # Adaptive icons: 108 dp canvas, artwork within the central 66 dp safe zone.
            (d / "ic_launcher_foreground.png").write_bytes(icon(int(108 * k), background=False, zoom=0.62))
        print("wrote Android launcher icons to", android)


if __name__ == "__main__":
    main()
```
