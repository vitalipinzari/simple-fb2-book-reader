# Reference material: sample book and screenshots of the original

`sample-book.fb2` is a small FB2 book written for these prompts (MIT, like the rest of `ai/`): an English and a
Russian chapter with a cover picture (the app icon), body title, section titles, epigraphs, emphasis, strong,
strikethrough, sup/sub, code, a poem with two stanzas, a subtitle `* * *`, an empty line, a web address written as
plain text and an explicit web link, a table, a citation, two footnotes in a notes body, dialogue dashes, «»
quotes, ё, and long words for hyphenation. It has 50 blocks and 5 639 characters; at 1280 × 820 with the default
settings it has 8 pages.

`screenshots/` holds what **the original Lanternleaf 0.7.0** (Windows build, NVIDIA OpenGL 4.1 driver) rendered
for that book in screenshot mode (0.6.0 rendered the same images except the Help panel, whose version line and
format list changed). A correct copy renders the same pictures: the same line breaks, hyphens, page
breaks, positions, colours, panel layouts and texts. Tiny anti-aliasing differences between GPUs are fine;
anything a reader would notice is not.

Each image was made with a fresh, empty settings folder (`--settings-dir <new temp dir>`) and
`--size 1280x820` unless the table says otherwise:

```powershell
& Lanternleaf.exe --settings-dir <tmp> --screenshot <out.png> --size 1280x820 <options> ai\reference\sample-book.fb2
```

| Image | Options | What it shows |
|---|---|---|
| `01-cover-day.png` | *(none)* | first page: the cover picture scaled into the page, Day theme |
| `02-day-chapter-start.png` | `--next 2` | Chapter One: two-line section title, right-aligned epigraph and its author, justified text with first-line indents, max line length 40 em centred in a wide window |
| `03-sepia-two-pages.png` | `--theme sepia --columns 2 --next 1` | open book with spine shading; hyphenation, footnote marker `[1]`, sup/sub, strikethrough, bold, poem title |
| `04-night-amber.png` | `--theme night-amber --next 3` | amber text on black; poem with stanzas and author; `* * *`; the web address stays blue and underlined and the long URL breaks after slashes without hyphens |
| `05-dusk-russian.png` | `--theme dusk --next 5` | Russian chapter start: dialogue dashes, Russian hyphenation, «», ё, footnote `[2]`, citation with author |
| `06-curl.png` | `--page-turn curl --next 2 --turn 0.4` | single-page 3D curl frozen at t = 0.4: the Chapter One page peels off to the left over the next page; lit cylinder, mirrored print showing through the paper back, shadows |
| `07-spread-curl.png` | `--columns 2 --page-turn curl --next 1 --turn 0.5` | two-page spread: the right page flipping over the spine, carrying the next left page on its back |
| `08-toolbar-status-bar.png` | `--panel toolbar --next 2` | pinned toolbar and status bar (chapter, progress bar with chapter marks, `3 / 8`, `1%`); the page laid out between them |
| `09-settings-panel.png` | `--panel settings --next 2` | Settings panel in the top-left half: Text, Colours (with notes), Page turning sections |
| `10-contents-panel.png` | `--panel toc --next 2` | Contents panel, current chapter highlighted |
| `11-help-panel.png` | `--panel help --next 2` | Help panel text |
| `12-find-in-book.png` | `--find "lamp oil" --next 2` | Library → Find in this book: query, "2 matches", Chapter/Text table with snippets |
| `13-find-go-highlight.png` | `--find "lamp oil" --find-go` | jump to the first match: the page starts at the line of the match, which is highlighted; poem, separator, blue underlined web address |
| `14-narrow-window-toolbar.png` | `--size 700x900 --panel toolbar --next 2` | narrow window: the buttons that do not fit are in **Menu**; the status bar's chapter title is ellipsised |
| `15-narrow-window-menu.png` | `--size 700x900 --panel toolbar --next 2 --click 660,26` | the same with **Menu** clicked open: Go to page, Find in this book, One page (✓), Two pages, like a book, Full screen, Help, a separator, About Lanternleaf |

PowerShell note: pass a phrase as one argument with the call operator (`& $exe … --find 'lamp oil'`).
`Start-Process -ArgumentList` joins array items with spaces without quoting, so `lamp oil` would arrive as two
arguments.

`09-settings-panel.png`: the panel ends with the path of the settings folder, below the visible part. A temp
folder path of a very different length wraps differently and changes the length of the scrollbar's thumb;
that alone is not a difference to fix.

The About panel is not among the references because its copyright line differs on purpose in the MIT edition
(see `ai/PROMPT.md` § 7).
