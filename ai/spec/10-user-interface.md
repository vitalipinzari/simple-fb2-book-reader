# 10 — User interface: toolbar, status bar, panels, pop-ups and the file browser

Scope: this specification covers `src/app/AppUi.cpp` and `src/app/FileBrowser.cpp`, meaning every `App` member function defined in them and their file-local helpers. Together they draw everything made with Dear ImGui on top of the page: the style derived from the colour theme, the toolbar and its overflow **Menu**, the status bar (chapter, progress bar with chapter marks, page, percentage, and typing a page number or percentage), the panels (Library with its Recent / Find books / Find in this book tabs, Contents, Settings, Go to, Help, About, and the in-app file browser), panel placement, the footnote pop-up, error messages, the toast, Android's storage-access prompt and notices, and the system file and folder dialogs. The page itself, input, navigation, persistence and frame pacing belong to `src/app/App.cpp` (spec 09). They appear here only where the UI depends on them. All declarations (`App` members and nested types, the `ll::ui` helpers, `Settings`, `RecentBook`, `Theme`, `platform::`, `LibrarySearch`, `SearchHit`, `Document`, `BookLayout` …) are in the verbatim headers and are not repeated.

## 1. Conventions and context

### 1.1 The two files

`src/app/AppUi.cpp` begins with the comment line
`// Lanternleaf - Dear ImGui panels (toolbar, library and search, contents, settings, help ...).`
followed by these includes, in this order and grouping:

```cpp
#include <imgui.h>
#include <imgui_stdlib.h>

#include <algorithm>
#include <cfloat>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "app/App.h"
#include "app/UiHelpers.h"
#include "core/BookLoader.h"
#include "core/FileUtil.h"
#include "core/Unicode.h"
#include "platform/Platform.h"
```

Everything is in `namespace ll`. First an anonymous namespace holds the helpers of §2.1. Then come the member functions, in this source order: `anyPanelOpen`, `panelOpen`, `showPanel`, `togglePanel`, `focusIfRequested`, `storageAccess`, `onStorageAccessGranted`, `narrowUi`, `placePanel`, `drawStorageAccessNotice`, `drawStoragePrompt`, `showToast`, `drawToast`, `drawAbout`, `applyImGuiStyle`, `drawUi`, `drawToolbar`, `toolbarBarHeight`, `statusBarTwoRows`, `statusBarBarHeight`, `updateBars`, `drawStatusBar`, `drawLibrary`, `drawLibraryRecent`, `startLibrarySearch`, `drawLibrarySearch`, `drawLibraryFind`, `drawToc`, `drawSettings`, `drawGoto`, `drawHelp`, `drawFootnote`, `drawMessages`, `openFileDialog`, `addFolderDialog`.

`src/app/FileBrowser.cpp` begins with the two comment lines

```cpp
// Lanternleaf - in-app file browser. Android's system pickers hand out content:// URIs that cannot be
// reopened after a restart, so with "All files access" books are opened by their real path instead.
```

followed by

```cpp
#include <imgui.h>

#include <algorithm>
#include <cstdio>
#include <filesystem>

#include "app/App.h"
#include "app/UiHelpers.h"
#include "core/BookLoader.h"
#include "core/FileUtil.h"
#include "core/Unicode.h"
#include "platform/Platform.h"

namespace fs = std::filesystem;
```

and then `namespace ll { … }` containing an anonymous namespace (§2.2) and `openFileBrowser`, `browseTo`, `drawFileBrowser`, in that order.

The code uses the Dear ImGui 1.92+ API: `ImGui::PushFont(nullptr, size)`, `ImGuiStyle::FontSizeBase` / `FontScaleDpi`, `ImGuiCol_TabSelected`, `ImGuiCol_TabSelectedOverline`, `ImGuiCol_NavCursor`. The vcpkg port in use is Dear ImGui 1.93.0. `imgui_stdlib.h` provides the `std::string*` overloads of `InputText` / `InputTextWithHint`.

### 1.2 Units, scale, coordinates

- All positions and sizes are Dear ImGui coordinates. These are SDL window coordinates ("window units"). `vp` always means `ImGui::GetMainViewport()`, which covers the whole window.
- `s` is `displayScale_`: SDL's window display scale (1.0 on a 96-dpi desktop; the screen density on Android, e.g. 2.625). A constant written here as "N·s" is `N.0f * s` in the code. Constants written without "·s" are not scaled.
- `k = fbW_ > 0 ? static_cast<float>(winW_) / static_cast<float>(fbW_) : 1.0f` converts framebuffer pixels to window units. The safe-area insets `safeLeft_`, `safeTop_`, `safeRight_`, `safeBottom_` are kept in framebuffer pixels and are always multiplied by `k` here.
- After `applyImGuiStyle` every size in `ImGui::GetStyle()` is already multiplied by `s` (`ScaleAllSizes`), so values read from the style (frame padding, item spacing, window padding, frame height) need no further scaling.
- Notation. "In the X colour" or `PushStyleColor(ImGuiCol_Text, X colour)` stands for `ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyleColorVec4(ImGuiCol_X))`, popped with `ImGui::PopStyleColor()` right after the item(s) it colours. "Disabled colour" means `ImGuiCol_TextDisabled` and "accent colour" means `ImGuiCol_CheckMark`. Column tables list the `ImGui::TableSetupColumn(label, ImGuiTableColumnFlags_…, weight or width)` calls in declaration order. A column marked "wide only" is declared only when the panel is not narrow. Unqualified calls such as `Separator()` or `SameLine()` are `ImGui::` functions.

### 1.3 Strings

Both source files are pure ASCII. Every non-ASCII character in a literal is written as a UTF-8 hex escape, and this spec quotes such literals the same way:

| Escape in the source | Character |
|---|---|
| `"\xE2\x80\xA6"` | U+2026 HORIZONTAL ELLIPSIS `…` |
| `"\xE2\x80\x94"` | U+2014 EM DASH `—` |
| `"\xE2\x80\x93"` | U+2013 EN DASH `–` |
| `"\xD1\x91"` | U+0451 CYRILLIC SMALL LETTER IO `ё` |
| `"\xD0\xB5"` | U+0435 CYRILLIC SMALL LETTER IE `е` |

All quotation marks inside UI texts are ASCII `"` (U+0022, written `\"` in the literals). Apostrophes are ASCII `'`. The `...` in labels such as `Add folder...`, `Searching...`, `Counting the pages...` is three ASCII full stops, not U+2026. Runs of spaces (U+0020) are given with their count where they matter. Line breaks inside labels and texts are `"\n"` (U+000A). There are no other invisible characters.

Macros used in texts come from the generated `app/Version.h` (template `src/app/Version.h.in`, values from the verbatim CMake files): `kAppVersion` = `LL_VERSION` = `"0.6.0"`, `LL_DEVELOPER` = `"Vitali Pinzari"`, `LL_COPYRIGHT` = `"\xC2\xA9 2026 Vitali Pinzari"` (`© 2026 Vitali Pinzari`).

### 1.4 What App.cpp provides (spec 09), for context only

Each frame `App::iterate` first computes whether the toolbar should show:
`showToolbar_ = toolbarPinned_ || !doc_ || anyPanelOpen() || hover || statusEdit_ != StatusEdit::None || <any Dear ImGui popup open>`.
Here `hover` applies to desktops only. It is true while the pointer is in the window within the top zone `max(56, barsShown_ ? topBarH_ + safeTop_·k : 0)` or, with a book open, within the bottom zone `max(56, barsShown_ ? bottomBarH_ + safeBottom_·k : 0)`. `toolbarPinned_` is toggled by a right click and F10, and set by a centre tap on touch screens. Then `iterate` runs `ImGui::NewFrame(); updateBars(); if (doc_ && !viewValid_) rebuildView(); drawUi(); ImGui::Render();`.

App.cpp functions that the UI calls, with the effects that matter here:

- `openBook(path)` returns `bool`. On success it closes the Library and the file browser (`showLibrary_ = false; browser_.open = false;`). On failure it calls `showError("Could not open \"<file name>\": <error>")`.
- `showError(msg)` appends `msg` to `messages_`, which `drawMessages` shows.
- `setColumns(mode)` shows the toast `Two pages need a wider screen: turn the device sideways or make the text smaller.` when `"2"` is asked for and does not fit.
- `setTheme(id)` stores the theme, calls `refreshTheme()` and `applyImGuiStyle()`, and saves.
- `zoomBy(factor)` multiplies the text size. `setFontSize(px)` clamps to 8..96.
- Also used: `toggleFullscreen`, `setScreenBrightness(level)` (-1 = system), `applyScreenSaver`, `checkAutoNight(true)`, `refreshTheme`, `finishTurn`, `setViewStart`, `goToBlock`, `goToPercent`, `currentPercent`, `viewPercent`, `chapterTitleAt` (the title of the TOC entry containing a block, else the book title), `runFind` (fills `findHits_`, at most 1000, and sets `findTruncated_`), `availableFamilies`, `applyFontFamily`, `updateGeometry`, `scheduleSave`, `requestRedraw`, `wake`, `now`.
- `pollAsync` consumes the dialog results. It opens the first of `pendingOpen_`. It appends each of `pendingFolders_` that is not yet listed to `settings_.searchRoots` and calls `scheduleSave()`. It moves new search hits into `hits_` and sets `hitsSorted_ = false`.
- `followLink` fills `footnoteTitle_`, `footnoteText_`, `footnoteBlock_`, `footnoteX_`/`footnoteY_` (window coordinates of the click) and sets `showFootnote_`.
- Esc and Android Back call `closeTopPanel()`. It cancels, in this order: the status-bar number edit, an open popup, the footnote, the messages, the storage prompt, the browser, About, Help, Go to, Settings, Contents, the Library (only while a book is open), and finally the find highlight. A click or tap outside every panel, menu and note calls `returnToReading()`, which closes all of them.
- `initImGui` sets `io.ConfigWindowsMoveFromTitleBarOnly = true`, adds PT Sans Regular (`fonts/PTSans-Regular.ttf`) at 17.0 px as the default UI font, sets `displayScale_`, then calls `applyImGuiStyle()`. `handleEvent` calls `applyImGuiStyle()` again whenever the display scale changes by more than 0.001.

## 2. File-local helpers

### 2.1 AppUi.cpp (anonymous namespace)

```cpp
ImVec4 v4(const Color& c, float a) { return ImVec4(c.r, c.g, c.b, a); }
```
The `Color`'s own alpha is ignored. Every style colour gets the alpha written next to it.

`std::string humanSize(uint64_t bytes)`: with `std::snprintf` into `char buf[32]`, it writes `"%.1f MB"` of `static_cast<double>(bytes) / (1024.0 * 1024.0)` when `bytes >= 1024ull * 1024ull`, else `"%.0f KB"` of `static_cast<double>(bytes) / 1024.0`. For example, 300 bytes gives `0 KB` and 2 621 440 bytes gives `2.5 MB`.

`std::string matchText(uint8_t m)`: returns `"-"` when `m & kMatchAny`. Otherwise it joins the names of the set bits with `", "`, in this order: `kMatchName` → `file name`, `kMatchTitle` → `title`, `kMatchAuthor` → `author`, `kMatchSeries` → `series`, `kMatchText` → `text`. For example, name + title gives `file name, title`. With no bit set the result is empty.

`std::string dirOf(const std::string& path)`: everything before the last `/` or `\` (`find_last_of("/\\")`), or an empty string when there is none.

`fitText` shortens a text with an ellipsis so that it fits a width in the current font:

```cpp
// `s` shortened with an ellipsis to fit `maxW` (window units, current font).
std::string fitText(const std::string& s, float maxW) {
  if (ImGui::CalcTextSize(s.c_str()).x <= maxW) return s;
  std::string t = s;
  while (!t.empty()) {
    t.resize(utf8PrevPos(t, t.size()));
    const std::string candidate = trimCopy(t) + "\xE2\x80\xA6";
    if (ImGui::CalcTextSize(candidate.c_str()).x <= maxW) return candidate;
  }
  return {};
}
```

`flatButton` is a button that looks like plain text until it is hovered or pressed. It is used on the status bar:

```cpp
bool flatButton(const char* id, const std::string& text, float width) {
  ImGui::PushID(id);
  ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0, 0, 0, 0));
  ImGui::PushStyleVar(ImGuiStyleVar_ButtonTextAlign, ImVec2(0.0f, 0.5f));
  const bool clicked = ImGui::Button(text.empty() ? " " : text.c_str(), ImVec2(width, 0));
  ImGui::PopStyleVar();
  ImGui::PopStyleColor();
  ImGui::PopID();
  return clicked;
}
```
Only the idle colour is transparent; `ButtonHovered` and `ButtonActive` still show. The text is left-aligned and vertically centred, and the height is the frame height.

`helpRow(what, keys)` adds one row to the current two-column table: `TableNextRow()`, `TableSetColumnIndex(0)`, `TextWrapped("%s", what)`, `TableSetColumnIndex(1)`, `TextWrapped("%s", keys)`.

### 2.2 FileBrowser.cpp (anonymous namespace)

`std::string parentOf(const std::string& path)` returns `pathToUtf8(pathFromUtf8(path).parent_path())`. For a root such as `/` or `C:\` it returns the same path. For `""` it returns `""`.

`std::string sizeText(uint64_t bytes)` gives the same output as `humanSize`, but its code divides by `1048576.0` for MB: `"%.1f MB"` when `bytes >= 1024ull * 1024ull`, else `"%.0f KB"` of `bytes / 1024.0`, in a 32-byte buffer.

## 3. Panel bookkeeping

- `anyPanelOpen()` is `showLibrary_ || showToc_ || showSettings_ || showHelp_ || showGoto_ || showAbout_ || browser_.open`. The footnote, the messages, the toast and the storage prompt are not panels.
- `panelOpen(p)` returns the flag that belongs to `p` (`browser_.open` for `Panel::Browser`). `Panel::None` gives `false`.
- `showPanel(p, libraryTab)` opens one panel at a time, because all panels open in the same place and the one asked for replaces any other. It sets all six `show*_` flags and `browser_.open` to `false`, then sets the flag of `p`. For `Panel::Library` with `libraryTab >= 0` it also sets `libraryTab_ = libraryTab`; a negative value keeps the last tab. Then it sets `focusPanel_ = p` and calls `requestRedraw()`. `showPanel(Panel::None)` closes every panel.
- `togglePanel(p)`: if `panelOpen(p)`, it clears only that flag and does nothing else (no redraw request, no focus change). Otherwise it calls `showPanel(p)`.
- `focusIfRequested(p)` is called right before the panel's `ImGui::Begin`. If `focusPanel_ == p` it calls `ImGui::SetNextWindowFocus()` and sets `focusPanel_ = Panel::None`.
- `narrowUi()` returns `ImGui::GetWindowWidth() / std::max(0.5f, displayScale_) < 560.0f`. It is called inside a panel window and is true when the panel is narrower than 560 logical units; lists then drop columns. Call sites: `drawLibrary` (tab labels), `drawLibraryRecent`, `drawLibrarySearch`, `drawLibraryFind` (columns, progress line) and `drawSettings` (theme notes).

## 4. Style: `applyImGuiStyle()`

This builds a fresh style each time and replaces the current one (`ImGui::GetStyle() = st;` at the end). It is called by `initImGui`, by `setTheme` (and so by `checkAutoNight` and theme cycling), by the Brightness slider in Settings, and on display-scale changes.

1. `ImGuiStyle st;` then `ImGui::StyleColorsDark(&st)` if `theme_.dark`, else `ImGui::StyleColorsLight(&st)`. Colours that are not listed below keep these presets. Sizes that are not listed keep Dear ImGui's defaults.
2. Sizes, set before any scaling:

| Field | Value |
|---|---|
| `WindowRounding` | 8 |
| `ChildRounding` | 6 |
| `FrameRounding` | 5 |
| `GrabRounding` | 5 |
| `PopupRounding` | 6 |
| `ScrollbarRounding` | 6 |
| `TabRounding` | 5 |
| `WindowPadding` | (14, 12) |
| `FramePadding` | (8, 5) |
| `ItemSpacing` | (8, 7) |
| `CellPadding` | (6, 4) |
| `WindowBorderSize` | 1 |
| `SeparatorTextBorderSize` | 1 |

3. Colours. `theme_` is the brightness-adjusted current theme (`adjustedTheme`). Let `bg = theme_.background`, `fg = theme_.text`, `ac = theme_.accent`, and
   `panel = theme_.dark ? Color::mix(bg, fg, 0.07f) : Color::mix(bg, Color{0.45f, 0.4f, 0.3f, 1}, 0.06f)`.
   `mix(a, b, t)` here means `v4(Color::mix(a, b, t), 1)`. The assignments, in source order:

| `ImGuiCol_…` | Value |
|---|---|
| `Text` | `v4(fg, 1)` |
| `TextDisabled` | `v4(theme_.secondary, 1)` |
| `WindowBg` | `v4(panel, 1.0f)` |
| `PopupBg` | `v4(panel, 1.0f)` |
| `ChildBg` | `ImVec4(0, 0, 0, 0)` |
| `Border` | mix(panel, fg, 0.2) |
| `FrameBg` | mix(panel, fg, 0.08) |
| `FrameBgHovered` | mix(panel, ac, 0.2) |
| `FrameBgActive` | mix(panel, ac, 0.3) |
| `TitleBg` | mix(panel, fg, 0.06) |
| `TitleBgActive` | mix(panel, ac, 0.18) |
| `TitleBgCollapsed` | `v4(panel, 0.8f)` |
| `Button` | mix(panel, fg, 0.09) |
| `ButtonHovered` | mix(panel, ac, 0.28) |
| `ButtonActive` | mix(panel, ac, 0.42) |
| `Header` | mix(panel, ac, 0.2) |
| `HeaderHovered` | mix(panel, ac, 0.3) |
| `HeaderActive` | mix(panel, ac, 0.4) |
| `CheckMark` | `v4(ac, 1)` |
| `SliderGrab` | `v4(ac, 0.8f)` |
| `SliderGrabActive` | `v4(ac, 1)` |
| `Separator` | mix(panel, fg, 0.18) |
| `Tab` | mix(panel, fg, 0.07) |
| `TabHovered` | mix(panel, ac, 0.3) |
| `TabSelected` | mix(panel, ac, 0.22) |
| `TabSelectedOverline` | `v4(ac, 1)` |
| `TableHeaderBg` | mix(panel, fg, 0.07) |
| `TableRowBgAlt` | `v4(fg, 0.035f)` |
| `TableBorderLight` | mix(panel, fg, 0.12) |
| `PlotHistogram` | `v4(ac, 0.85f)` |
| `ScrollbarBg` | `ImVec4(0, 0, 0, 0)` |
| `ScrollbarGrab` | mix(panel, fg, 0.2) |
| `ScrollbarGrabHovered` | mix(panel, fg, 0.3) |
| `ScrollbarGrabActive` | `v4(ac, 1)` |
| `ResizeGrip` | `v4(ac, 0.2f)` |
| `ResizeGripHovered` | `v4(ac, 0.5f)` |
| `ResizeGripActive` | `v4(ac, 0.8f)` |
| `TextSelectedBg` | `v4(ac, 0.35f)` |
| `NavCursor` | `v4(ac, 1)` |

   As a result, the UI follows the Brightness setting. Light themes dim the paper, which makes the panels darker; dark themes dim the ink, which makes the UI text and accent darker. The accent (`CheckMark`) is also the colour that other code reads for highlighted text: the storage notice, folder names in the browser, and the progress-bar fill.
4. Touch-first overrides (`if (touchFirst_)`, "finger-sized controls"): `FramePadding = (12, 9)`, `ItemSpacing = (12, 10)`, `ItemInnerSpacing = (10, 8)`, `CellPadding = (8, 9)`, `ScrollbarSize = 20`, `GrabMinSize = 24`, `TouchExtraPadding = (4, 4)`.
5. `st.ScaleAllSizes(displayScale_);` scales every size above, including the touch values. Then `st.FontScaleDpi = displayScale_;` and `st.FontSizeBase = touchFirst_ ? 17.5f : 17.0f;`, which are not scaled by `ScaleAllSizes`. The UI font size is therefore 17 × s on desktops and 17.5 × s on touch screens.
6. `ImGui::GetStyle() = st;`

Check values: at brightness 1.00 the Day theme's `WindowBg` is (0.967, 0.964, 0.958). Sepia gives (0.926, 0.894, 0.814), Dusk (0.158, 0.133, 0.105), Night amber (0.070, 0.046, 0.010) and Night red (0.061, 0.009, 0.004). On a desktop at s = 1 the frame height is 17 + 2·5 = 27.

## 5. Frame entry and the bars

### 5.1 `drawUi()`

```cpp
void App::drawUi() {
  toolbarHeight_ = 0;
  if (touchFirst_ && (anyPanelOpen() || storagePromptOpen_)) {
    // Dim the page behind open panels: it shows that a tap there leads back to reading.
    const ImGuiViewport* vp = ImGui::GetMainViewport();
    ImGui::GetBackgroundDrawList()->AddRectFilled(vp->Pos, ImVec2(vp->Pos.x + vp->Size.x, vp->Pos.y + vp->Size.y),
                                                  IM_COL32(0, 0, 0, theme_.dark ? 120 : 80));
  }
  if (showToolbar_) drawToolbar();
  if (barsShown_) drawStatusBar();
  if (browser_.open) drawFileBrowser();
  if (showLibrary_) drawLibrary();
  if (showToc_) drawToc();
  if (showSettings_) drawSettings();
  if (showGoto_) drawGoto();
  if (showHelp_) drawHelp();
  if (showAbout_) drawAbout();
  if (showFootnote_) drawFootnote();
  if (storagePromptOpen_) drawStoragePrompt();
  drawToast();
  drawMessages();
}
```

The dimming is drawn only on touch screens. It covers the whole viewport, over the page but beneath every ImGui window (including the toolbar and the status bar). It is drawn while a panel or the storage prompt is open, but not for the footnote or menus. `toolbarHeight_` is 0 unless the toolbar is drawn in this frame (§6.7). Everything drawn after the toolbar is placed relative to it.

### 5.2 Bar heights

```cpp
float App::toolbarBarHeight() const {
  return ImGui::GetFrameHeight() + 2.0f * ImGui::GetStyle().WindowPadding.y;
}

bool App::statusBarTwoRows() const {
  return ImGui::GetMainViewport()->Size.x / std::max(0.5f, displayScale_) < 640.0f;
}

float App::statusBarBarHeight() const {
  const ImGuiStyle& st = ImGui::GetStyle();
  const float rows = statusBarTwoRows() ? 2.0f : 1.0f;
  return rows * ImGui::GetFrameHeight() + (rows - 1.0f) * st.ItemSpacing.y + 2.0f * std::round(st.WindowPadding.y * 0.5f);
}
```

The toolbar is one row of buttons with the full window padding above and below it. The status bar is one row, or two rows when the viewport is narrower than 640 logical units, with half the window padding (rounded) above and below. On a desktop at s = 1 this gives a toolbar of 27 + 24 = 51, a one-row status bar of 27 + 12 = 39, and a two-row status bar of 54 + 7 + 12 = 73 window units.

### 5.3 `updateBars()`: the bars and the page layout

This is called inside the ImGui frame, before `drawUi()`. The toolbar and the status bar show and hide together. While both show, the page is laid out between them (`updateGeometry` in App.cpp reads `barsShown_`, `topBarH_`, `bottomBarH_`).

```cpp
void App::updateBars() {
  const bool shown = showToolbar_ && doc_ != nullptr;
  const float top = shown ? toolbarBarHeight() : 0.0f;
  const float bottom = shown ? statusBarBarHeight() : 0.0f;
  if (shown == barsShown_ && top == topBarH_ && bottom == bottomBarH_) return;
  barsShown_ = shown;
  topBarH_ = top;
  bottomBarH_ = bottom;
  if (!shown) statusEdit_ = StatusEdit::None;
  if (turning_) finishTurn();
  updateGeometry();  // the page now fits between the bars, or fills the screen again
  requestRedraw();
}
```

Without a book the toolbar can show (`showToolbar_` is always true then), but `barsShown_` stays false: there is no status bar and the page does not move. Hiding the bars cancels a number being typed into the status bar. Any change of the heights also re-lays out the page, for example when the status bar switches between one and two rows or the display scale changes.

## 6. Toolbar: `drawToolbar()`

There is one toolbar for every screen. Each item has its place, and as many as fit are shown. Those that do not fit (the least needed first) move into the **Menu** at the right end, which always also holds About. Phones (upright or sideways) and narrow desktop windows therefore reach everything the same way.

### 6.1 Window

```cpp
  const ImGuiViewport* vp = ImGui::GetMainViewport();
  // Window units per framebuffer pixel, to respect the safe area (notches, rounded corners).
  const float k = fbW_ > 0 ? static_cast<float>(winW_) / static_cast<float>(fbW_) : 1.0f;
  const float insetL = safeLeft_ * k, insetT = safeTop_ * k, insetR = safeRight_ * k;
  ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + insetL, vp->Pos.y + insetT));
  // A fixed height (one row of buttons): the page is laid out below it (updateBars).
  ImGui::SetNextWindowSize(ImVec2(vp->Size.x - insetL - insetR, toolbarBarHeight()));
  ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 0.0f);
  ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
  const ImGuiWindowFlags flags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                 ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing |
                                 ImGuiWindowFlags_NoBringToFrontOnFocus;
  if (ImGui::Begin("##toolbar", nullptr, flags)) {
    … // §6.2 – §6.7
  }
  ImGui::End();
  ImGui::PopStyleVar(2);
```

The toolbar spans the full width inside the left and right safe insets and sits below the top inset. It is square-cornered and borderless, with the `WindowBg` (panel) colour. Panels always stay in front of it.

### 6.2 Measurements

```cpp
    // Shortcut tooltips: a tap leaves the pointer "hovering", so touch screens get none.
    auto tip = [this](const char* t) {
      if (!touchFirst_ && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) ImGui::SetTooltip("%s", t);
    };
    const float s = displayScale_;
    const ImGuiStyle& st = ImGui::GetStyle();
    const float spacing = st.ItemSpacing.x;
    auto buttonW = [&](const char* label) { return ImGui::CalcTextSize(label).x + st.FramePadding.x * 2.0f; };
    const char* fullLabel = !settings_.fullscreen ? "Full screen" : touchFirst_ ? "System bars" : "Window";
    const float themeW = 140.0f * s;
    const float sepW = ImGui::CalcTextSize("|").x + spacing;
```

A button's width is its label's text width plus twice the horizontal frame padding, which is exactly what `ImGui::Button` draws. The full-screen button is labelled `Full screen` while windowed. In full screen it reads `Window` on desktops and `System bars` on touch screens. The theme drop-down is 140·s wide. `sepW` is the width of a `|` character plus one item spacing.

### 6.3 Items, widths and priorities

```cpp
    enum Item { kOpen, kLibrary, kFindBooks, kContents, kGoTo, kFindInBook, kTextSize, kTheme, kPages, kSettings,
                kFullScreen, kHelp, kItemCount };
    struct Slot {
      float w;
      int priority;  // higher stays on the toolbar longer
      bool shown;
    };
    Slot slot[kItemCount] = {
        {buttonW("Open"), 10, true},
        {buttonW("Library"), 8, true},
        {buttonW("Find books"), 7, true},
        {buttonW("Contents"), 8, true},
        {buttonW("Go to"), 3, true},
        {buttonW("Find in book"), 3, true},
        {sepW + buttonW("A-") + spacing + ImGui::CalcTextSize("00").x + spacing + buttonW("A+"), 9, true},
        {themeW, 9, true},
        {buttonW("1 page") + 2.0f * s + buttonW("2 pages"), 6, true},
        {buttonW("Settings"), 8, true},
        {buttonW(fullLabel), 4, true},
        {buttonW("Help"), 5, true},
    };
    const float menuW = buttonW("Menu");
    const float avail = ImGui::GetContentRegionAvail().x - menuW - spacing;
    auto used = [&] {
      float t = 0;
      int n = 0;
      for (const Slot& sl : slot) {
        if (sl.shown) t += sl.w + (n++ > 0 ? spacing : 0.0f);
      }
      return t;
    };
    while (used() > avail) {  // the least needed (of equals, the rightmost) goes to the menu first
      int drop = -1;
      for (int i = 0; i < kItemCount; ++i) {
        if (slot[i].shown && (drop < 0 || slot[i].priority <= slot[drop].priority)) drop = i;
      }
      if (drop < 0) break;
      slot[drop].shown = false;
    }
    for (int p = 10; p >= 0; --p) {  // then put back whatever still fits, the most needed first
      for (int i = 0; i < kItemCount; ++i) {
        if (slot[i].shown || slot[i].priority != p) continue;
        slot[i].shown = true;
        if (used() > avail) slot[i].shown = false;
      }
    }
```

- The room is the content width of the toolbar (window width minus both horizontal paddings), less the Menu button and one item spacing. `used()` adds the widths of the shown items with one item spacing between neighbours.
- The text-size group always counts the separator (`sepW`), even when it is the first item and the separator is not drawn. Its number is estimated with the width of `"00"`.
- Pass 1 removes the shown item with the lowest priority until the rest fits; among equal priorities it removes the rightmost. As the window narrows, items therefore leave the toolbar in this order: **Find in book, Go to, the full-screen button, Help, 1 page / 2 pages, Find books, Settings, Contents, Library, the theme drop-down, the text-size group, Open**.
- Pass 2 walks the priorities from 10 down to 0 and, within a priority, the items from left to right. It puts back every hidden item that still fits. A narrower, less needed item can therefore return into the room left by a wider one (for example Help after 1 page / 2 pages went). Among equal priorities the leftmost returns first (Go to before Find in book).
- This runs every frame, so the toolbar responds immediately to resizing and to a change of the full-screen label. The text size itself does not change the layout, because the slot uses the fixed width of `"00"`.

### 6.4 The shown items

Shown items are drawn in enum order. Every item except the first is preceded by `ImGui::SameLine()`. `first` is true for the first shown item, and `any` becomes true once anything is drawn. `ti = themeIndex(settings_.theme)`.

| Item | Controls drawn | Action | Tooltip (desktop, `tip`) |
|---|---|---|---|
| `kOpen` | `Button("Open")` | `openFileDialog()` | `Open a book (Ctrl+O)` |
| `kLibrary` | `Button("Library")` | If `showLibrary_ && libraryTab_ == 0`: `showLibrary_ = false`. Else `showPanel(Panel::Library, 0)` | `Recently read books (Ctrl+L)` |
| `kFindBooks` | `Button("Find books")` | `showPanel(Panel::Library, 1); focusQuery_ = true;` | `Search your drives by file name, title, author or text (Ctrl+F)` |
| `kContents` | `Button("Contents")`, disabled without a book | `togglePanel(Panel::Toc)` | `Table of contents (T)` |
| `kGoTo` | `Button("Go to")`, disabled without a book | `togglePanel(Panel::Goto)` | `Go to a page or position (Ctrl+G)` |
| `kFindInBook` | `Button("Find in book")`, disabled without a book | `showPanel(Panel::Library, 2); focusQuery_ = true;` | `Search inside this book (Ctrl+Shift+F)` |
| `kTextSize` | Separator (see below), `Button("A-")`, the size, `Button("A+")` | `A-`: `zoomBy(1.0f / 1.08f)`. `A+`: `zoomBy(1.08f)` | `A-`: `Smaller text (Ctrl+Minus, Ctrl+wheel)`. `A+`: `Bigger text (Ctrl+Plus, Ctrl+wheel)` |
| `kTheme` | Drop-down `##theme`, width `themeW` | `setTheme(id)` of the chosen theme | `Colour theme (C)`. Each entry in the open list: the theme's `note` |
| `kPages` | `1 page` and `2 pages` mode buttons | `setColumns("1")` / `setColumns("2")` | `One page at a time (B switches)` / `Two pages side by side, like an open book (B switches)` |
| `kSettings` | `Button("Settings")` | `togglePanel(Panel::Settings)` | `Settings (Ctrl+Comma)` |
| `kFullScreen` | `Button(fullLabel)` | `toggleFullscreen()` | `F11` |
| `kHelp` | `Button("Help")` | `togglePanel(Panel::Help)` | `Shortcuts, colour themes, About (F1)` |

Details:

- `Contents`, `Go to` and `Find in book` are each wrapped in `ImGui::BeginDisabled(!doc_)` … `EndDisabled()`, with the `tip` call inside. A disabled item reports no hover, so it shows no tooltip.
- Text-size group. If the item is not `first`, it starts with `ImGui::TextDisabled("|"); ImGui::SameLine();`. Then a shared lambda `textSize` draws `Button("A-")` + tip, `SameLine()`, `ImGui::Text("%.0f", settings_.fontSize)` (for example `21`), `SameLine()`, `Button("A+")` + tip. The Menu reuses the same lambda (§6.6), without the separator.
- Theme drop-down. `ImGui::SetNextItemWidth(themeW)` and `ImGui::BeginCombo("##theme", themes()[ti].name)`. For each theme `t` in `themes()` order it draws `ImGui::Selectable(themes()[t].name, t == ti)`; when clicked it calls `setTheme(themes()[t].id)`. After each entry, `if (!touchFirst_ && ImGui::IsItemHovered()) ImGui::SetTooltip("%s", themes()[t].note);` (no delay). Then `EndCombo()`. `tip("Colour theme (C)")` follows the combo whether or not it is open.
- Mode buttons. A local lambda `modeButton(label, active)` draws `ImGui::Button(label)`. While `active` it pushes `ImGuiCol_Button` = the style's `ButtonActive` colour, so the current mode looks pressed. `1 page` is active when `columns_ == 1` and `2 pages` when `columns_ == 2`. These are the columns actually shown, so with the `auto` setting either can be lit. Between the two buttons: `ImGui::SameLine(0, 2.0f * s)`.

### 6.5 The book's title

After the items, and only when a book is open and at least one item was drawn:

```cpp
    const float menuX = ImGui::GetWindowWidth() - st.WindowPadding.x - menuW;
    if (doc_ && any) {
      // The book's title before the menu, if it fits after the last button.
      std::string t = doc_->meta.title;
      const std::string a = doc_->meta.authorsJoined();
      if (!a.empty()) t = a + " \xE2\x80\x94 " + t;
      const float x = menuX - spacing - ImGui::CalcTextSize(t.c_str()).x;
      const float buttonsEnd = ImGui::GetItemRectMax().x - ImGui::GetWindowPos().x;
      if (x > buttonsEnd + 30.0f * s) {
        ImGui::SameLine(x);
        ImGui::TextDisabled("%s", t.c_str());
      }
    }
```

The text reads `Author — Title`, with the author first and U+2014 between spaces, or just the title when there is no author. It is right-aligned one item spacing before the Menu button, in the disabled colour. It shows only if a gap of more than 30·s remains after the last drawn item. It is never shortened: it either fits whole or is left out.

### 6.6 The Menu

```cpp
    if (any) ImGui::SameLine(menuX);
    else ImGui::SetCursorPosX(menuX);
    if (ImGui::Button("Menu")) ImGui::OpenPopup("##menu");
    tip("Everything that does not fit on the toolbar, and About");
    // The menu opens below its button, against the right edge.
    ImGui::SetNextWindowPos(ImVec2(ImGui::GetItemRectMax().x, ImGui::GetItemRectMax().y), ImGuiCond_Appearing,
                            ImVec2(1.0f, 0.0f));
    if (ImGui::BeginPopup("##menu")) {
      bool listed = false;
      for (int i = 0; i < kItemCount; ++i) {
        if (slot[i].shown) continue;
        listed = true;
        switch (i) { … }  // table below
      }
      if (listed) ImGui::Separator();
      if (ImGui::MenuItem("About Lanternleaf")) showPanel(Panel::About);
      ImGui::EndPopup();
    }
```

The `Menu` button is always present, right-aligned at `menuX`. The popup's top-right corner is placed at the button's bottom-right corner when the popup appears. It lists the hidden items in toolbar (enum) order:

| Hidden item | Menu entry | Enabled | Checked | Action |
|---|---|---|---|---|
| `kOpen` | `MenuItem("Open a book")` | yes | – | `openFileDialog()` |
| `kLibrary` | `MenuItem("Recent books")` | yes | – | `showPanel(Panel::Library, 0)` |
| `kFindBooks` | `MenuItem("Find books")` | yes | – | `showPanel(Panel::Library, 1); focusQuery_ = true;` |
| `kContents` | `MenuItem("Contents", nullptr, false, doc_ != nullptr)` | with a book | – | `showPanel(Panel::Toc)` |
| `kGoTo` | `MenuItem("Go to page", nullptr, false, doc_ != nullptr)` | with a book | – | `showPanel(Panel::Goto)` |
| `kFindInBook` | `MenuItem("Find in this book", nullptr, false, doc_ != nullptr)` | with a book | – | `showPanel(Panel::Library, 2); focusQuery_ = true;` |
| `kTextSize` | `AlignTextToFramePadding(); TextUnformatted("Text size"); SameLine();` then the `textSize` group (`A-`, number, `A+`, with their tooltips) | – | – | as on the toolbar. These are buttons, so the menu stays open while the size changes. |
| `kTheme` | `BeginMenu("Colour theme")` containing `MenuItem(name, nullptr, t == ti)` for every theme, then `EndMenu()` | – | current theme | `setTheme(themes()[t].id)` |
| `kPages` | `MenuItem("One page", nullptr, columns_ == 1)` then `MenuItem("Two pages, like a book", nullptr, columns_ == 2)` | – | current mode | `setColumns("1")` / `setColumns("2")` |
| `kSettings` | `MenuItem("Settings")` | – | – | `showPanel(Panel::Settings)` |
| `kFullScreen` | `MenuItem(!settings_.fullscreen ? "Full screen" : touchFirst_ ? "Show system bars" : "Leave full screen")` | – | – | `toggleFullscreen()` |
| `kHelp` | `MenuItem("Help")` | – | – | `showPanel(Panel::Help)` |

The Menu always ends with `About Lanternleaf`. A separator precedes it only when at least one item is listed above, so with everything on the toolbar the Menu holds About alone. Menu entries open panels with `showPanel`, which does not toggle, unlike the toolbar's Contents, Go to, Settings and Help buttons, which use `togglePanel`. While the Menu, its theme submenu, or the toolbar's theme drop-down is open, the toolbar stays visible, because App.cpp counts any open popup.

### 6.7 Toolbar height for the rest of the frame

The last statement inside the `if (Begin)` is `toolbarHeight_ = ImGui::GetWindowHeight() + insetT;`. Panels, the toast, and the touch number box are placed below this value.

## 7. Status bar: `drawStatusBar()`

This is drawn only while `barsShown_`, that is, with a book open and the toolbar shown. It shows the chapter, the progress bar, the page(s) on screen out of all pages, and how far into the book the reader is.

### 7.1 Window

```cpp
  const ImGuiViewport* vp = ImGui::GetMainViewport();
  const float k = fbW_ > 0 ? static_cast<float>(winW_) / static_cast<float>(fbW_) : 1.0f;
  const float insetL = safeLeft_ * k, insetR = safeRight_ * k, insetB = safeBottom_ * k;
  const float s = displayScale_;
  const float padY = std::round(ImGui::GetStyle().WindowPadding.y * 0.5f);
  ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + insetL, vp->Pos.y + vp->Size.y - insetB - bottomBarH_));
  ImGui::SetNextWindowSize(ImVec2(vp->Size.x - insetL - insetR, bottomBarH_));
  ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 0.0f);
  ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
  ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(ImGui::GetStyle().WindowPadding.x, padY));
  const ImGuiWindowFlags flags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                 ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing |
                                 ImGuiWindowFlags_NoBringToFrontOnFocus | ImGuiWindowFlags_NoScrollWithMouse;
  const bool visible = ImGui::Begin("##status", nullptr, flags);
  ImGui::PopStyleVar(3);
  if (!visible || !doc_ || !viewValid_ || doc_->blocks.empty()) {
    ImGui::End();
    return;
  }
  const ImGuiStyle& st = ImGui::GetStyle();
  const ImGuiIO& io = ImGui::GetIO();
```

The status bar sits on the bottom safe inset and spans the full width inside the side insets. Its height is `bottomBarH_` (§5.2), and its vertical padding is half the window padding. The three style variables are popped right after `Begin`, so the contents use the normal style. Without a valid view the empty bar still shows.

### 7.2 Texts

```cpp
  const bool counted = layout_->countDone() && layout_->pageCount() > 0;
  const int total = counted ? layout_->pageCount() : 0;
  const int page = counted ? layout_->pageIndexOf(view_.pages[0].start) + 1 : 0;
  const int lastPage = counted && view_.count == 2 && !view_.pages[1].empty() ? std::min(page + 1, total) : page;
  const double progress = viewPercent(view_);
  char pageText[64], pctText[16];
  if (!counted) std::snprintf(pageText, sizeof(pageText), "\xE2\x80\xA6 / \xE2\x80\xA6");  // still counting
  else if (lastPage != page) std::snprintf(pageText, sizeof(pageText), "%d\xE2\x80\x93%d / %d", page, lastPage, total);
  else std::snprintf(pageText, sizeof(pageText), "%d / %d", page, total);
  // Rounded to the nearest percent (a page reached by typing 40 starts just before 40 % of the text); 100 % only at
  // the very end.
  int pct = static_cast<int>(std::lround(progress * 100.0));
  if (pct >= 100 && progress < 1.0) pct = 99;
  std::snprintf(pctText, sizeof(pctText), "%d%%", pct);
```

The page text is `… / …` while the pages are still being counted, `12 / 345` for one page, and `12–13 / 345` (U+2013) for two pages side by side. The percentage is `37%`, with no space. It shows `99%` until the progress actually reaches 1.0. `viewPercent(view_)` is the reading progress at the end of the view.

### 7.3 Widths

```cpp
  const float pad = st.FramePadding.x * 2.0f;
  const float spacing = st.ItemSpacing.x;
  const float avail = ImGui::GetContentRegionAvail().x;
  const float pageW = std::max(ImGui::CalcTextSize(pageText).x, ImGui::CalcTextSize("00000").x) + pad;
  const float pctW = std::max(ImGui::CalcTextSize(pctText).x, ImGui::CalcTextSize("100.0").x) + pad;
  const std::string chapter = chapterTitleAt(view_.pages[0].start.block);
  const bool twoRows = statusBarTwoRows();
  float chapterW = 0, barW = 0;
  if (twoRows) {
    barW = avail;
    chapterW = std::max(0.0f, avail - pageW - pctW - 2.0f * spacing);
  } else {
    chapterW = std::min(ImGui::CalcTextSize(chapter.c_str()).x + pad, avail * 0.3f);
    barW = avail - chapterW - pageW - pctW - 3.0f * spacing;
    const float minBar = 80.0f * s;
    if (barW < minBar) {
      chapterW = std::max(0.0f, chapterW - (minBar - barW));
      barW = avail - chapterW - pageW - pctW - 3.0f * spacing;
    }
  }
```

On one row the chapter takes its text width but at most 30 % of the bar. The page and percentage fields are at least as wide as `00000` and `100.0` plus the frame padding. The progress bar gets the rest, but at least 80·s, which it takes from the chapter. On two rows the progress bar has the whole first row, and the chapter takes whatever the page and percentage fields leave on the second row.

### 7.4 Chapter

```cpp
  auto chapterButton = [&] {
    const std::string label = fitText(chapter.empty() ? doc_->meta.title : chapter, chapterW - pad);
    if (ui::tapped(flatButton("chapter", label, std::max(1.0f, chapterW)), s)) togglePanel(Panel::Toc);
    if (!touchFirst_ && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) ImGui::SetTooltip("Contents (T)");
  };
```

The chapter title (or the book title before the first chapter) is shortened with `…` to fit. A click or tap (not the end of a finger drag) toggles the Contents panel.

### 7.5 Progress bar

A click, a tap or a drag moves the reading position. A drag shows where it leads while it lasts.

```cpp
  auto progressBar = [&] {
    const float h = ImGui::GetFrameHeight();
    const ImVec2 p0 = ImGui::GetCursorScreenPos();
    ImGui::InvisibleButton("##progress", ImVec2(std::max(1.0f, barW), h));
    const bool active = ImGui::IsItemActive();
    const bool hovered = ImGui::IsItemHovered();
    const float knob = std::round(6.0f * s);
    const float x0 = p0.x + knob, x1 = std::max(x0 + 1.0f, p0.x + barW - knob);
    auto fractionAt = [&](float x) { return std::clamp((x - x0) / (x1 - x0), 0.0f, 1.0f); };
    const bool mouseOk = ImGui::IsMousePosValid();
    const float shown = active && mouseOk ? fractionAt(io.MousePos.x) : static_cast<float>(progress);
    ImDrawList* dl = ImGui::GetWindowDrawList();
    const float cy = std::round(p0.y + h * 0.5f);
    const float th = std::max(2.0f, std::round(3.0f * s));
    const ImU32 track = ImGui::GetColorU32(ImGuiCol_TextDisabled, 0.35f);
    const ImU32 fill = ImGui::GetColorU32(ImGuiCol_CheckMark);
    dl->AddRectFilled(ImVec2(x0, cy - th * 0.5f), ImVec2(x1, cy + th * 0.5f), track, th * 0.5f);
    dl->AddRectFilled(ImVec2(x0, cy - th * 0.5f), ImVec2(x0 + (x1 - x0) * shown, cy + th * 0.5f), fill, th * 0.5f);
    // Chapter starts as small ticks (books with a manageable number of chapters).
    if (doc_->totalChars > 0 && doc_->toc.size() <= 150) {
      const ImU32 tick = ImGui::GetColorU32(ImGuiCol_TextDisabled, 0.7f);
      for (const TocEntry& t : doc_->toc) {
        if (t.level > 1 || t.block <= 0 || t.block >= static_cast<int>(doc_->blocks.size())) continue;
        const float f = static_cast<float>(static_cast<double>(doc_->blocks[static_cast<size_t>(t.block)].charStart) /
                                           static_cast<double>(doc_->totalChars));
        const float x = std::round(x0 + (x1 - x0) * f);
        dl->AddLine(ImVec2(x, cy - th * 1.6f), ImVec2(x, cy + th * 1.6f), tick, std::max(1.0f, std::round(s)));
      }
    }
    dl->AddCircleFilled(ImVec2(x0 + (x1 - x0) * shown, cy), (active || hovered) ? knob * 1.35f : knob, fill);
    auto blockAt = [&](float f) {
      const uint64_t target = static_cast<uint64_t>(static_cast<double>(f) * static_cast<double>(doc_->totalChars));
      auto it = std::upper_bound(doc_->blocks.begin(), doc_->blocks.end(), target,
                                 [](uint64_t v, const Block& b) { return v < b.charStart; });
      return std::max(0, static_cast<int>(it - doc_->blocks.begin()) - 1);
    };
    if (active && mouseOk) {
      // Where letting go leads: the position and its chapter, just above the bar (not under the finger).
      ImGui::SetNextWindowPos(ImVec2(x0 + (x1 - x0) * shown, p0.y - 6.0f * s), ImGuiCond_Always, ImVec2(0.5f, 1.0f));
      ImGui::BeginTooltip();
      const std::string where = chapterTitleAt(blockAt(shown));
      ImGui::Text("%.1f %%", shown * 100.0f);
      if (!where.empty()) {
        ImGui::SameLine();
        ImGui::TextDisabled("%s", fitText(where, 360.0f * s).c_str());
      }
      ImGui::EndTooltip();
    }
    if (ImGui::IsItemDeactivated() && mouseOk) goToPercent(fractionAt(io.MousePos.x));
    if (!touchFirst_ && hovered && !active) ImGui::SetTooltip("Click or drag to move through the book");
  };
```

In words: the bar is an invisible button one frame high. Its track is a rounded bar, max(2, round(3·s)) thick, in the disabled-text colour at 35 % alpha. The track is inset by the knob radius round(6·s) at both ends. The part read so far is filled with the accent. Top-level chapter starts (TOC level ≤ 1, block > 0) are drawn as vertical ticks 3.2 × the track thickness tall, max(1, round(s)) wide, in the disabled colour at 70 % alpha. Ticks are drawn only when the TOC has at most 150 entries. A round accent knob marks the position, and it grows ×1.35 while the bar is hovered or held. While held, the fill and the knob follow the pointer, and a tooltip centred above the knob (its bottom 6·s above the bar) shows `42.3 %` (note the space before `%`) followed by the chapter at that point, shortened to 360·s, in the disabled colour. Releasing the button jumps there with `goToPercent`, even for a plain click. On desktops, hovering without pressing shows the tooltip `Click or drag to move through the book` at once, without delay.

### 7.6 Page number and percentage: the edit fields

A click or tap turns either field into a text field for typing a new value. Enter goes there. Esc, Back, or a click elsewhere leaves it. On touch screens the on-screen keyboard covers the bottom of the screen, so the number is typed into a small box near the top, just below the toolbar, while the bar keeps showing the current value.

```cpp
  auto numberField = [&](const char* id, StatusEdit kind, const char* text, float w, bool enabled) {
    if (statusEdit_ == kind) {
      const bool box = touchFirst_;
      if (box) {
        // An on-screen keyboard covers the bottom of the screen: the number is typed into a small box at the top,
        // just below the toolbar, while the bar keeps showing the current value.
        flatButton(id, text, w);
        ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + vp->Size.x * 0.5f, vp->Pos.y + toolbarHeight_ + 8.0f * s),
                                ImGuiCond_Always, ImVec2(0.5f, 0.0f));
        ImGui::Begin("##statusedit", nullptr,
                     ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize |
                         ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoMove);
        ImGui::AlignTextToFramePadding();
        ImGui::TextUnformatted(kind == StatusEdit::Page ? "Go to page" : "Go to");
        ImGui::SameLine();
      }
      ImGui::SetNextItemWidth(box ? std::max(w, ImGui::CalcTextSize("0000000").x + pad) : w);
      if (statusEditFocus_) {
        ImGui::SetKeyboardFocusHere();
        statusEditFocus_ = false;
      }
      const bool enter = ImGui::InputText(id, &statusText_,
                                          ImGuiInputTextFlags_CharsDecimal | ImGuiInputTextFlags_EnterReturnsTrue |
                                              ImGuiInputTextFlags_AutoSelectAll);
      if (enter) {
        statusEdit_ = StatusEdit::None;
        if (kind == StatusEdit::Page && counted) {
          const int n = std::atoi(statusText_.c_str());
          if (n >= 1) {
            if (turning_) finishTurn();
            setViewStart(layout_->pageStart(std::min(n, total) - 1), true);
          }
        } else if (kind == StatusEdit::Percent && !statusText_.empty()) {
          goToPercent(std::clamp(std::atof(statusText_.c_str()), 0.0, 100.0) / 100.0);
        }
      } else if (ImGui::IsItemDeactivated()) {
        statusEdit_ = StatusEdit::None;
      }
      if (box) {
        ImGui::SameLine();
        if (kind == StatusEdit::Page) ImGui::TextDisabled("of %d", total);
        else ImGui::TextDisabled("%%");
        ImGui::End();
      }
      return;
    }
    ImGui::BeginDisabled(!enabled);
    if (ui::tapped(flatButton(id, text, w), s)) {
      statusEdit_ = kind;
      statusEditFocus_ = true;
      // Moving the keyboard focus into the new field takes Dear ImGui a few frames: draw them now, or the first
      // key typed would arrive before the field is ready (the app sleeps when nothing happens).
      requestRedraw(10);
      char buf[32];
      if (kind == StatusEdit::Page) std::snprintf(buf, sizeof(buf), "%d", page);
      else std::snprintf(buf, sizeof(buf), "%.1f", progress * 100.0);
      statusText_ = buf;
    }
    ImGui::EndDisabled();
    if (!touchFirst_ && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal | ImGuiHoveredFlags_AllowWhenDisabled)) {
      ImGui::SetTooltip("%s", kind == StatusEdit::Page ? (enabled ? "Go to a page" : "Counting the pages...")
                                                       : "Go to a percentage of the book");
    }
  };
```

- Starting an edit pre-fills the field with the current page (`%d`) or the percentage with one decimal (`%.1f`, for example `42.3`). Everything is selected (`AutoSelectAll`), so typing replaces it, and the keyboard focus moves into the field. Only decimal characters are accepted (`CharsDecimal`: digits, `.`, `+`, `-`, `*`, `/`).
- On desktops the input field replaces the flat button in place, with the same width. On touch screens a separate auto-sized window `##statusedit` (no decoration, not movable) is centred horizontally with its top 8·s below the toolbar. It holds the label `Go to page` / `Go to`, the input (at least as wide as `0000000` plus padding), and the suffix `of <total>` / `%` in the disabled colour. Meanwhile the status bar keeps the flat button with the current text.
- Enter on the page field, with the pages counted and n ≥ 1, jumps to page min(n, total). A turn in progress is finished first. Enter on the percentage field with some text jumps to clamp(value, 0, 100) %. Either way the edit ends. Any other deactivation (focus lost, a click elsewhere, Esc inside the field) ends it without moving. App.cpp also ends it on Esc or Back (`closeTopPanel`) and whenever the bars hide (`updateBars`).
- The page field is disabled until the pages are counted (`enabled` = `counted`). Its desktop tooltip is then `Counting the pages...`; `AllowWhenDisabled` makes it show while disabled.

### 7.7 Order

```cpp
  if (twoRows) {
    progressBar();
    chapterButton();
  } else {
    chapterButton();
    ImGui::SameLine();
    progressBar();
  }
  ImGui::SameLine();
  numberField("##page", StatusEdit::Page, pageText, pageW, counted);
  ImGui::SameLine();
  numberField("##percent", StatusEdit::Percent, pctText, pctW, true);
  ImGui::End();
```

On one row: chapter, progress bar, page, percentage. On two rows: the progress bar alone on the first row, then chapter, page and percentage on the second.

## 8. Panel placement: `placePanel()`

Every panel opens in the top-left corner of the reading area and covers half of it: the left half on a wide screen, the top half on a tall one. The reading area is the space below the toolbar and above the status bar, inside the safe area (notches, rounded corners). The function returns the extra window flags for the panel's `Begin`.

```cpp
int App::placePanel() {
  // The reading area: below the toolbar, above the status bar, inside the safe area (notches, rounded corners).
  const ImGuiViewport* vp = ImGui::GetMainViewport();
  const float k = fbW_ > 0 ? static_cast<float>(winW_) / static_cast<float>(fbW_) : 1.0f;
  const float left = safeLeft_ * k, right = safeRight_ * k;
  const float top = std::max(toolbarHeight_, safeTop_ * k);
  const float bottom = safeBottom_ * k + (barsShown_ ? bottomBarH_ : 0.0f);
  const float areaW = std::max(1.0f, vp->Size.x - left - right);
  const float areaH = std::max(1.0f, vp->Size.y - top - bottom);
  // Its top left corner, and half of it: the left half when it is wide, the top half when it is tall.
  const ImVec2 size = areaW >= areaH ? ImVec2(std::floor(areaW * 0.5f), areaH) : ImVec2(areaW, std::floor(areaH * 0.5f));
  // Each time a panel opens it starts there. On a desktop it can then be moved (by its title bar) and resized;
  // on touch screens it stays put, so a finger that scrolls it never drags the window too.
  const ImGuiCond cond = touchFirst_ ? ImGuiCond_Always : ImGuiCond_Appearing;
  ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + left, vp->Pos.y + top), cond);
  ImGui::SetNextWindowSize(size, cond);
  int flags = ImGuiWindowFlags_NoCollapse;
  if (touchFirst_) flags |= ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoResize;
  return flags;
}
```

Users of `placePanel`: Library, Contents, Settings, Go to, Help, About and the file browser. Each calls it first, then `focusIfRequested`, then `Begin`. A square area counts as wide. On desktops the position and size apply each time the panel appears, after which the user can move and resize it. On touch screens they are forced every frame, and the panel cannot be moved or resized. All panels have a title bar with a close button (`&flag`), cannot be collapsed, and have saved settings (they do not pass `NoSavedSettings`). The footnote, the messages, the toast, the storage prompt and the touch number box are placed separately.

## 9. Library panel

### 9.1 `drawLibrary()`: window and tabs

```cpp
void App::drawLibrary() {
  const int panelFlags = placePanel();
  bool open = true;
  focusIfRequested(Panel::Library);
  if (!ImGui::Begin("Library", &open, panelFlags)) {
    ImGui::End();
    if (!open) showLibrary_ = false;
    return;
  }
  // In a short panel the controls and the list do not fit together: the panel scrolls (with a finger on the
  // controls; a list at its end passes the movement on).
  ui::touchScroll(displayScale_, false);
  const int req = libraryTab_ != appliedLibraryTab_ ? libraryTab_ : -1;
  auto tabFlags = [&](int i) { return req == i ? ImGuiTabItemFlags_SetSelected : ImGuiTabItemFlags_None; };
  const bool narrow = narrowUi();
  if (ImGui::BeginTabBar("##libtabs")) {
    if (ImGui::BeginTabItem(narrow ? "Recent" : "Recent books", nullptr, tabFlags(0))) {
      if (req < 0) libraryTab_ = 0;
      drawLibraryRecent();
      ImGui::EndTabItem();
    }
    if (ImGui::BeginTabItem(narrow ? "Find books" : "Find books on disk", nullptr, tabFlags(1))) {
      if (req < 0) libraryTab_ = 1;
      drawLibrarySearch();
      ImGui::EndTabItem();
    }
    if (ImGui::BeginTabItem(narrow ? "In this book" : "Find in this book", nullptr, tabFlags(2))) {
      if (req < 0) libraryTab_ = 2;
      drawLibraryFind();
      ImGui::EndTabItem();
    }
    ImGui::EndTabBar();
  }
  appliedLibraryTab_ = libraryTab_;
  ImGui::End();
  if (!open) showLibrary_ = false;
}
```

| `libraryTab_` | Tab label (wide panel) | Tab label (narrow panel, §3) | Content |
|---|---|---|---|
| 0 | `Recent books` | `Recent` | `drawLibraryRecent()` (§9.2) |
| 1 | `Find books on disk` | `Find books` | `drawLibrarySearch()` (§9.3) |
| 2 | `Find in this book` | `In this book` | `drawLibraryFind()` (§9.5) |

The window title is `Library`, and its close button writes into the local `open`. `libraryTab_` is both the tab that was asked for (by `showPanel`, by start-up, or by the toolbar) and the tab the user is on. `appliedLibraryTab_` remembers its value at the end of the previous draw. When the two differ, the asked-for tab is selected with `ImGuiTabItemFlags_SetSelected`, and in that frame the open tab does not write `libraryTab_` (`req >= 0`). Dear ImGui applies a `SetSelected` request from the next frame on, so for that one frame the previously visible tab is still drawn. If that tab is Find books or Find in this book (with a book open), its query field consumes a pending `focusQuery_` (§9.3 step 1, §9.5 step 2), not the requested tab's field. Otherwise whichever tab is open writes its index, so a tab clicked by the user is remembered. The panel scrolls with a finger as a whole (`children = false`); the lists inside pass on movement at their ends (`ui::touchScroll`).

### 9.2 Recent tab: `drawLibraryRecent()`

1. If `settings_.recent` is empty: `ImGui::Spacing()` and `ImGui::TextWrapped("%s", …)`, then return. The text on touch screens is
   `"No books yet. Open one from the menu, or use \"Find books\"."`
   and otherwise
   `"No books yet. Open one with Ctrl+O, drop a file here, or use \"Find books on disk\"."`
2. Existence cache: `if (now() - existsCacheTime_ > 3.0) { existsCache_.clear(); existsCacheTime_ = now(); }`. A row looks up `existsCache_[rb.path]` and fills it with `fileExists(rb.path)` on a miss. Each listed file is therefore checked at most once per 3 s, and only while its row is drawn.
3. Table `##recent` with `narrow ? 2 : 4` columns, flags `ImGuiTableFlags_RowBg | ImGuiTableFlags_ScrollY | ImGuiTableFlags_Resizable | ImGuiTableFlags_BordersInnerV | ImGuiTableFlags_SizingStretchProp`, and size `ImVec2(0, ui::listHeight())`. Inside, first `ui::touchScroll(s)`, then `TableSetupScrollFreeze(0, 1)` (the header row stays), then the columns:

| Column | Shown | Flags | Weight / width |
|---|---|---|---|
| `Title` | always | `WidthStretch` | 0.42 |
| `Author` | wide panel only | `WidthStretch` | 0.22 |
| `Read` | always | `WidthFixed` | 56·s |
| `Folder` | wide panel only | `WidthStretch` | 0.36 |

   Then `TableHeadersRow()` and an `ImGuiListClipper` over `settings_.recent` (most recent first, as stored).
4. Each row `i` (inside `PushID(i)` … `PopID()`), with `rb = settings_.recent[i]`:
   - Column 0. The label is `rb.title`, or `fileNameOf(rb.path)` when the title is empty. On a narrow panel with authors, `"\n" + rb.authors` is appended, making a two-line row. For a missing file, `"  (missing)"` is appended (two spaces before the parenthesis). The label is drawn as `ImGui::Selectable(label, rb.path == bookPath_, ImGuiSelectableFlags_SpanAllColumns)` inside `BeginDisabled(!exists)` … `EndDisabled()`, so the open book is highlighted and a missing book is greyed out. When `ui::tapped(…, s)` is true, the row's path is remembered as `toOpen`.
   - Context menu on that row: `BeginPopupContextItem("##ctx")` with `MenuItem("Open", nullptr, false, exists)` → `toOpen`; then, only if `platform::canRevealFiles()`, `MenuItem("Show in folder", nullptr, false, exists)` → `platform::revealInFileManager(rb.path)`; then `MenuItem("Remove from the list")` → `toRemove`.
   - Tooltip: `if (!ui::touchInput() && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayNormal)) ImGui::SetTooltip("%s", rb.path.c_str());`, showing the full path.
   - A missing book's row is submitted disabled, and Dear ImGui reports no hover for a disabled item, so neither its context menu nor its tooltip opens.
   - Wide panel: column 1 is `TextUnformatted(rb.authors)`. Next column (`Read`): `ImGui::Text("%d%%", static_cast<int>(rb.percent * 100.0 + 0.5))`, for example `37%`. Wide panel: last column is `TextDisabled("%s", dirOf(rb.path))`.
5. After the table, removal first: `settings_.removeRecent(toRemove); scheduleSave();`. Then opening: `openBook(toOpen)`, even for the book that is already open (it is loaded again). A successful open closes the Library; a failed one adds an error message and leaves the Library open.

### 9.3 Find books tab: `drawLibrarySearch()`

`s = displayScale_`, `running = search_->running()`. In order:

1. Query line. `ImGui::SetNextItemWidth(-110.0f * s)`. If `focusQuery_`: `ImGui::SetKeyboardFocusHere(); focusQuery_ = false;`. Then
   `const bool enter = ImGui::InputTextWithHint("##query", "Title, author, file name or a phrase from the text (empty: list every book)", &query_, ImGuiInputTextFlags_EnterReturnsTrue);`
   followed by `SameLine()`. While a search runs: `Button("Stop", ImVec2(-FLT_MIN, 0))` → `search_->cancel()`. Otherwise: `if (ImGui::Button("Search", ImVec2(-FLT_MIN, 0)) || enter) startLibrarySearch();`. The button fills the rest of the line, and Enter while running does nothing.
2. Check boxes that flow onto new lines on narrow panels. Before each box after the first, `SameLine()` then `flow(label)`:
   ```cpp
   auto flow = [&](const char* label) {
     const float need = ImGui::GetFrameHeight() + ImGui::GetStyle().ItemInnerSpacing.x + ImGui::CalcTextSize(label).x;
     if (ImGui::GetContentRegionAvail().x < need + ImGui::GetStyle().ItemSpacing.x) ImGui::NewLine();
   };
   ```
   The boxes, in order:

| Check box | Bound to | Tooltip (when `!ui::touchInput()` and hovered, no delay) |
|---|---|---|
| `File names` | `settings_.searchByName` | – |
| `Title, author, series` | `settings_.searchByMeta` | – |
| `Text inside books (slow)` | `settings_.searchByContent` | `"Reads every book and looks for the whole phrase, ignoring case and \xD1\x91/\xD0\xB5."` (… `ё/е.`) |
| `Skip system folders` | `settings_.skipSystemDirs` | – |
| `Skip non-book .txt` | `settings_.ignoreTinyTxt` | `Ignores .txt files under 16 KB and licence/readme/changelog files.` |

   The first box has no `flow` call. Changing a box does not save by itself; the values are saved by the next save, for example when a search starts.
3. `if (!storageAccess()) drawStorageAccessNotice();` (§17.3). This happens only on Android without file access.
4. Folders. `ImGui::TreeNodeEx("##where", ImGuiTreeNodeFlags_None, "Where to look (%d)", static_cast<int>(settings_.searchRoots.size()))`, closed by default. When open:
   - For each root `i`, inside `PushID(i)`: `SmallButton("Remove")`, `SameLine()`, `TextUnformatted(root)`. A pressed Remove erases that root after the loop and calls `scheduleSave()`.
   - `Button("Add folder...")` → `addFolderDialog()`. Then `SameLine()`.
   - The label is `touchFirst_ ? "Whole device" : "Add all drives"`. If `GetContentRegionAvail().x < CalcTextSize(label).x + 40.0f * s`, call `NewLine()`. The button appends every `platform::driveRoots()` entry that is not yet listed, then `scheduleSave()`. Then `SameLine()`.
   - The label is `touchFirst_ ? "Usual book folders" : "Downloads, Documents, Desktop"`, with the same `NewLine` rule. The button sets `settings_.searchRoots = platform::defaultSearchRoots()`, replacing the list, then `scheduleSave()`.
   - `TreePop()`.
5. Status line. `p = search_->progress()`, `narrow = narrowUi()`.
   - Once a search has been started in this session (`searchStarted_`):
     - While running: `ImGui::Text("Searching... %llu folders, %llu files, %llu books, %d found", p.dirs, p.files, p.books, hits_.size())`, with casts to `unsigned long long` and `int`. On a wide panel this is followed by the folder being scanned. `maxW = GetContentRegionAvail().x * 0.55f`. `dir = p.currentDir`, and while `dir` is wider than `maxW` its first code point is removed (`dir.erase(0, utf8NextPos(dir, 0))`, so the end of the path stays). Then `SameLine()` and `TextDisabled("%s", dir)`.
     - Finished: `ImGui::TextWrapped("%s in %.1f s: %llu files in %llu folders, %llu books checked, %d found.", p.cancelled ? "Stopped" : "Done", p.seconds, p.files, p.dirs, p.books, hits_.size())`.
   - Before any search: in the disabled colour (`PushStyleColor(ImGuiCol_Text, TextDisabled colour)`), `ImGui::TextWrapped("Tip: leave the query empty to list every FB2/TXT book in the chosen folders.")`.
6. Results table, named `narrow ? "##hitsN" : "##hits"`, so the narrow and wide tables keep separate column and sort states. It has `narrow ? 2 : 5` columns, flags `RowBg | ScrollY | Resizable | BordersInnerV | Sortable | SizingStretchProp` (all `ImGuiTableFlags_`), and size `ImVec2(0, ui::listHeight())`. Inside: `ui::touchScroll(s)`, `TableSetupScrollFreeze(0, 1)`, then the columns:

| Column | Shown | Flags | Weight / width | Sort key (comparator `col`) |
|---|---|---|---|---|
| `Title` | always | `WidthStretch` + `DefaultSort` | 0.36 | 0: `toLowerUtf8(title)` |
| `Author` | wide only | `WidthStretch` | 0.2 | 1: `toLowerUtf8(authors)` |
| `Found in` | always | narrow: `WidthFixed`; wide: `WidthStretch` | narrow: 90·s; wide: 0.1 | 2: `matched` (the bit mask as a number) |
| `Size` | wide only | `WidthFixed` | 70·s | 3: `size` |
| `Folder` | wide only | `WidthStretch` | 0.34 | 4: `toLowerUtf8(path)` (the whole path) |

   Then `TableHeadersRow()`, followed by sorting:
   ```cpp
   if (ImGuiTableSortSpecs* ss = ImGui::TableGetSortSpecs()) {
     if (ss->SpecsDirty || !hitsSorted_) {
       if (ss->SpecsCount > 0) {
         const ImGuiTableColumnSortSpecs& sp = ss->Specs[0];
         const bool asc = sp.SortDirection == ImGuiSortDirection_Ascending;
         // Narrow table: column 1 is "Found in" (column 2 of the wide one).
         const int col = narrow && sp.ColumnIndex == 1 ? 2 : sp.ColumnIndex;
         std::stable_sort(hits_.begin(), hits_.end(), [&](const SearchHit& a, const SearchHit& b) {
           int c = 0;
           switch (col) {
             case 1: c = toLowerUtf8(a.authors).compare(toLowerUtf8(b.authors)); break;
             case 2: c = static_cast<int>(a.matched) - static_cast<int>(b.matched); break;
             case 3: c = a.size < b.size ? -1 : (a.size > b.size ? 1 : 0); break;
             case 4: c = toLowerUtf8(a.path).compare(toLowerUtf8(b.path)); break;
             default: c = toLowerUtf8(a.title).compare(toLowerUtf8(b.title)); break;
           }
           return asc ? c < 0 : c > 0;
         });
       }
       ss->SpecsDirty = false;
       hitsSorted_ = true;
     }
   }
   ```
   Hits are sorted by title, ascending, from the start (`DefaultSort`). They are sorted again whenever the user clicks a header, and whenever new hits arrive (`pollAsync` clears `hitsSorted_`).
7. Rows, through an `ImGuiListClipper` over `hits_`. Each row `i` sits inside `PushID(i)` … `PopID()`, with `h = hits_[i]`:
   - Column 0: label `h.title`, plus `"\n" + h.authors` on a narrow panel when there are authors. `if (ui::tapped(ImGui::Selectable(label, h.path == bookPath_, ImGuiSelectableFlags_SpanAllColumns), s)) { toOpen = h.path; openedByText = (h.matched & kMatchText) != 0; }`.
   - Tooltip, when `!ui::touchInput() && ImGui::IsItemHovered(ImGuiHoveredFlags_DelayShort)`: `BeginTooltip()`, `TextUnformatted(h.path)`. Then, if a series is set, `TextDisabled("Series: %s", h.series)`. If a format is set, `TextDisabled("%s, %s", h.format, humanSize(h.size))`, for example `FB2, 1.2 MB`. If there is a snippet: `Separator()`, `PushTextWrapPos(ImGui::GetFontSize() * 34.0f)`, `TextUnformatted(h.snippet)`, `PopTextWrapPos()`. Then `EndTooltip()`.
   - Context menu `BeginPopupContextItem("##ctx")`: `MenuItem("Open")` sets `toOpen = h.path` but leaves `openedByText` false. If `platform::canRevealFiles()`, `MenuItem("Show in folder")` → `platform::revealInFileManager(h.path)`.
   - Narrow panel: column 1 is `TextUnformatted(matchText(h.matched))`. Wide panel: column 1 `TextUnformatted(h.authors)`, column 2 `TextUnformatted(matchText(h.matched))`, column 3 `TextUnformatted(humanSize(h.size))`, column 4 `TextDisabled("%s", dirOf(h.path))`.
8. After the table, if `toOpen` is set:
   ```cpp
   const std::string phrase = query_;
   if ((toOpen == bookPath_ || openBook(toOpen)) && openedByText) {
     // Found by a phrase from the text: show that place, highlighted.
     findQuery_ = phrase;
     runFind();
     if (!findHits_.empty()) {
       const FindHit& f = findHits_.front();
       highlight_.block = f.block;
       highlight_.start = f.offset;
       highlight_.end = f.offset + f.length;
       goToBlock(f.block, f.offset);
     }
     showLibrary_ = false;
   }
   ```
   Choosing another book opens it, and a successful `openBook` closes the panel. Choosing the book that is already open does nothing, unless it was found by its text. For a book found by its text, the query becomes the find-in-book phrase, the first occurrence is highlighted and shown, and the panel closes.

### 9.4 `startLibrarySearch()`

```cpp
void App::startLibrarySearch() {
  if (!settings_.searchByName && !settings_.searchByMeta && !settings_.searchByContent) settings_.searchByName = true;
  // Without file access Android shows folders but hides the books in them: search again once access is granted.
  searchNeedsAccess_ = touchFirst_ && !storageAccess();
  SearchOptions o;
  o.query = query_;
  o.roots = settings_.searchRoots;
  o.byFileName = settings_.searchByName;
  o.byMeta = settings_.searchByMeta;
  o.byContent = settings_.searchByContent;
  o.skipSystemDirs = settings_.skipSystemDirs;
  o.minTxtBytes = settings_.ignoreTinyTxt ? 16 * 1024 : 1;
  o.skipNonBookTxt = settings_.ignoreTinyTxt;
  o.skipContent = [](const std::string& p) { return platform::isCloudPlaceholder(p); };
  hits_.clear();
  hitsSorted_ = false;
  searchStarted_ = true;
  settings_.lastQuery = query_;
  search_->start(std::move(o));
  scheduleSave();
  requestRedraw();
}
```

With all three "search by" boxes off, `File names` is switched on, and the box shows that. The search runs on the background thread (`LibrarySearch`), and results stream into `hits_` through `pollAsync`. It is also called by `onStorageAccessGranted` (§17.2) and by App.cpp's screenshot mode.

### 9.5 Find in this book tab: `drawLibraryFind()`

1. Without a book: `ImGui::TextDisabled("Open a book first.")`, then return.
2. `ImGui::SetNextItemWidth(-110.0f * s)`, then `focusQuery_` handling as in §9.3. Then `const bool enter = ImGui::InputTextWithHint("##find", "Word or phrase", &findQuery_, ImGuiInputTextFlags_EnterReturnsTrue);`, `SameLine()`, `if (ImGui::Button("Find", ImVec2(-FLT_MIN, 0)) || enter) runFind();`.
3. If `findQuery_` is not empty: `ImGui::TextDisabled("%d matches%s", static_cast<int>(findHits_.size()), findTruncated_ ? " (showing the first 1000)" : "")`, for example `3 matches`, `1 matches`, or `1000 matches (showing the first 1000)`. The count belongs to the last `runFind`, while the text field may already hold a new query.
4. Table `narrow ? "##findhitsN" : "##findhits"` with `narrow ? 1 : 2` columns, flags `RowBg | ScrollY | Resizable | BordersInnerV | SizingStretchProp`, and size `ImVec2(0, ui::listHeight())`. Inside: `ui::touchScroll(s)` and `TableSetupScrollFreeze(0, 1)`. Columns: on a wide panel only, `Chapter` (`WidthStretch`, 0.28); then `Text` (`WidthStretch`, 0.72). Then `TableHeadersRow()` and an `ImGuiListClipper` over `findHits_`.
5. Each row `i` (inside `PushID(i)`), in column 0. `current = highlight_.block == h.block && highlight_.start == h.offset` selects the row of the highlighted match.
   - Narrow panel: a tall selectable with the text drawn over it.
     ```cpp
     ImGui::PushTextWrapPos(0);
     if (ui::tapped(ImGui::Selectable(("##hit" + std::to_string(i)).c_str(), current,
                                      ImGuiSelectableFlags_AllowOverlap,
                                      ImVec2(0, ImGui::GetTextLineHeightWithSpacing() * 3.2f)),
                    s))
       go = i;
     ImGui::SetCursorPosY(ImGui::GetCursorPosY() - ImGui::GetTextLineHeightWithSpacing() * 3.2f -
                          ImGui::GetStyle().ItemSpacing.y);
     ImGui::TextDisabled("%s", h.chapter.empty() ? "-" : h.chapter.c_str());
     ImGui::TextWrapped("%s", h.snippet.c_str());
     ImGui::PopTextWrapPos();
     ```
   - Wide panel: `if (ui::tapped(ImGui::Selectable(h.chapter.empty() ? "-" : h.chapter.c_str(), current, ImGuiSelectableFlags_SpanAllColumns), s)) go = i;` then column 1 `TextUnformatted(h.snippet)`.
6. After `EndTable()` (still inside the `if (BeginTable)`), if a row was chosen: `highlight_ = {h.block, h.offset, h.offset + h.length}` and `goToBlock(h.block, h.offset)`. The panel stays open, and the page behind it moves to the match.

## 10. Contents panel: `drawToc()`

1. `placePanel()`, `focusIfRequested(Panel::Toc)`, `ImGui::Begin("Contents", &showToc_, panelFlags)`. If that returns false, `End()` and return.
2. Without a book or without TOC entries: `ImGui::TextDisabled("This book has no table of contents.")`, `End()`, return. (The `T` key can open the panel without a book.)
3. `ui::touchScroll(s)`. `appearing = ImGui::IsWindowAppearing()`. `cur = doc_->tocIndexForBlock(viewStart_.block)` is the entry containing the first line on screen.
4. For each entry `i` (inside `PushID(i)`): `indent = max(0, level - 1) × 16·s`. If `indent > 0`, `Indent(indent)`. `if (ui::tapped(ImGui::Selectable(t.title.c_str(), i == cur), s)) go = i;`. When the window is appearing and this is the current entry, `ImGui::SetScrollHereY(0.4f)`. Then `Unindent(indent)`.
5. `End()`. Then, if an entry was chosen, `goToBlock(doc_->toc[go].block, 0)`. The panel stays open.

All entries are listed as full-width selectables (no tree, no clipper). The current chapter is highlighted and, on opening, scrolled to 40 % of the panel's height.

## 11. Settings panel: `drawSettings()`

`placePanel()`, `focusIfRequested(Panel::Settings)`, `ImGui::Begin("Settings", &showSettings_, panelFlags)` (if false: `End()`, return), then `ui::touchScroll(s)`. A local `bool relayout = false`. Labels sit to the right of the controls. They get room, but sliders stay usable on phones:
`const float avail = ImGui::GetContentRegionAvail().x; ImGui::PushItemWidth(std::max(avail * 0.55f, avail - 200.0f * s));`
The item width is popped (`PopItemWidth()`) just before `End()`. "Relayout" in the tables means `relayout = true`. After `End()`, if `relayout`: `if (turning_) finishTurn(); updateGeometry(); scheduleSave(); requestRedraw();`. Every `ui::slider` gets `scale = s`.

### 11.1 `SeparatorText("Text")`

| Control | Label | Range / items | Format | Value | On change |
|---|---|---|---|---|---|
| `BeginCombo` / `Selectable` | `Typeface` | `availableFamilies()`. Preview `settings_.fontFamily`. The current family is selected. | – | – | Choosing a different family: `if (!applyFontFamily(f)) showError("Could not load the typeface " + f);` then `scheduleSave()`. Choosing the current family does nothing. |
| `ui::slider` (float) | `Size` | 10 … 72 | `%.0f px` | a local copy of `settings_.fontSize` | `setFontSize(size)` |
| `ui::slider` | `Line spacing` | 1.0 … 2.2 | `%.2f` | `settings_.lineSpacing` | relayout |
| `ui::slider` | `Side margins` | 0 … 20 | `%.0f %%` (shows `6 %`) | `marginPct = settings_.margin * 100` | `settings_.margin = marginPct / 100`; relayout |
| `ui::slider` | `First-line indent` | 0 … 4 | `%.1f em` | `settings_.paragraphIndent` | relayout |
| `ui::slider` | `Space between paragraphs` | 0 … 1.5 | `%.1f em` | `settings_.paragraphSpacing` | relayout |
| `Checkbox` | `Justify` | – | – | `settings_.justify` | relayout |
| `Checkbox` | `Hyphenation (English, Russian)` | – | – | `settings_.hyphenate` | relayout |
| `ImGui::Combo` (3 items) | `Pages on screen` | `Automatic (two when wide)`, `One page`, `Two pages, like a book`, standing for `"auto"`, `"1"`, `"2"` | – | index from `settings_.columns`: `"1"` → 1, `"2"` → 2, anything else → 0 | `setColumns(colIds[colIdx])` |
| note | – | – | – | – | see below |
| `ui::slider` | `Max line length` | 20 … 80 | `%.0f em` | `settings_.maxLineWidth` | relayout. Tooltip `Single-page mode: long lines are hard to read; 30-45 em is comfortable.` whenever `ImGui::IsItemHovered()` (no touch check, no delay) |

Between `Justify` and `Hyphenation`: `SameLine()`, then `if (ImGui::GetContentRegionAvail().x < ImGui::CalcTextSize("Hyphenation (English, Russian)").x + 50.0f * s) ImGui::NewLine();`.
The note after `Pages on screen` appears when `settings_.columns == "2" && !twoPagesFit_`. It is `PushTextWrapPos(0)`, `TextDisabled("Two pages need a wider screen: turn the device sideways or make the text smaller.")`, `PopTextWrapPos()`.

### 11.2 `SeparatorText("Colours")`

- With `ti = themeIndex(settings_.theme)` and `narrow = narrowUi()`, for each theme in `themes()` order: `if (ImGui::RadioButton(t.name, i == ti)) setTheme(t.id);`. Then, on a narrow panel, `Indent(GetFrameHeight() + style.ItemInnerSpacing.x)`, which puts the note on the next line aligned with the radio's label. On a wide panel, `SameLine(180.0f * s)` puts the note in a column 180·s from the window's left edge. Then `PushTextWrapPos(0)`, `TextDisabled("%s", t.note)`, `PopTextWrapPos()`, and on a narrow panel `Unindent` by the same amount. The notes are the `note` strings of `Themes.cpp`.
- `ui::slider("Brightness", &settings_.brightness, 0.2f, 1.0f, "%.2f", s)` → `refreshTheme(); applyImGuiStyle(); scheduleSave();`. Tooltip `Dark themes dim the text, light themes dim the paper.` when `ImGui::IsItemHovered()` (no touch check, no delay).
- `Checkbox("Switch themes by the clock", &settings_.autoNight)` → `checkAutoNight(true); scheduleSave();`.
- While `settings_.autoNight`: `Indent()` (default indent), then:
  - `ui::slider("Night starts at", &settings_.nightFrom, 0, 23, "%d:00", s)` (int), showing for example `21:00`;
  - `ui::slider("Night ends at", &settings_.nightTo, 0, 23, "%d:00", s)`;
  - a theme drop-down `Day theme` bound to `settings_.dayTheme`, then `Night theme` bound to `settings_.nightTheme`. Each is `BeginCombo(label, themes()[themeIndex(id)].name)` with `Selectable(t.name, id == t.id)` for every theme; a click sets `id = t.id`.
  - If any of these four changed: `checkAutoNight(true); scheduleSave();`. Then `Unindent()`.

### 11.3 `SeparatorText("Page turning")`

- `ImGui::Combo("Animation", &turnIdx, turnNames, 4)` with names `3D page curl`, `Slide`, `Fade out and in`, `Instant`, standing for `"curl"`, `"slide"`, `"fade"`, `"none"`. The index comes from `settings_.pageTurn`: `"slide"` → 1, `"fade"` → 2, `"none"` → 3, anything else → 0. On change: `if (turning_) finishTurn(); settings_.pageTurn = turnIds[turnIdx]; scheduleSave();`.
- If `turnIdx == 3`, including when it was just chosen: wrapped `TextDisabled("The next and previous pages are prepared ahead, so the page changes at once.")`. Otherwise `ui::slider("Duration", &settings_.turnSeconds, 0.15f, 1.2f, "%.2f s", s)` → `scheduleSave()`.

### 11.4 `SeparatorText("Screen")`

- `Checkbox("Keep the screen on while reading", &settings_.keepScreenOn)` → `applyScreenSaver(); scheduleSave();`.
- Only if `platform::canSetScreenBrightness()` (Android). This is Lanternleaf's own screen brightness, which other apps do not share; a swipe on the left part of the page also sets it:
  - `own = settings_.screenBrightness >= 0`. `level = 100 × (own ? settings_.screenBrightness : sqrt(clamp(platform::systemScreenBrightness(), 0, 1)))`.
  - `ui::slider("Screen brightness", &level, 1.0f, 100.0f, own ? "%.0f %%" : "%.0f %% (system)", s)` → `setScreenBrightness(level / 100.0f)`. It shows for example `55 %` or `55 % (system)`.
  - `Button("Use the system brightness")` inside `BeginDisabled(!own)` → `setScreenBrightness(-1.0f)`.
  - Wrapped `TextDisabled("While reading: swipe up or down on the left part of the page.")`.
- `Checkbox(touchFirst_ ? "Hide the status and navigation bars" : "Full screen", &fullscreen)` on a local copy of `settings_.fullscreen` → `toggleFullscreen()`.

### 11.5 `SeparatorText("Storage")`

- `TextDisabled("Settings, reading positions and the search cache live in:")`
- `TextWrapped("%s", prefDir_.c_str())`
- `if (platform::canRevealFiles() && ImGui::Button("Show folder")) platform::revealInFileManager(settingsFile_);` opens the file manager with `settings.json` selected. This is desktop only.

## 12. Go to panel: `drawGoto()`

1. `placePanel()`, `focusIfRequested(Panel::Goto)`, `ImGui::Begin("Go to", &showGoto_, panelFlags)` (if false: `End()`, return). This panel has no `ui::touchScroll`.
2. Without a book: `TextDisabled("No book is open.")`, `End()`, return.
3. When the window is appearing: `gotoPercent_ = currentPercent() * 100`, and `gotoPage_` is `layout_->pageIndexOf(viewStart_) + 1` if the pages are counted, else 1.
4. `fieldW = max(120·s, GetContentRegionAvail().x - 90·s)`.
5. `SetNextItemWidth(fieldW)`. `ui::slider("##pct", &gotoPercent_, 0.0f, 100.0f, "%.1f %%", displayScale_)` (for example `42.3 %`; its return value is unused). `SameLine()`. `if (ImGui::Button("Go##pct")) goToPercent(gotoPercent_ / 100.0);`.
6. If `layout_->countDone()`:
   - `SetNextItemWidth(fieldW)`, then `ImGui::InputInt("##page", &gotoPage_, 1, 100, ImGuiInputTextFlags_CharsDecimal)`. The step is 1 and the fast step 100, with `-` / `+` buttons; decimal input brings up a number pad on phones.
   - `gotoPage_ = std::clamp(gotoPage_, 1, std::max(1, layout_->pageCount()))` every frame.
   - `SameLine()`. `Button("Go##page")` → `if (turning_) finishTurn(); setViewStart(layout_->pageStart(gotoPage_ - 1), true);`.
   - `TextDisabled("Page %d of %d", gotoPage_, layout_->pageCount())`.
7. Otherwise: `TextDisabled("Counting pages... %.0f%%", layout_->countProgress() * 100.0f)`, for example `Counting pages... 37%`.
8. `End()`. The panel stays open after either Go. Both buttons read `Go`; the part after `##` is only the ID.

## 13. Help panel: `drawHelp()`

`placePanel()`, `focusIfRequested(Panel::Help)`, `ImGui::Begin("Help", &showHelp_, panelFlags)` (if false: `End()`, return), `ui::touchScroll(s)`. Then, in order:

1. `ImGui::Text("Lanternleaf %s", kAppVersion)`, which shows `Lanternleaf 0.6.0`. Then `SameLine()` and `SmallButton("About")` → `showPanel(Panel::About)`, which replaces Help.
2. In the disabled colour (`PushStyleColor(ImGuiCol_Text, TextDisabled colour)` … `PopStyleColor()`): `ImGui::TextWrapped("A reader for FB2 and TXT books, drawn entirely on the GPU (OpenGL). %s.", LL_COPYRIGHT)`, which shows `… (OpenGL). © 2026 Vitali Pinzari.`.
3. Touch screens only: `SeparatorText("Touch")`, then a table `##touch` with 2 columns and flags `ImGuiTableFlags_RowBg | ImGuiTableFlags_SizingStretchProp`. The columns are `What` (`WidthStretch`, 0.4) and `How` (`WidthStretch`, 0.6). They are set up but no header row is drawn. Rows are added with `helpRow`, in this order:

| # | What | How |
|---|---|---|
| 1 | `Next page` | `Tap the right part of the page, or swipe left` |
| 2 | `Previous page` | `Tap the left third, or swipe right` |
| 3 | `Menu and status bar` | `Tap the middle of the page; any tap on the page hides them again` |
| 4 | `Status bar` | `Tap the chapter for the contents, the bar to jump there, the page number or the percentage to type one in` |
| 5 | `Screen brightness` | `Swipe up or down on the left part of the page` |
| 6 | `Bigger / smaller text` | `Pinch with two fingers, or A+ / A-` |
| 7 | `One page / two pages` | `The 1 page / 2 pages buttons, or under Menu when they do not fit` |
| 8 | `Menu` | `At the right end of the toolbar: everything that does not fit on it, and About` |
| 9 | `Footnotes` | `Tap the footnote number` |
| 10 | `Close a menu or panel` | `Tap the page outside it, or Back` |
| 11 | `Leave the app` | `Back on the page (your place is saved)` |

4. The keyboard list. On phones and tablets it is only for an attached keyboard, so it is folded away by default. `bool showKeys = true;`. On touch screens: `Spacing()`, then `showKeys = ImGui::CollapsingHeader("Keyboard and mouse")` (closed by default). Otherwise: `SeparatorText("Keyboard, mouse and touch")`. If `showKeys`, a table `##keys` with 2 columns and flags `RowBg | SizingStretchProp`, columns `What` (stretch 0.32) and `How` (stretch 0.68), no header row:

| # | What | How |
|---|---|---|
| 1 | `Next page` | `Right, Down, Page Down, Space, mouse wheel down, click the right part of the page` |
| 2 | `Previous page` | `Left, Up, Page Up, Shift+Space, Backspace, mouse wheel up, click the left third` |
| 3 | `First / last page` | `Home / End` |
| 4 | `Bigger / smaller text` | `Ctrl + mouse wheel, Ctrl+Plus / Ctrl+Minus, two-finger pinch` |
| 5 | `Default text size` | `Ctrl+0` |
| 6 | `Open a book` | `Ctrl+O, or drag an FB2/TXT/ZIP file onto the window` |
| 7 | `Find books on your drives` | `Ctrl+F` |
| 8 | `Find in this book` | `Ctrl+Shift+F` |
| 9 | `Recent books` | `Ctrl+L` |
| 10 | `Contents` | `T` |
| 11 | `Go to page or position` | `Ctrl+G` |
| 12 | `Colour theme` | `C next, Shift+C previous, Ctrl+1 ... Ctrl+5` |
| 13 | `One page / two pages (book)` | `B, or the 1 page / 2 pages buttons` |
| 14 | `Settings` | `Ctrl+Comma` |
| 15 | `Toolbar and status bar` | `Move the pointer to the top or the bottom edge; right click or F10 keeps them open` |
| 16 | `Status bar` | `Click the chapter for the contents, the bar to jump there (or drag), the page number or the percentage to type one in` |
| 17 | `Full screen` | `F11 or Alt+Enter` |
| 18 | `Footnotes` | `Click the footnote number` |
| 19 | `Close a panel` | `Esc, or click the page outside it` |

   (Row 12 has three ASCII full stops between `Ctrl+1` and `Ctrl+5`, with a space on each side. Row 4 is `Ctrl + mouse wheel` with spaces around `+`, while the other shortcuts have none.)
5. `SeparatorText("Why these colour themes")`, `PushTextWrapPos(0)`, then `TextUnformatted` of exactly this literal, then `PopTextWrapPos()`:
   ```cpp
   "Day and Sepia use dark text on a light page, which reads best in a lit room. In the evening, short-wavelength "
   "(blue) light is what suppresses melatonin most (Brainard et al. 2001; Thapan et al. 2001), and reading on a "
   "light-emitting screen before bed delays sleep (Chang et al., PNAS 2015). Dusk removes almost all blue; Night "
   "amber emits only long-wavelength light (~600 nm), in line with studies on amber light and blue-blocking "
   "glasses (Burkhart & Phelps 2009); Night red (>610 nm) also keeps your eyes dark-adapted, because rods are "
   "almost blind to red - the reason astronomers and pilots use red light. The Brightness slider dims the text "
   "further. Themes colour the text only: pictures keep their own colours, and web links stay blue and "
   "underlined."
   ```
6. `SeparatorText("Credits")`, `PushTextWrapPos(0)`, `TextUnformatted` of:
   ```cpp
   "PT Serif and PT Sans by ParaType (SIL Open Font License). Hyphenation patterns from the hyph-utf8 project: "
   "American English by Gerard D.C. Kuiken, Russian by Alexander I. Lebedev (LPPL). Built with SDL3, FreeType, "
   "HarfBuzz, Dear ImGui, glad, miniz, stb and nlohmann/json."
   ```
   then `PopTextWrapPos()` and `End()`.

## 14. About panel: `drawAbout()`

`s = displayScale_`, `placePanel()`, `focusIfRequested(Panel::About)`, `ImGui::Begin("About Lanternleaf", &showAbout_, panelFlags)` (if false: `End()`, return). The contents, verbatim:

```cpp
  ui::touchScroll(s);
  ImGui::PushFont(nullptr, ImGui::GetStyle().FontSizeBase * 1.9f);
  ImGui::TextUnformatted("Lanternleaf");
  ImGui::PopFont();
  ImGui::Text("Version %s", kAppVersion);
  ImGui::SameLine();
  ImGui::TextDisabled("%s", platform::systemDescription().c_str());
  ImGui::Spacing();
  ImGui::TextWrapped("A reader for FB2 and TXT books, drawn with OpenGL: justified, hyphenated text in English and "
                     "Russian, a 3D page curl, colour themes for day and night, and a search that finds books "
                     "anywhere on your drives.");
  ImGui::Spacing();
  ImGui::Text("%s. Released under the MIT License.", LL_COPYRIGHT);
  ImGui::Text("Developer: %s", LL_DEVELOPER);

  if (touchFirst_) {
    ImGui::SeparatorText("This device");
    const bool access = storageAccess();
    ImGui::Text("Access to files: %s", access ? "allowed" : "not allowed");
    if (!access) {
      ImGui::SameLine();
      if (ImGui::SmallButton("Allow")) {
        platform::requestStorageAccess();
        storageAccessChecked_ = -100;
      }
    }
  }

  ImGui::SeparatorText("Credits");
  ImGui::PushTextWrapPos(0);
  ImGui::TextUnformatted(
      "Fonts: PT Serif and PT Sans by ParaType (SIL Open Font License 1.1).\n"
      "Hyphenation patterns: the hyph-utf8 project - American English by Gerard D.C. Kuiken, Russian by "
      "Alexander I. Lebedev and others.\n"
      "Built with SDL 3 (zlib), FreeType (FreeType License), HarfBuzz (MIT), Dear ImGui (MIT), miniz (MIT), "
      "stb (MIT / public domain), JSON for Modern C++ (MIT) and glad (MIT).\n"
      "Colour themes follow research on light and sleep by Brainard et al., Thapan et al., Chang et al. and "
      "Burkhart & Phelps (see Help).");
  ImGui::PopTextWrapPos();
  if (ImGui::CollapsingHeader("Licences of these components")) {
    if (noticesText_.empty()) {
      std::vector<unsigned char> data;
      noticesText_ = platform::loadAsset("licenses/THIRD-PARTY-NOTICES.txt", data)
                         ? std::string(data.begin(), data.end())
                         : std::string("The licence texts are missing from this installation.");
    }
    ImGui::PushTextWrapPos(0);
    ImGui::TextUnformatted(noticesText_.c_str(), noticesText_.c_str() + noticesText_.size());
    ImGui::PopTextWrapPos();
  }
  ImGui::End();
```

The copyright line `ImGui::Text("%s. Released under the MIT License.", LL_COPYRIGHT);` is the only intended difference from the 0.6.0 About panel.

What it shows: `Lanternleaf` in a 1.9× larger font. Then `Version 0.6.0`, followed on the same line by the system description in the disabled colour (`platform::systemDescription()`, for example `Windows x64` or `Android (API 34) arm64`). Then the description paragraph, and `© 2026 Vitali Pinzari. Released under the MIT License.` and `Developer: Vitali Pinzari`. On touch screens a section `This device` follows, with `Access to files: allowed` or `Access to files: not allowed` plus a small `Allow` button. The `Allow` button asks Android for "All files access" and forces the access state to be checked again on the next call. Then come the four credit paragraphs, separated by line breaks, and a collapsing header `Licences of these components`, closed by default. The first time that header is opened, the bundled asset `licenses/THIRD-PARTY-NOTICES.txt` is read once into `noticesText_` and kept for the rest of the session. If the asset is missing, the text is `The licence texts are missing from this installation.`, and that text is also cached.

## 15. Footnote pop-up: `drawFootnote()`

The pop-up is opened by `followLink` when a footnote reference is clicked or tapped. Its window coordinates are `footnoteX_`, `footnoteY_`.

```cpp
  const float s = displayScale_;
  const ImGuiViewport* vp = ImGui::GetMainViewport();
  const float maxW = std::min(560.0f * s, vp->Size.x * 0.9f);
  float x = std::clamp(footnoteX_ - maxW * 0.5f, vp->Pos.x + 8.0f, vp->Pos.x + vp->Size.x - maxW - 8.0f);
  float y = footnoteY_ + 14.0f * s;
  if (y > vp->Pos.y + vp->Size.y * 0.6f) y = std::max(vp->Pos.y + 8.0f, footnoteY_ - vp->Size.y * 0.35f);
  ImGui::SetNextWindowPos(ImVec2(x, y), ImGuiCond_Appearing);
  ImGui::SetNextWindowSizeConstraints(ImVec2(260.0f * s, 0), ImVec2(maxW, vp->Size.y * 0.6f));
```

Then `ImGui::Begin("Footnote", &showFootnote_, ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings)`. When `Begin` returns true:

1. If `footnoteTitle_` is not empty: `TextDisabled("%s", footnoteTitle_)`.
2. `PushTextWrapPos(maxW - 30.0f * s)`, `TextUnformatted(footnoteText_)`, `PopTextWrapPos()`.
3. `Separator()`.
4. `Button("Go to the note")` → `showFootnote_ = false; goToBlock(footnoteBlock_, 0);`. Then `SameLine()` and `Button("Close")` → `showFootnote_ = false`.

`End()` is always called. The pop-up is placed when it appears. It is centred horizontally on the click, kept 8 units (unscaled) from the viewport's sides, and starts 14·s below the click. If that would put its top lower than 60 % of the screen, it opens 35 % of the screen height above the click instead, but never above 8 units from the top. Its width is between 260·s and `maxW`, and its height is at most 60 % of the screen. It has a title bar `Footnote` with a close button. It can be moved, and it is not a panel: it is not dimmed and does not close other panels.

## 16. Messages: `drawMessages()`

Nothing is drawn while `messages_` is empty. Otherwise:

```cpp
  const ImGuiViewport* vp = ImGui::GetMainViewport();
  const float above = barsShown_ ? bottomBarH_ : 0.0f;  // above the status bar when it shows
  ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + vp->Size.x * 0.5f, vp->Pos.y + vp->Size.y - 50.0f * displayScale_ - above),
                          ImGuiCond_Always, ImVec2(0.5f, 1.0f));
  if (ImGui::Begin("##messages", nullptr,
                   ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoSavedSettings)) {
    for (const std::string& m : messages_) ImGui::TextUnformatted(m.c_str());
    if (ImGui::Button("OK")) messages_.clear();
  }
  ImGui::End();
```

The messages box is centred horizontally. Its bottom edge is 50·s above the bottom of the screen, or above the status bar while that shows; the bottom safe inset is not added. It lists every error message, one per line and unwrapped, with an `OK` button that dismisses all of them.

## 17. Toast and storage access

### 17.1 Toast: `showToast(text, seconds)` and `drawToast()`

`showToast` sets `toast_ = text` and `toastUntil_ = now() + seconds` (the header's default is 5.0). It starts a one-shot SDL timer of `static_cast<Uint32>(seconds * 1000 + 50)` ms whose callback calls `wake()` and returns 0, so the note disappears on time even when nothing else happens. Then it calls `requestRedraw()`.

`drawToast()`:

1. If `toast_` is empty, return. If `now() > toastUntil_`, clear `toast_` and return.
2. Position: at the top, below the toolbar when it shows, because the bottom belongs to the footer. `top = std::max(toolbarHeight_, safeTop_ * k) + 10.0f * displayScale_`. `SetNextWindowPos(ImVec2(vp->Pos.x + vp->Size.x * 0.5f, vp->Pos.y + top), ImGuiCond_Always, ImVec2(0.5f, 0.0f))`, which centres the window horizontally.
3. `SetNextWindowSizeConstraints(ImVec2(0, 0), ImVec2(vp->Size.x * 0.9f, vp->Size.y * 0.5f))` and `SetNextWindowBgAlpha(0.94f)`.
4. `Begin("##toast", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav)`. Inside: `PushTextWrapPos(vp->Size.x * 0.85f)`, `TextUnformatted(toast_)`, `PopTextWrapPos()`. Then `End()`.

The toast ignores all input. App.cpp also writes `toast_` / `toastUntil_` directly, for the live `Screen brightness NN %` note during a brightness swipe.

### 17.2 `storageAccess()` and `onStorageAccessGranted()`

```cpp
bool App::storageAccess() {
  if (now() - storageAccessChecked_ > 1.0) {
    const bool had = storageAccessCached_;
    storageAccessCached_ = platform::hasStorageAccess();
    storageAccessChecked_ = now();
    if (storageAccessKnown_ && !had && storageAccessCached_) onStorageAccessGranted();
    storageAccessKnown_ = true;
  }
  return storageAccessCached_;
}
```

This is a cached `platform::hasStorageAccess()` (always true on desktops), re-checked at most once a second. Setting `storageAccessChecked_ = -100` forces a check at the next call. Every "Allow" button does that, and so does App.cpp on returning to the foreground. A change from "no access" to "access", after the first check, calls:

```cpp
void App::onStorageAccessGranted() {
  // Lists made without access show folders but no books (Android hides other apps' files): make them again.
  SDL_Log("file access granted");
  storagePromptOpen_ = false;
  if (browser_.open && !browser_.dir.empty()) browseTo(browser_.dir);
  if (searchNeedsAccess_) {
    searchNeedsAccess_ = false;
    startLibrarySearch();
  }
  requestRedraw();
}
```

### 17.3 Storage notice inside panels: `drawStorageAccessNotice()`

This is shown at the top of the Find books tab (after the check boxes) and of the file browser while `!storageAccess()`, which happens only on Android:

1. In the accent colour (`PushStyleColor(ImGuiCol_Text, CheckMark colour)`): `ImGui::TextWrapped("Lanternleaf cannot see your books yet: Android shows it the folders, but not the files in them. " "Tap the button, switch on \"Allow access to manage all files\", then come back.")`. Then `PopStyleColor()`.
2. `Button("Allow access to files")` → `platform::requestStorageAccess(); storageAccessChecked_ = -100;`.
3. `Separator()`.

### 17.4 First-start prompt: `drawStoragePrompt()`

This is drawn while `storagePromptOpen_`. App.cpp sets that flag at start-up on touch screens without access, unless the user chose "Don't ask again" (`settings_.storagePromptDismissed`).

1. If `storageAccess()` is true: `storagePromptOpen_ = false`, return.
2. The window is centred at (50 %, 45 %) of the viewport (`SetNextWindowPos(…, ImGuiCond_Always, ImVec2(0.5f, 0.5f))`). Its width is `std::min(560.0f * s, vp->Size.x * 0.92f)` with automatic height (`SetNextWindowSize(ImVec2(w, 0), ImGuiCond_Always)`). `SetNextWindowFocus()` is called every frame.
3. `Begin("Your books###storage", nullptr, ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_AlwaysAutoResize)`. The title is `Your books`, with no close button. Contents:
   - `TextWrapped("Lanternleaf finds and opens FB2 and TXT books wherever they are on this device: Download, " "Documents, Books, Telegram, SD cards. Android allows that only with \"All files access\".")`
   - `Spacing()`
   - `TextWrapped("Tap \"Allow access\", switch on \"Allow access to manage all files\" for Lanternleaf, then " "come back. Lanternleaf only reads books; it never changes your files.")`
   - `Spacing()`
   - `Button("Allow access")` → `platform::requestStorageAccess(); storageAccessChecked_ = -100;`. Then `SameLine()`.
   - `Button("Not now")` → `storagePromptOpen_ = false`. Then `SameLine()`.
   - `Button("Don't ask again")` → `storagePromptOpen_ = false; settings_.storagePromptDismissed = true; scheduleSave();`.
   - In the disabled colour: `TextWrapped("If the switch is greyed out: Settings > Apps > Lanternleaf > the three-dot menu > " "\"Allow restricted settings\", then try again.")`. The `>` are ASCII greater-than signs.
4. `End()`.

The prompt closes by itself as soon as access is granted (step 1, or `onStorageAccessGranted`).

## 18. System dialogs: `openFileDialog()` and `addFolderDialog()`

```cpp
void App::openFileDialog() {
  if (touchFirst_) {
    // Android pickers return content:// URIs that cannot be reopened later: browse real paths instead.
    openFileBrowser(false);
    return;
  }
  static const SDL_DialogFileFilter kFilters[] = {{"Books (FB2, TXT, FB2.ZIP)", "fb2;txt;zip"}, {"All files", "*"}};
  std::string dir;
  if (!bookPath_.empty()) dir = dirOf(bookPath_);
  if (dir.empty()) {
    const auto roots = platform::defaultSearchRoots();
    if (!roots.empty()) dir = roots.front();
  }
  SDL_ShowOpenFileDialog(
      [](void* ud, const char* const* list, int) {
        App* app = static_cast<App*>(ud);
        if (!list || !list[0]) return;
        {
          std::lock_guard<std::mutex> lock(app->asyncMutex_);
          app->pendingOpen_.emplace_back(list[0]);
        }
        app->wake();
      },
      this, window_, kFilters, 2, dir.empty() ? nullptr : dir.c_str(), false);
}

void App::addFolderDialog() {
  if (touchFirst_) {
    openFileBrowser(true);
    return;
  }
  SDL_ShowOpenFolderDialog(
      [](void* ud, const char* const* list, int) {
        App* app = static_cast<App*>(ud);
        if (!list) return;
        {
          std::lock_guard<std::mutex> lock(app->asyncMutex_);
          for (int i = 0; list[i]; ++i) app->pendingFolders_.emplace_back(list[i]);
        }
        app->wake();
      },
      this, window_, nullptr, true);
}
```

- On desktops the file dialog has two filters: `Books (FB2, TXT, FB2.ZIP)` (patterns `fb2;txt;zip`) and `All files` (`*`). It allows a single selection. It starts in the folder of the open book, else in the first default search root (normally Downloads), else in SDL's default location. The chosen file is opened on the main thread by `pollAsync`.
- The folder dialog allows several folders and has no default location. `pollAsync` adds the chosen folders to the search roots.
- On touch screens both open the in-app file browser (§19): in file mode for Open, in folder mode for Add folder.

## 19. File browser (FileBrowser.cpp)

The in-app browser is used on Android, where the system pickers return content URIs. With "All files access", books are opened by their real paths instead.

### 19.1 `openFileBrowser(bool folderMode)`

```cpp
void App::openFileBrowser(bool folderMode) {
  showPanel(Panel::Browser);  // closes any other panel
  browser_.folderMode = folderMode;
  std::string start = browser_.dir;
  if (start.empty() || !isDirectory(start)) {
    start.clear();
    if (!bookPath_.empty() && bookPath_.find("/files/opened/") == std::string::npos) start = parentOf(bookPath_);
    if (start.empty() || !isDirectory(start)) {
      const auto roots = platform::defaultSearchRoots();
      if (!roots.empty()) start = roots.front();
    }
    if (start.empty() || !isDirectory(start)) {
      const auto drives = platform::driveRoots();
      if (!drives.empty()) start = drives.front();
    }
  }
  browseTo(start);
}
```

The browser opens in the folder it showed last, if that still exists. Otherwise it opens in the open book's folder, unless the book's path contains `/files/opened/` (a copy inside the app's own storage). After that it falls back to the first default search root, then to the first drive root. The folder is always listed afresh.

### 19.2 `browseTo(const std::string& dir)`

```cpp
void App::browseTo(const std::string& dir) {
  browser_.dir = dir;
  browser_.entries.clear();
  browser_.error.clear();
  browser_.scrollTop = true;
  std::error_code ec;
  fs::directory_iterator it(pathFromUtf8(dir), fs::directory_options::skip_permission_denied, ec);
  if (ec) {
    browser_.error = storageAccess() ? "This folder cannot be read." : "Lanternleaf has no access to your files yet.";
    return;
  }
  const fs::directory_iterator end;
  for (; it != end; it.increment(ec)) {
    if (ec) break;
    try {
      const fs::directory_entry& e = *it;
      const std::string name = pathToUtf8(e.path().filename());
      if (name.empty() || name[0] == '.') continue;
      std::error_code ec2;
      if (e.is_directory(ec2)) {
        browser_.entries.push_back(BrowserEntry{name, pathToUtf8(e.path()), true, 0});
      } else if (isSupportedBookName(name)) {
        const uint64_t size = e.file_size(ec2);
        browser_.entries.push_back(BrowserEntry{name, pathToUtf8(e.path()), false, ec2 ? 0 : size});
      }
    } catch (...) {
      // unconvertible names: skip
    }
  }
  std::sort(browser_.entries.begin(), browser_.entries.end(), [](const BrowserEntry& a, const BrowserEntry& b) {
    if (a.dir != b.dir) return a.dir;
    return toLowerUtf8(a.name) < toLowerUtf8(b.name);
  });
}
```

The listing hides names starting with `.` and keeps only folders and supported book files (`isSupportedBookName`: FB2, TXT and ZIP names). Folders come first, then files, each group sorted by the lower-cased name. A file whose size cannot be read is listed with size 0. If the folder cannot be opened, the list stays empty and the error is `This folder cannot be read.`, or `Lanternleaf has no access to your files yet.` while there is no storage access. The next draw scrolls the list to the top.

### 19.3 `drawFileBrowser()`

1. `flags = placePanel()` (where every panel opens: the top-left half of the reading area). The title is `browser_.folderMode ? "Choose a folder to search###browser" : "Open a book###browser"`, so both modes are the same window (`###browser`). `focusIfRequested(Panel::Browser)`, `ImGui::Begin(title, &browser_.open, flags)` (if false: `End()`, return).
2. `ui::touchScroll(s, false)`: a short panel scrolls to bring the list below the buttons into view.
3. `if (!storageAccess()) drawStorageAccessNotice();` (§17.3).
4. Places, as one flowing row of buttons:
   - For each `drives[i]` of `platform::driveRoots()` (inside `PushID(static_cast<int>(i))`): the label is `Device storage` for `i == 0`, else `"Card " + fileNameOf(drives[i])` (for example `Card 1234-ABCD`). The button calls `browseTo(drives[i])`, followed by `SameLine()`. These buttons never wrap.
   - For each `r` of `platform::defaultSearchRoots()` (inside `PushID(r.c_str())`): the label is `fileNameOf(r)` (for example `Download`). If it is longer than 24 bytes, it becomes its first 22 bytes + `"\xE2\x80\xA6"` (a byte cut, not a code-point cut). If `GetContentRegionAvail().x < CalcTextSize(label).x + 40.0f * s`, call `NewLine()`. Then the button calls `browseTo(r)`, followed by `SameLine()`.
   - `NewLine()` ends the row.
5. `Up` button, disabled when `parentOf(browser_.dir)` is empty or equals `browser_.dir` (at a root). It calls `browseTo(parentOf(browser_.dir))`. Then `SameLine()` and `TextWrapped("%s", browser_.dir)`, which is the current path.
6. Folder mode only: `Button("Search this folder for books")`. It appends `browser_.dir` to `settings_.searchRoots` if it is not listed, calls `scheduleSave()`, sets `browser_.open = false`, then `showPanel(Panel::Library, 1)`: back to "Find books", where the folder is now listed.
7. `Separator()`.
8. If `browser_.error` is set: `TextDisabled("%s", error)`. Otherwise, if there are no entries: `TextDisabled("No folders or FB2/TXT books here.")`.
9. The list: `BeginChild("##entries", ImVec2(0, ui::listHeight()))`, with no border and full width. When `BeginChild` returns true:
   - if `browser_.scrollTop`: `SetScrollY(0)` and `scrollTop = false`;
   - `ui::touchScroll(s)`;
   - an `ImGuiListClipper` over the entries, each row inside `PushID(i)`:
     - Folder: drawn in the accent colour (`PushStyleColor(ImGuiCol_Text, CheckMark colour)`) as `Selectable(e.name + "/")`. When `ui::tapped`, it sets `goDir = e.path`.
     - File: drawn as `Selectable(e.name + "   " + sizeText(e.size))` (three spaces), for example `War and Peace.fb2   1.2 MB`, inside `BeginDisabled(browser_.folderMode)`. When `ui::tapped`, it sets `openFile = e.path`.

   `EndChild()` is always called, then `End()`.
10. After the window: `if (!goDir.empty()) browseTo(goDir); if (!openFile.empty()) openBook(openFile);`. A successful open closes the browser, and a failed one shows an error message.

## 20. Where the touch helpers are used

| Helper (`UiHelpers.h`) | Call sites |
|---|---|
| `ui::touchScroll(s)` | About window; Contents window (after the empty check); Settings window; Help window; inside the Recent, results and find tables (right after `BeginTable`); inside the browser's `##entries` child |
| `ui::touchScroll(s, false)` | Library window (before the tab bar); browser window (before the storage notice). Lists of their own scroll these panels. |
| `ui::tapped(clicked, s)` | Status bar: chapter, page and percentage flat buttons. Rows of Recent, results, find (both layouts), Contents and the browser (folders and files). |
| `ui::slider(…, s)` | Every slider in Settings (`Size`, `Line spacing`, `Side margins`, `First-line indent`, `Space between paragraphs`, `Max line length`, `Brightness`, `Night starts at`, `Night ends at`, `Duration`, `Screen brightness`) and the Go to percentage slider |
| `ui::listHeight()` | Height of the Recent, results and find tables and of the browser's entry list |
| `ui::touchInput()` | Tooltip gate in the Library: Recent row path, result row details, and the two check-box tooltips |

No touch helper is used by the toolbar, the Menu, the footnote, the messages, the toast or the storage prompt. The Go to panel uses `ui::slider` but has no `ui::touchScroll`, so it does not scroll with a finger. Buttons, check boxes, radio buttons and combos rely on `touchScroll`'s release of the active item when a finger scrolls; no `ui::tapped` wraps them.

## 21. Tooltips

| Where | Condition | Text |
|---|---|---|
| Toolbar items and the Menu button | `!touchFirst_` and `IsItemHovered(DelayNormal)` | per §6.4 / §6.6 |
| Toolbar theme list entries | `!touchFirst_` and `IsItemHovered()` | the theme's `note` |
| Status bar chapter | `!touchFirst_` and `IsItemHovered(DelayNormal)` | `Contents (T)` |
| Progress bar (hovered, not held) | `!touchFirst_` | `Click or drag to move through the book` |
| Progress bar (held) | always, while the mouse position is valid | `%.1f %%` + chapter (§7.5) |
| Page field | `!touchFirst_` and `IsItemHovered` with `DelayNormal` + `AllowWhenDisabled` | `Go to a page`, or `Counting the pages...` while disabled |
| Percentage field | the same | `Go to a percentage of the book` |
| Recent row | `!ui::touchInput()` and `IsItemHovered(DelayNormal)` (not for missing books) | the full path |
| Result row | `!ui::touchInput()` and `IsItemHovered(DelayShort)` | path; `Series: %s`; `%s, %s` (format, size); snippet |
| `Text inside books (slow)` | `!ui::touchInput()` and `IsItemHovered()` | `"Reads every book and looks for the whole phrase, ignoring case and \xD1\x91/\xD0\xB5."` |
| `Skip non-book .txt` | `!ui::touchInput()` and `IsItemHovered()` | `Ignores .txt files under 16 KB and licence/readme/changelog files.` |
| `Max line length` | `IsItemHovered()` | `Single-page mode: long lines are hard to read; 30-45 em is comfortable.` |
| `Brightness` | `IsItemHovered()` | `Dark themes dim the text, light themes dim the paper.` |

## Checklist

Style and bars

- [ ] Desktop at s = 1: window padding 14×12, frame padding 8×5, item spacing 8×7, cell padding 6×4, window rounding 8, frame rounding 5, tab rounding 5, borders 1, UI font 17 px, frame height 27.
- [ ] Touch screens: frame padding 12×9, item spacing 12×10, item inner spacing 10×8, cell padding 8×9, scrollbar 20, grab minimum 24, touch extra padding 4×4 (all × s), UI font 17.5 × s.
- [ ] At brightness 1.00 the Day theme's panel background is (0.967, 0.964, 0.958) and Night amber's is (0.070, 0.046, 0.010). Check marks, slider grabs and the tab overline use the theme accent, and disabled text uses the theme's secondary colour.
- [ ] Choosing a theme (toolbar, Menu, Settings, C key) or moving the Brightness slider recolours the whole UI immediately.
- [ ] Toolbar height is 51 at desktop scale 1. The status bar is 39 on one row and 73 on two rows; it uses two rows when the window is narrower than 640 logical units.
- [ ] Without a book the toolbar is always visible and there is no status bar. Contents, Go to and Find in book are disabled (also in the Menu), and no title is shown.
- [ ] On touch screens an open panel or the storage prompt dims the page behind all UI windows: black, alpha 120 of 255 with dark themes, 80 with light ones. The footnote alone does not dim.

Toolbar and Menu

- [ ] With room for everything the order is: Open, Library, Find books, Contents, Go to, Find in book, `|`, `A-`, the size, `A+`, the theme drop-down (140·s wide), `1 page` and `2 pages` (2·s apart), Settings, the full-screen button, Help, and `Menu` against the right edge.
- [ ] Narrowing the window moves items into the Menu in this order: Find in book, Go to, full screen, Help, 1 page / 2 pages, Find books, Settings, Contents, Library, theme, text size, Open. A narrower item returns as soon as it fits again.
- [ ] The Menu lists the hidden items in toolbar order with their menu labels (`Open a book`, `Recent books`, `Find books`, `Contents`, `Go to page`, `Find in this book`, `Text size` with `A-`/`A+`, the `Colour theme` submenu, `One page` and `Two pages, like a book`, `Settings`, `Full screen` / `Leave full screen` / `Show system bars`, `Help`), then a separator, then `About Lanternleaf`. With nothing hidden it holds `About Lanternleaf` alone. It opens below the Menu button, right-aligned with it.
- [ ] `A-` / `A+` inside the Menu change the size and leave the Menu open.
- [ ] The pages button of the column count actually shown (`1 page` or `2 pages`) is drawn in the pressed colour. With "auto" this follows the window shape.
- [ ] `Library` closes the panel only if it is open on the Recent tab; otherwise it opens or switches to Recent. `Find books` and `Find in book` open their Library tab. The keyboard focus goes into that tab's query field when the Library was showing (or last showed) the same tab or Recent. Coming straight from the other search tab, that tab's field takes the focus request during the one transition frame.
- [ ] The full-screen button reads `Full screen`. In full screen it reads `Window` on desktops and `System bars` on touch screens.
- [ ] With a book open, `Author — Title` (U+2014) appears in the disabled colour just before Menu, but only if more than 30·s stays free after the last item.
- [ ] Desktop toolbar tooltips appear after the normal hover delay, for example `Open a book (Ctrl+O)`. Touch screens show no hover tooltips on the toolbar or the status bar; the only tooltip there is the progress bar's while it is dragged.

Status bar

- [ ] While pages are counted the page field reads `… / …` and is disabled; its tooltip is `Counting the pages...`. Afterwards it reads `12 / 345`, or `12–13 / 345` (U+2013) for two pages.
- [ ] The percentage reads `99%` on the last page until the very end, and `100%` only at progress 1.0.
- [ ] The chapter title is shortened with `…` to its width, and clicking it toggles Contents.
- [ ] The progress bar shows ticks at top-level chapter starts only when the TOC has at most 150 entries. Hovering enlarges the knob ×1.35. Dragging shows `42.3 %` and the chapter title in a tooltip above the knob, and releasing jumps there. A single click jumps as well.
- [ ] On desktops, clicking the page number turns it into an input field holding the current page, fully selected. Typing `50` and Enter shows page 50. A number above the total goes to the last page. Clicking elsewhere or Esc cancels.
- [ ] Clicking the percentage pre-fills one decimal (`42.3`). Entering `150` goes to the end.
- [ ] On touch screens the input appears in a small box centred 8·s below the toolbar, reading `Go to page` [field] `of 345`, or `Go to` [field] `%`. The status bar keeps showing the old value.
- [ ] On two rows the progress bar takes the whole first row; chapter, page and percentage share the second.

Panels

- [ ] Each panel opens at the top-left corner of the reading area. It covers the left half when the area is at least as wide as tall, otherwise the top half. On desktops it can then be moved and resized. On touch screens it is fixed and re-placed every frame.
- [ ] Opening any panel closes the panel that was open. Esc closes panels one at a time (spec 09).
- [ ] A panel narrower than 560 logical units uses the short tab labels `Recent` / `Find books` / `In this book`, two-line rows (title above author), fewer columns, and theme notes below their radio buttons.
- [ ] Recent: missing books are greyed out with `  (missing)`, and the `Read` column shows `37%`. On desktops a right click offers `Open`, `Show in folder` and `Remove from the list`; Android has no `Show in folder`. With no books the panel shows the empty-list text for the platform.
- [ ] Find books: `Search` becomes `Stop` while searching. The status line reads `Searching... 120 folders, 3400 files, 85 books, 12 found`, then `Done in 1.2 s: 3400 files in 120 folders, 85 books checked, 12 found.` or `Stopped in …`.
- [ ] Unchecking `File names`, `Title, author, series` and `Text inside books (slow)` and then searching re-checks `File names`.
- [ ] `Where to look (N)` lists the folders with `Remove` buttons, then `Add folder...`, `Add all drives` / `Whole device`, and `Downloads, Documents, Desktop` / `Usual book folders`. The last two wrap to a new line when short of room.
- [ ] Results are sorted by Title ascending at first. Clicking a column header sorts by it, and newly found books are sorted in.
- [ ] Opening a result that was found by its text shows the first occurrence of the query, highlighted, and closes the Library.
- [ ] Find in this book shows `N matches`, plus ` (showing the first 1000)` when truncated. Choosing a row moves the page there and highlights the match; the panel stays open.
- [ ] Contents highlights the current chapter and scrolls it to 40 % on opening. Deeper levels are indented 16·s per level. A book without a TOC shows `This book has no table of contents.`.
- [ ] Settings ranges and formats: Size 10–72 `%.0f px`, Line spacing 1.0–2.2 `%.2f`, Side margins 0–20 `%.0f %%`, First-line indent 0–4 `%.1f em`, Space between paragraphs 0–1.5 `%.1f em`, Max line length 20–80 `%.0f em`, Brightness 0.2–1.0 `%.2f`, Night starts/ends 0–23 `%d:00`, Duration 0.15–1.2 `%.2f s`, Screen brightness 1–100 `%.0f %%` (+ ` (system)`). With `Instant` chosen, the Duration slider is replaced by its note.
- [ ] The Settings layout changes (spacing, margins, indent, paragraph space, justify, hyphenation, line length) re-lay out the page at once and are saved.
- [ ] Go to: the slider shows `42.3 %`. The page input is clamped to 1…page count, followed by `Page N of M`. While pages are counted it shows `Counting pages... 37%` instead of the page input.
- [ ] Help: `Lanternleaf 0.6.0` with a small `About` button. On touch screens it has the `Touch` table (11 rows) and a collapsed `Keyboard and mouse` header; on desktops the `Keyboard, mouse and touch` table (19 rows). Then `Why these colour themes` and `Credits`.
- [ ] About: `Lanternleaf` at 1.9× size, `Version 0.6.0` with the system description, the description paragraph, `© 2026 Vitali Pinzari. Released under the MIT License.`, and `Developer: Vitali Pinzari`. On touch screens it adds `This device` / `Access to files: …`. Then Credits and the collapsed `Licences of these components`, which shows the notices asset.

Pop-ups

- [ ] Footnote: opens 14·s below the reference, horizontally centred on it. Low on the screen (below 60 %) it opens above the reference. Its width is between 260·s and min(560·s, 90 %). `Go to the note` jumps to the note and closes the pop-up; `Close` closes it.
- [ ] Error messages: centred, 50·s above the bottom edge (above the status bar when it shows). `OK` removes all of them.
- [ ] Toast: centred 10·s below the toolbar (or the top safe inset), 94 % opaque, click-through. It disappears on time even if nothing else happens.
- [ ] Android first start without file access shows `Your books`, centred at 45 % of the height, with `Allow access`, `Not now` and `Don't ask again`. It closes by itself once access is granted, and `Don't ask again` is remembered.
- [ ] When access is granted, an open browser lists its folder again, and a search that ran without access runs again.

Dialogs and file browser

- [ ] Desktop Open uses the system file dialog with `Books (FB2, TXT, FB2.ZIP)` (`fb2;txt;zip`) and `All files` (`*`), starting in the open book's folder. Desktop Add folder uses a multi-selection folder dialog, and the folders join the search list.
- [ ] On touch screens Open shows the in-app browser `Open a book`, and Add folder shows `Choose a folder to search`.
- [ ] Browser: place buttons `Device storage`, `Card <volume>` and the default folder names. `Up` is disabled at a root, and the current path is shown. Folders come first, in the accent colour with a trailing `/`, then files as `name   1.2 MB`, each group alphabetical ignoring case. Dot names and non-book files are hidden. An empty folder shows `No folders or FB2/TXT books here.`, and an unreadable one shows `This folder cannot be read.` or `Lanternleaf has no access to your files yet.`.
- [ ] In folder mode files are greyed out, and `Search this folder for books` adds the folder and returns to the Find books tab with it listed.
- [ ] On touch screens a finger drag on a list scrolls it and never opens the row under the finger. A vertical drag that starts on a slider scrolls the panel and leaves the value unchanged; a tap on a slider sets the value.
