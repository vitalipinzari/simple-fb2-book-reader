# 13 — Tests and verification

Scope: how to prove the copy is exact — the unit test program and its exact expected output, the screenshot
mode and the reference images of the original, interaction checks, the log, manual desktop checks and Android
device checks. Run the relevant part at the end of every phase of `ai/PROMPT.md` § 5.

## 1. Unit tests (`tests/core_tests.cpp`, verbatim in `ai/files/04-tests.md`)

A single program without a framework: `CHECK(cond)` and `CHECK_EQ(a, b)` count checks and print
`FAILED <file>:<line>: <expression>` for each failure; the program prints one line per test group, some indented
diagnostics, and finally `<n> checks, <m> failures`; it returns 1 if anything failed. Its only argument is the
assets folder (default `assets`). CTest runs it as `ll_tests <repo>/assets` (`./build.ps1 -Test`), or run it
directly: `build\vs2026\Release\ll_tests.exe <repo>\assets`.

Groups: unicode, encodings (cp1251, KOI8-R, CP866, UTF-16, cp1252), xml (the tolerant reader), fb2 (structure,
styles, footnotes, cover, broken markup), txt (paragraph heuristics, typography, Gutenberg), pdf (the standard
test vectors of MD5, SHA-256/384/512, RC4 and AES; the lexer; the Flate, LZW, ASCIIHex, ASCII85 and RunLength
filters and PNG predictors; text strings and glyph names; a generated two-page book with its title, author,
paragraphs, joined hyphenated words, list, outline and contents; the same book with broken cross-reference
offsets; metadata from the head and tail of a file; text extraction; a cross-reference stream with an object
stream and an Identity-H font with a ToUnicode map; a picture through the PDF picture container; RC4, AES-128 and
AES-256 encrypted files; a stream that an encrypted file keeps in the clear; the same compressed file with an
indirect /Length on its cross-reference stream, read without a repair; damaged content (a form with an unclosed
artifact and more Q than q, a ToUnicode bfrange onto an array and one that ends at <FFFFFFFF>, a predictor row
longer than its stream); tables of evenly spaced lines (a row per line with values in lower case, and a row whose
cells go on over two lines); garbage that must fail), hyphenation, line
breaking, matching (transliteration, query terms), web addresses (trailing punctuation and brackets, Cyrillic
paths, existing links left alone, styles kept around new links), library search (on a temporary folder tree,
including a zip and a cp1251 file in a Cyrillic folder), and — with `LL_TESTS_WITH_TEXT` — text layout (no
overflow, justified edges, pagination forwards and backwards, page counting, zoom anchoring, unbreakable URLs,
headings taller than a page, headings never ending a page).

**Expected output of the full build** (`LL_BUILD_TEXT=ON`, bundled fonts and patterns), exactly, line for line:

```text
unicode
encodings
xml
fb2
txt
pdf
  pdf: 5 blocks, 2 contents entries, repaired 5 blocks, encrypted files opened 3 of 3
hyphenation
  hyphenation: hy-phen-ation com-puter Ta-ble пе-ре-но-сы про-грам-ми-ро-ва-ние До-сто-ев-ский несчаст-ли-вая
line breaking
matching
web addresses
library search
text layout
  kerning AV: 1.264 vs 1.367
  lines=384 overflow=0 ragged=0 hyphenated=180 (optimal ok=41 fail=21 greedy=6)
  pages=20 back-consistent=19
  subtitle pages=13, ending in a heading=0
  narrow URL: 7 lines, 3 end after a slash, 0 hyphens
840 checks, 0 failures
```

The indented lines are measurements, not checks: the `pdf` line counts the blocks and contents entries of the
generated PDF book, the blocks of its copy with broken cross-reference offsets and the encrypted test files that
opened (spec 15); the others come out of the hyphenator, the shaper (kerning of "AV"),
the line breaker (how many paragraphs the optimal algorithm solved, failed, and how many needed the greedy
fallback), the paginator and the URL breaker, all on the bundled fonts. Identical numbers are the strongest
evidence that hyphenation, shaping, line breaking and pagination behave exactly like the original; any difference
points at the module to fix (specs 05 and 07). With `LL_BUILD_TEXT=OFF` the program stops after
`library search` and prints fewer checks, still with 0 failures.

## 2. Screenshot mode

`Lanternleaf.exe --screenshot <out.png>` renders off-screen at `--size` (default 1280 × 820), waits a few frames
(`--frames`, default 4), writes the PNG and quits. It never writes the settings unless `--allow-save` is given, so
combine it with `--settings-dir <fresh temp dir>` to get first-start defaults. Options (spec 09 is
authoritative): `--goto <percent>`, `--next <pages>`, `--turn <t>` (turns one more page and freezes the animation
at t; curl unless `--page-turn slide|fade`), `--panel toc|settings|help|about|library|goto|browser|folders|storage|toolbar`
(`toolbar` pins the toolbar and status bar), `--search <q>` / `--search-root <dir>` / `--search-content` (Library →
Find books, search started), `--find <phrase>` (Library → Find in this book) with `--find-go` (jump to the first
match instead, highlighted), `--click x,y` (repeatable; each click is a move, a press and a release on successive
frames through the normal event path), and the overrides `--theme`, `--font-size`, `--columns`, `--page-turn`,
`--font`. The log (section 4) records each step.

### 2.1 Compare with the original

`ai/reference/sample-book.fb2` and `ai/reference/screenshots/` hold the original's renders; the table and the exact
command lines are in `ai/reference/README.md`. Render the same 15 images with your build and compare each pair by
looking at both: line breaks and hyphens, page starts, title/epigraph/poem/citation placement, indents, colours,
spine and shadows, the curl geometry, toolbar buttons and their order, what moved into Menu at 700 px, status bar
texts, panel placement, every label in the Settings, Contents, Help and Library panels. Fix every visible
difference. (A pixel diff is a useful extra on the same GPU vendor; anti-aliasing may differ slightly between
drivers.) The images are those of the original 0.7.0; it renders 01–10 and 12–15 exactly like 0.6.0 did.
`09-settings-panel.png` has one trap: the Settings panel ends with the path of the settings folder, below the
visible part, so the length of your temp folder's path changes how that text wraps and with it the length of
the scrollbar's thumb. A difference in the thumb alone is not a fault.

The README screenshots in `docs/` are made the same way (spec 14).

### 2.2 Interaction checks with `--click`

| Command (plus `--settings-dir <tmp> --size 1280x820 … sample-book.fb2`) | Expected |
|---|---|
| `--panel settings --next 2 --click 1000,400` | the click lands on the page beside the panel: the panel **and** the bars close, the page stays Chapter One (no page turn); the log shows `screenshot click 1: move at 1000,400`, `… press at …`, `… release at …` |
| `--next 2 --click 1100,400` | a click in the right part of the page turns to the next page (page 4) |
| `--next 3 --click 150,400` | a click in the left third goes back to page 3 (the log's last line counts 4 turns drawn on the spot) |
| `--panel toolbar --next 2 --click 1240,26` | opens **Menu** under its button; at 1280 px every other button fits, so it holds only *About Lanternleaf* |
| `--size 700x900 --panel toolbar --next 2 --click 660,26` | opens **Menu** with the buttons that did not fit, ending with *About Lanternleaf* (= `ai/reference/screenshots/15-narrow-window-menu.png`) |

## 3. Desktop checks (Windows)

Use test books made in a temp folder: the sample book; a copy zipped as `.fb2.zip`; a Russian TXT saved as cp1251,
KOI8-R, CP866, UTF-16 LE with BOM and UTF-8 (the unit tests' `encodeSingleByte` shows how to produce single-byte
encodings); a hard-wrapped English TXT with `CHAPTER I` headings and Gutenberg start/end markers; an FB2 with a
wrong XML encoding declaration; PDF books: a document exported to PDF from a word processor (with
headings and an outline), a LaTeX PDF (hyphenation, footnotes, two columns if you have one), a PDF with pictures,
and copies that are truncated, renamed to `.txt`, or encrypted without a user password (qpdf `--encrypt`).

- [ ] First start (empty settings folder): Day theme, one page, instant turns, welcome screen; window 1180 × 820.
- [ ] Every test book opens with correct text, contents and title; the TXT encodings are detected; Gutenberg
      boilerplate is gone; chapter headings are in Contents.
- [ ] PDF books open as reflowable text in the book font: no running heads or page numbers, words hyphenated at
      line ends are joined, paragraphs continue across pages, headings and the outline (as Contents) are right,
      pictures appear in reading order, a two-column page is read column by column; zoom and themes work as for
      FB2. A PDF renamed to `.txt` still opens as a PDF; a truncated or encrypted (no user password) copy opens.
- [ ] Keys of spec 01 § 4 / spec 09 all work, including Home/End, Ctrl+G, T, F1, Ctrl+Comma, C / Shift+C,
      Ctrl+1…5, B, F10, F11, Alt+Enter, Esc (closes Menu first, then the panel).
- [ ] Ctrl+wheel, Ctrl+Plus/Minus and Ctrl+0 zoom with reflow: the line being read stays on screen; window
      resizing keeps it too; the window cannot be made smaller than 10 % of the monitor in each direction.
- [ ] Each page-turn style (curl, slide, fade, instant) animates forwards and backwards, in one-page and two-page
      mode; going back shows exactly the pages seen going forward (also across a chapter start).
- [ ] The status bar shows chapter, progress with chapter marks, page `n / N` (after background counting) and
      percent; clicking the chapter opens Contents, clicking/dragging the bar jumps, the page number and the
      percentage can be typed in.
- [ ] Clicking a footnote number shows the note pop-up; a web link opens the browser.
- [ ] Ctrl+F finds the sample book by file name, by title ("Lamplighter"), by author ("Wren"), and by a phrase
      from the text with *content* search on; `Толстой`/`Tolstoy`/`Tolstoj` find `Tolstoy_*.fb2.zip`; an empty
      query lists every book, PDFs with their title and author; a phrase is found inside a PDF with
      content search; results stream in while the search runs.
- [ ] Ctrl+Shift+F finds "lamp oil" (2 matches) and jumps with highlight.
- [ ] Quit and restart: the same book opens at the same place, with the same window, font and theme; a renamed
      copy of the book still resumes (fingerprint).
- [ ] Idle CPU use is 0 % with a book open and nothing happening.
- [ ] About shows `Lanternleaf 0.7.0`, "© 2026 Vitali Pinzari. Released under the MIT License.", the system
      description (`Windows x64`) and the licences section with `THIRD-PARTY-NOTICES.txt`.

## 4. The log

`lanternleaf.log` in the settings folder (also written to the console). The original's lines for a screenshot run
of the sample book, for comparison (the GL version and timings vary by machine):

```text
Lanternleaf 0.7.0, OpenGL 4.1.0 NVIDIA 610.88
opened D:\projects\BookReader\ai\reference\sample-book.fb2: FB2, UTF-8, 50 blocks, 5639 chars, parse 1 ms, first page 0 ms
page count: 8 pages, 2 ms of work
screenshot written: <out.png>
instant page turns: 0 shown from the pages prepared ahead, 2 drawn on the spot
```

For a PDF the format and encoding read `PDF, PDF 1.7` (the version in the file's header), for example
`opened …\book.pdf: PDF, PDF 1.7, 7318 blocks, 1176858 chars, parse 726 ms, first page 1 ms` for a
350-page book. The `page count` line appears only when the status bar shows (pages are counted only then) and
the last line only after at least one page turn. In normal use, leaving the app writes the instant-turn
statistic as the last line; with instant turns most turns should come "from the pages prepared ahead".

## 5. Android device checks

Procedures (emulator flags, permissions without tapping, automation arguments, pinch through the emulator
console, landscape lock, screenshots): spec 11 § 7. On a phone-sized emulator (1080 × 2400) check:

- [ ] Start: immersive full screen, Day theme, the *All files access* prompt; after allowing (or with appops) the
      file browser lists books and Find books searches Download, Documents, Books and Telegram folders.
- [ ] Tap zones: right part → next page, left third → previous page, middle → toolbar and status bar (buttons that
      do not fit are under Menu); any tap on the page outside them hides them; swipes turn pages.
- [ ] Pinch zooms with reflow and keeps the place; A+/A− in the toolbar do the same.
- [ ] A vertical swipe on the left part of the page changes Lanternleaf's own brightness; Settings → Screen has
      the slider and *Use the system brightness*; the value survives a restart.
- [ ] Panels open in the top half (portrait) or left half (landscape) over the dimmed page and do not move when
      their list is dragged; a vertical drag that starts on a slider or check box scrolls instead of changing it;
      a sideways drag moves a slider; lists at their top or bottom pass the drag on to the panel.
- [ ] Back closes the Menu, then the panel; on the page it leaves the app and the position is saved.
- [ ] Landscape (`cmd window user-rotation lock 1`): two pages side by side when each page stays readable; text,
      toolbar and panels stay clear of the camera cutout and system bars but not of the gesture zones.
- [ ] The page-number field of the status bar opens the number pad; search fields get no auto-capitalisation or
      autocorrect.
- [ ] "Open with Lanternleaf" works for FB2, `.fb2.zip`, TXT and PDF from a file manager; the book reopens after a
      restart.
- [ ] About shows `Android (API 34) x64` on the x86_64 emulator and the storage-access state.

## Checklist

- `ll_tests` output equals section 1's block exactly.
- All 15 reference renders match the originals in `ai/reference/screenshots/`.
- The `--click` table of section 2.2 behaves as stated.
- Every box of sections 3 and 5 is ticked.
