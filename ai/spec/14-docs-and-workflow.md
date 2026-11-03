# 14 — Documentation, screenshots, change list, backlog and release habits

Scope: the repository's documentation and the working conventions of the project — the README and its four
screenshots, the original brief, the change list, the bug and feature backlog folders, and the release habits
that every later iteration of the copy follows. All text files here are verbatim in
`ai/files/05-docs-assets-tools.md`; the screenshots are made with the app itself.

## 1. `README.md` (verbatim, MIT edition)

The user manual and developer overview, in this order: title and one-paragraph pitch; platforms and stack;
version line ("Version 0.6.0 · © 2026 Vitali Pinzari. Released under the MIT License (see [LICENSE](LICENSE)).");
a four-image table (*Day, two pages* / *Night amber* / *3D page curl* / *Two-page turn*); the note on the name;
**Features**; **Building** (Visual Studio 2026, `build.ps1` options, the release folder and the version);
**Android** (`build-android.ps1`, requirements, signing, what is different on a phone, what to do when no books
show up); **Using it** (key table, data folder `%APPDATA%\Lanternleaf\`); **Why these night themes** (the
literature behind Day/Sepia, blue light and melatonin, Dusk, Night amber, Night red); **Architecture** (folders,
key design decisions, how the Android build is put together); **Testing** (`ll_tests` coverage, screenshot mode
with its full option synopsis, the log); **Known limitations**; **Credits and licences**.

It is reproduced byte for byte (CRLF line endings, as the bundle states). Some of its statements describe the
history of the original working folder (for example the release folder example still names 0.2.0 files); keep
them as they are — the README is part of the exact copy.

## 2. README screenshots (`docs/`)

The README links four PNGs. The original's were rendered from A. P. Chekhov's «Степь» (public domain) in screenshot
mode by earlier versions of the app; render them again with your 0.6.0 build so they show the current look:

| File | Size | Command options (plus `--settings-dir <fresh tmp> --screenshot docs\<file>`) |
|---|---|---|
| `docs/day-two-pages.png` | 1300 × 800 | `--size 1300x800 --theme day --columns 2 --goto 3` |
| `docs/night-amber.png` | 640 × 860 | `--size 640x860 --theme night-amber --goto 3` |
| `docs/page-curl.png` | 640 × 860 | `--size 640x860 --theme sepia --page-turn curl --goto 3 --turn 0.4` |
| `docs/spread-turn.png` | 1300 × 800 | `--size 1300x800 --theme day --columns 2 --page-turn curl --goto 3 --turn 0.5` |

Use any public-domain FB2 of «Степь» (Chekhov, 1888) if you can get one; otherwise use
`ai/reference/sample-book.fb2` with `--next 2` instead of `--goto 3`. Never use a copyrighted book for images that
are published with the repository. Look at each image before keeping it (text pages, no panel, curl caught
mid-turn).

## 3. `PROMPT.md` (verbatim)

The original brief the project was started from ("Book Reader — Build Prompt": target platform, stack, hard
rules for 3D rendering, formats, scaling, hyphenation, colours, resume, search, languages). It is history and
stays unchanged; this regeneration prompt lives in `ai/PROMPT.md`.

## 4. Change list and backlog (verbatim)

- `CHANGELIST.md` — "Application Change List": verified bug fixes and features per version, newest first
  (0.6.0, 0.5.0, 0.4.0 with dates). Only items the developer has verified go here.
- `bugs/prompt.md` — the rules of the bug folder; `bugs/report.md` — the bug list template (Platform,
  Description, Screenshot, AppVersionFound, Status) with an empty `##bugs` section. Screenshots of bugs sit next to
  the report.
- `features/prompt.md` — the rules of the feature folder; `features/features.md` — the feature list template
  (Platform, Description, Status) with an empty `## features` section.

The life cycle the rules define: an item is *Reported/Requested* → the agent or developer who fixes it marks it
*Fixed/Implemented* (with the version) → the developer tests it and marks it *Verified/Confirmed* → on the next
iteration it is removed (with its screenshots) and summarised in `CHANGELIST.md` under the version. Only the
developer marks items verified.

## 5. Release habits (for every later iteration of the copy)

- Every delivered iteration bumps `VERSION` (patch or minor) and is built for both platforms; the staged files
  carry the version (`release/Windows/Lanternleaf-<version>.exe`, `release/Android/Lanternleaf-<version>.apk`) and
  older versions stay next to them.
- After a build, report the release paths. If staging warns that the exe could not be replaced, that version is
  running: never kill the process; the folder refreshes on the next build after it is closed.
- Android changes are checked on an emulator as in spec 11 § 7 (read-only AVD if it holds someone's data).
- Text files are edited as UTF-8 without BOM; never round-trip them through PowerShell 5.1
  `Get-Content`/`Set-Content` (spec 02 § 7, `ai/PROMPT.md` rule 5).
- When the app changes, refresh this `ai/` folder: run `python -I ai/tools/make_bundles.py` (it rewrites
  `ai/files/` and the checksums and warns about files no bundle or spec covers), update the affected specs, the
  expected test output (spec 13 § 1) and the reference renders (`ai/reference/`).

## Checklist

- `README.md`, `PROMPT.md`, `CHANGELIST.md`, `bugs/prompt.md`, `bugs/report.md`, `features/prompt.md`,
  `features/features.md` match their checksums.
- `docs/` holds the four PNGs at the sizes above, rendered by the copy, and the README shows them.
- The README's version line, Credits and licences say MIT (`ai/PROMPT.md` § 7).
