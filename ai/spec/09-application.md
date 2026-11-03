# 09 — The application: start-up, window, navigation, input, rendering, persistence

**Scope.** This specification covers `src/app/App.cpp`: the definitions of every `ll::App` member declared in `src/app/App.h` that is not defined in `src/app/AppUi.cpp` or `src/app/FileBrowser.cpp`, plus three file-local helpers. It is the SDL3 application itself: start-up and the command line, the window and the OpenGL context, loading the fonts and the hyphenation patterns, the Dear ImGui set-up, opening a book and restoring the reading position, the page geometry, navigation, the page-turn animations and the instant-turn page cache, frame rendering, all keyboard, mouse, wheel and touch input, text size, themes and the automatic night theme, screen brightness, persistence, frame pacing, results from dialogs and threads, logging, the screenshot/automation mode and shutdown. The panels, toolbar, status bar, toast, messages box, footnote pop-up, storage prompt and the ImGui style (`applyImGuiStyle`) are specified in `10-user-interface.md`; `BookLayout`, `Shaper` and `FontLibrary` in `07-fonts-shaping-layout.md`; `Renderer2D`, `GlyphAtlas`, `PageTurn` and the GL helpers in `08-rendering.md`. The headers (`App.h` included), `main.cpp`, `Settings.cpp`, `Themes.cpp` and `Platform.cpp` are reproduced verbatim in `ai/files` and are only referred to here.

---

## 1. Conventions used in this file

- **px** = framebuffer pixels (`fbW_ × fbH_`, from `SDL_GetWindowSizeInPixels`). **Window units** = SDL window coordinates (`winW_ × winH_`, from `SDL_GetWindowSize`); mouse events, `SDL_GetMouseState` and Dear ImGui use window units. The page geometry (`fontPx_`, `marginTop_`, `marginBottom_`, `columnX_`, `columnW_`) and the safe-area insets (`safeLeft_` …) are px; `topBarH_`, `bottomBarH_` and `toolbarHeight_` are window units.
- **s** = `displayScale_` (SDL's window display scale: 1 at 100 % on a desktop, the density on Android).
- **"any popup open"** = `ImGui::IsPopupOpen("", ImGuiPopupFlags_AnyPopupId | ImGuiPopupFlags_AnyPopupLevel)`.
- **"last page of view `v`"** = `v.pages[1]` if `v.count == 2 && !v.pages[1].empty()`, otherwise `v.pages[0]`.
- **"finish a running turn"** = `if (turning_) finishTurn();`.
- `requestRedraw()` without an argument means 3 frames (the default argument in `App.h`).
- `SDL_Log` lines are quoted with their exact printf formats; §24 lists all of them.
- Comparisons of setting strings (`settings_.columns`, `settings_.pageTurn`, panel names, flags) are exact and case-sensitive.
- Code blocks marked `cpp` are verbatim excerpts of `App.cpp` (comments mostly dropped); unmarked blocks are pseudo-code.

`main.cpp` (verbatim) drives the class through SDL's main callbacks: `SDL_AppInit` creates the `App` and returns `init()`'s result as `SDL_APP_CONTINUE`/`SDL_APP_FAILURE`; `SDL_AppIterate` → `iterate()`; `SDL_AppEvent` → `handleEvent()`; `SDL_AppQuit` → `shutdown()` then `delete`. `shutdown()` therefore also runs after a failed `init()` and must cope with a partly initialised object (§23).

## 2. File structure

Includes, in this order: `"app/App.h"`, `<imgui.h>`, `<imgui_impl_opengl3.h>`, `<imgui_impl_sdl3.h>`, `<imgui_internal.h>` (needed for `GImGui`, `ImGuiWindow`, `ImGui::GetInputTextState`, `ImGui::GetActiveID`), `<algorithm>`, `<cfloat>`, `<iterator>`, `<cmath>`, `<cstdlib>`, `<cstring>`, `<ctime>`, `<filesystem>`, `"core/BookLoader.h"`, `"core/FileUtil.h"`, `"core/ImageCodec.h"`, `"core/Unicode.h"`, `"platform/Platform.h"`. Everything is inside `namespace ll { ... }`.

Order of the code: an anonymous namespace with the helpers of §3; `App::App() = default;` and `App::~App() = default;`; `now`, `wake`, `showError`; then groups introduced by a banner comment — a line `// ` followed by 93 `-`, a line `// <Group>`, the dash line again:

| Banner | Functions, in order |
|---|---|
| `Setup` | `parseArgs`, `init`, `createWindow`, `applyMinimumWindowSize`, `loadFonts`, `availableFamilies`, `applyFontFamily`, `loadHyphenation`, `initImGui` |
| `Geometry, views, navigation` | `updateGeometry`, `setColumns`, `makeView`, `rebuildView`, `setViewStart`, `goNext`, `goPrev`, `goHome`, `goEnd`, `goToBlock`, `goToPercent`, `percentAt`, `currentPercent`, `chapterTitleAt`, `startTurn`, `finishTurn`, `followLink`, `runFind` |
| `Persistence` | `saveReadingPosition`, `saveSettingsNow`, `scheduleSave` |
| `Rendering` | `imageTexture`, `drawPage`, `viewPercent`, `drawWelcome`, `renderView`, `renderFrame`, `renderSignature`, `dropPageCache`, `fillPageCache`, `takeScreenshot` |
| `Input` | `setFontSize`, `zoomBy`, `setScreenBrightness`, `toggleFullscreen`, `applyScreenSaver`, `setTheme`, `refreshTheme`, `cycleTheme`, `checkAutoNight`, `onKeyDown`, `closeTopPanel`, `readingModeBlocked`, `returnToReading`, `handleTap`, `onMouseDown`, `pointOverUi`, `onFinger`, `onWheel`, `handleEvent` |
| `Main loop` | `pollAsync`, `updateCallbackRate`, `iterate`, `pushShotClickPhase`, `shutdown`, `openBook`, `restorePosition` |

## 3. File-local helpers (anonymous namespace)

### 3.1 The log file hook

Globals: `FILE* g_logFile = nullptr; SDL_LogOutputFunction g_defaultLog = nullptr; void* g_defaultLogData = nullptr;`

`void SDLCALL logOutput(void*, int category, SDL_LogPriority priority, const char* message)`:
1. If `g_logFile`: `std::fprintf(g_logFile, "%s\n", message)` and `std::fflush(g_logFile)` — only the message text, no category, priority or time stamp; flushed after every line.
2. If `g_defaultLog`: forward to it, `g_defaultLog(g_defaultLogData, category, priority, message)` (so messages still reach the debugger/console/logcat).

`void openLogFile(const std::string& path)`:
1. If `g_logFile` is open, `fclose` it and set it to null (on Android the process, and these globals, can outlive the app: a second start must neither leak the file nor chain the hook to itself).
2. Open `path` with mode `"w"` (truncate; text mode, so on Windows lines end in CR LF): Windows `_wfopen(pathFromUtf8(path).c_str(), L"w")`, elsewhere `std::fopen(path.c_str(), "w")`. A failed open leaves `g_logFile` null (messages then only go to the default output).
3. `SDL_GetLogOutputFunction(&current, &currentData)`; if `current != logOutput`, store `current`/`currentData` in `g_defaultLog`/`g_defaultLogData`.
4. `SDL_SetLogOutputFunction(logOutput, nullptr)`.

The hook is never removed and the file is never closed explicitly (the OS closes it at exit).

### 3.2 The on-screen keyboard hook

Dear ImGui's SDL3 backend starts text input with SDL's default properties, which on Android mean capitalised sentences and autocorrect. Lanternleaf starts text input itself, first, with plain-text properties (or a number pad for numeric fields); the backend's own IME callback then only positions and stops it.

```cpp
struct TextInputHook {
  void (*backend)(ImGuiContext*, ImGuiViewport*, ImGuiPlatformImeData*) = nullptr;
  SDL_Window* window = nullptr;
  SDL_PropertiesID text = 0;
  SDL_PropertiesID number = 0;
  SDL_PropertiesID active = 0;
};
TextInputHook g_textInput;
```

`void setImeData(ImGuiContext* ctx, ImGuiViewport* viewport, ImGuiPlatformImeData* data)` — installed as `ImGuiPlatformIO::Platform_SetImeDataFn` (§9):

```cpp
  TextInputHook& h = g_textInput;
  if (h.window && (data->WantVisible || data->WantTextInput)) {
    const ImGuiInputTextState* st = ImGui::GetInputTextState(ImGui::GetActiveID());
    const ImGuiInputTextFlags numeric = ImGuiInputTextFlags_CharsDecimal | ImGuiInputTextFlags_CharsScientific |
                                        ImGuiInputTextFlags_LocalizeDecimalPoint;  // the last: any InputScalar
    const bool number = st && (st->Flags & numeric);
    const SDL_PropertiesID want = number ? h.number : h.text;
    if (SDL_TextInputActive(h.window) && h.active != want) SDL_StopTextInput(h.window);
    if (!SDL_TextInputActive(h.window)) {
      SDL_StartTextInputWithProperties(h.window, want);
      h.active = want;
    }
  }
  if (h.backend) h.backend(ctx, viewport, data);
```

The two property sets are created in `initImGui` (§9).

### 3.3 Easing

```cpp
float easeInOut(float t) {
  t = std::clamp(t, 0.0f, 1.0f);
  return t < 0.5f ? 4 * t * t * t : 1 - std::pow(-2 * t + 2, 3.0f) / 2;
}
```

Cubic ease-in-out; used by the slide and fade page turns (§13.4).

## 4. Small members

- `now()`: seconds since start-up as `double`: `(SDL_GetPerformanceCounter() - startCounter_) / SDL_GetPerformanceFrequency()` (both converted to `double` before dividing).
- `wake()`: `SDL_Event e; SDL_zero(e); e.type = wakeEvent_; SDL_PushEvent(&e);` — callable from any thread (timers, the search worker, dialog callbacks).
- `showError(msg)`: `SDL_Log("%s", msg.c_str())`, `messages_.push_back(msg)`, `requestRedraw()`. (The messages box is drawn by the UI.)

## 5. Command line: `parseArgs(argc, argv, openPath)`

Loops `i = 1 … argc-1`; `a = argv[i] ? argv[i] : ""`. A local `next()` returns `argv[++i]` if `i + 1 < argc`, else `""` (it consumes the following argument whatever it looks like, even one starting with `-`). Always returns `true` (`init` ignores the result). Flags may come in any order; a flag given twice keeps the last value except the repeatable ones.

| Argument | Value | Effect |
|---|---|---|
| `--settings-dir` | `DIR` | `prefDir_ = DIR`; if non-empty and not ending in `/` or `\`, a `/` is appended. An empty value leaves `prefDir_` empty, so `init` falls back to the platform folder. |
| `--screenshot` | `FILE` | `shot_.enabled = true; shot_.out = FILE` (PNG path written at the end). |
| `--size` | `WxH` | Only if the value contains `x`: `shot_.width = max(200, atoi(part before x))`, `shot_.height = max(200, atoi(part after x))`. Default 1280 × 820. (`createWindow` then still applies its 320 × 240 floor.) |
| `--frames` | `N` | `shot_.frames = max(1, atoi(N))`. Default 4. |
| `--goto` | `P` | `shot_.gotoPercent = atof(P)` — a percentage 0–100. Default −1 (none). |
| `--next` | `N` | `shot_.nextPages = atoi(N)`. Default 0. |
| `--turn` | `T` | `shot_.turnT = (float)atof(T)` — a frozen turn position 0–1. Default −1 (none). |
| `--panel` | `NAME` | `shot_.panel = NAME` (values in §6.2). |
| `--search` | `QUERY` | `shot_.search = QUERY`. |
| `--search-root` | `DIR` | appended to `shot_.searchRoots` (repeatable). |
| `--search-content` | — | `shot_.searchContent = true`. |
| `--find` | `PHRASE` | `shot_.find = PHRASE`. |
| `--click` | `X,Y` | Only if the value contains `,`: appends `(float)atof(X), (float)atof(Y)` to `shot_.clicks` (window units; repeatable). |
| `--allow-save` | — | `shotAllowSave_ = true`. |
| `--find-go` | — | `shotFindGo_ = true`. |
| `--theme`, `--font-size`, `--columns`, `--page-turn`, `--font` | `VALUE` | `overrides_.emplace_back(flag, VALUE)`; applied after the settings file is loaded (§6.1 step 11). |
| any other non-empty argument not starting with `-` | — | `openPath = a` (the last one wins). |
| any other argument starting with `-` | — | ignored; it consumes nothing, so a value after an unknown flag becomes a positional argument (a book path). |

Outside screenshot mode only `--settings-dir`, the five overrides and the book path have an effect; everything else is parsed but used only when `--screenshot` was given. In a normal run the overrides become part of `settings_` and are written with the next save (no save is scheduled for them; opening a book, for example, saves at once).

## 6. Start-up: `init(argc, argv)`

### 6.1 Steps, in this exact order

1. `startCounter_ = SDL_GetPerformanceCounter()`.
2. `std::string openPath; parseArgs(argc, argv, openPath);`
3. `touchFirst_ = platform::isTouchFirst()`.
4. `SDL_SetAppMetadata(kAppName, kAppVersion, "app.lanternleaf.reader")` (`kAppName` is `"Lanternleaf"`).
5. Hints: `SDL_SetHint(SDL_HINT_WINDOWS_INTRESOURCE_ICON, "1")`, `SDL_SetHint(SDL_HINT_WINDOWS_INTRESOURCE_ICON_SMALL, "1")` (the window icons come from resource id 1 of the executable), `SDL_SetHint(SDL_HINT_ANDROID_TRAP_BACK_BUTTON, "1")` (Android Back arrives as `SDLK_AC_BACK` and the app decides what it does).
6. `SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)`; on failure `SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, kAppName, SDL_GetError(), nullptr)` and `return false`.
7. `wakeEvent_ = SDL_RegisterEvents(1)`.
8. If `prefDir_` is empty: `prefDir_ = platform::prefDir()` (`SDL_GetPrefPath("", "Lanternleaf")`, with a trailing separator). If `prefDir_` is non-empty: `std::filesystem::create_directories(pathFromUtf8(prefDir_), ec)` (error ignored) and `openLogFile(prefDir_ + "lanternleaf.log")`. (If it is still empty, no log file is opened and the files below are relative names.)
9. `settingsFile_ = prefDir_ + "settings.json"`, `metaCacheFile_ = prefDir_ + "library-cache.json"`, `imguiIni_ = prefDir_ + "imgui.ini"`.
10. `settings_.load(settingsFile_)` (result ignored: a missing or broken file leaves the defaults of `Settings.h`).
11. Apply `overrides_` in command-line order:
    - `--theme` → `settings_.theme = value` (stored as given; an unknown id displays as theme 0 "day" through `themeIndex`, and stays stored unnormalised until something calls `setTheme`);
    - `--font-size` → `settings_.fontSize = std::clamp((float)std::atof(value), 8.0f, 120.0f)`;
    - `--columns` → `settings_.columns = value` (anything other than `"2"` or `"auto"` behaves as one page);
    - `--page-turn` → `settings_.pageTurn = value` (`"none"`, `"slide"`, `"fade"`; anything else animates as the curl);
    - `--font` → `settings_.fontFamily = value` (an unavailable family falls back to PT Serif in `loadFonts`).
12. If `settings_.searchRoots` is empty: `settings_.searchRoots = platform::defaultSearchRoots()`.
13. `query_ = settings_.lastQuery`.
14. `metaCache_.load(metaCacheFile_)`.
15. `search_ = std::make_unique<LibrarySearch>(metaCache_)`; `search_->setNotify([this] { wake(); })`.
16. `refreshTheme()` (so `theme_` is valid before anything is drawn or styled).
17. `if (!createWindow()) return false;` (§7.1).
18. `if (!loadFonts())`: `SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, kAppName, "The bundled fonts could not be loaded. Is the 'assets' folder next to the program?", window_)` and `return false`.
19. `loadHyphenation()`.
20. `layout_ = std::make_unique<BookLayout>(*bookShaper_, &hyph_)`.
21. `std::string err; if (!r2d_.init(&err) || !turn_.init(&err))` → message box `"OpenGL initialisation failed:\n" + err` (parent `window_`) and `return false` (`turn_.init` is not attempted when `r2d_.init` fails).
22. `glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxTextureSize_)` (member default 2048).
23. `initImGui()` (§9).
24. `updateGeometry()` (§11.1).
25. `SDL_Log("Lanternleaf %s, OpenGL %s", kAppVersion, gl::glVersionString())`.
26. Book: if `openPath` is non-empty → `openBook(openPath)`; otherwise, if `settings_.lastBook` is non-empty and `fileExists(settings_.lastBook)` → `openBook(settings_.lastBook)`. (A failing command-line book does not fall back to the last book; its error message is shown.)
27. If `!doc_`: `showLibrary_ = true; libraryTab_ = settings_.recent.empty() ? 1 : 0;` (the Find tab for a first start, the Recent tab otherwise).
28. `storagePromptOpen_ = touchFirst_ && !shot_.enabled && !settings_.storagePromptDismissed && !storageAccess();`
29. `checkAutoNight(true)` (§19).
30. `minuteTimer_ = SDL_AddTimer(30000, cb, this)` where `cb` calls `wake()` and returns `interval` (repeats every 30 000 ms).
31. If `shot_.enabled`: the screenshot set-up of §6.2.
32. `requestRedraw()`; `return true`.

Consequence of the order: the settings file is read before the command-line overrides, and `checkAutoNight(true)` runs after them — with `autoNight` on in the settings file, the clock's day/night theme replaces a `--theme` value.

### 6.2 Screenshot set-up (end of `init`, only when `shot_.enabled`)

```cpp
    const std::string savedTurn = settings_.pageTurn;
    settings_.pageTurn = "none";
    if (doc_ && shot_.gotoPercent >= 0) goToPercent(shot_.gotoPercent / 100.0);
    for (int k = 0; k < shot_.nextPages; ++k) goNext();
    settings_.pageTurn = savedTurn;
    if (doc_ && shot_.turnT >= 0) {
      if (settings_.pageTurn != "slide" && settings_.pageTurn != "fade") settings_.pageTurn = "curl";
      goNext();
      turnFrozen_ = true;
      turnT_ = shot_.turnT;
    }
```

So `--goto` and `--next` move without animation (each `--next` step is an instant turn drawn on the spot, counted in `instantDrawn_`); `--turn T` starts a forward turn to the next view and freezes it at `turnT_ = T` (style slide or fade if that is the page-turn setting, the curl otherwise — `settings_.pageTurn` stays `"curl"` afterwards). At the end of the book no turn starts but `turnFrozen_`/`turnT_` are still set (harmless: nothing is turning).

Then, from `shot_.panel` (each test independent, the flags are set directly, not through `showPanel`):

| `--panel` | Effect |
|---|---|
| `toc` | `showToc_ = true` |
| `settings` | `showSettings_ = true` |
| `help` | `showHelp_ = true` |
| `goto` | `showGoto_ = true` |
| `library` | `showLibrary_ = true; libraryTab_ = 0` |
| `toolbar` | `toolbarPinned_ = true` |
| `browser` | `openFileBrowser(false)` |
| `folders` | `openFileBrowser(true)` |
| `about` | `showAbout_ = true` |
| `storage` | `storagePromptOpen_ = true` |
| anything else | nothing |

(Without a book, step 27 has already opened the library, so e.g. `--panel settings` shows both. With a book, any panel or `--panel toolbar` makes the toolbar and status bar appear in the first frame; `updateBars` then finishes a running turn, so `--turn` combined with them shows the next page, not a frozen turn.)

Then, if `!shot_.search.empty() || !shot_.searchRoots.empty()`: `query_ = shot_.search`; if `shot_.searchRoots` is non-empty, `settings_.searchRoots = shot_.searchRoots`; `settings_.searchByContent = shot_.searchContent`; `showLibrary_ = true; libraryTab_ = 1;` `startLibrarySearch()`.

Then, if `!shot_.find.empty() && doc_`: `findQuery_ = shot_.find; runFind();` then, if `shotFindGo_ && !findHits_.empty()`: highlight the first hit (`highlight_ = {f.block, f.offset, f.offset + f.length}`) and `goToBlock(f.block, f.offset)`; otherwise `showLibrary_ = true; libraryTab_ = 2;` (the find results list).

## 7. Window and GL context

### 7.1 `createWindow()`

1. GL attributes, with `SDL_GL_SetAttribute`, before the window is created:
   - GLES build (`LL_GLES` defined, i.e. Android): `SDL_GL_CONTEXT_PROFILE_MASK = SDL_GL_CONTEXT_PROFILE_ES`, `SDL_GL_CONTEXT_MAJOR_VERSION = 3`, `SDL_GL_CONTEXT_MINOR_VERSION = 0`.
   - Desktop: `SDL_GL_CONTEXT_PROFILE_MASK = SDL_GL_CONTEXT_PROFILE_CORE`, major 4, minor 1, `SDL_GL_CONTEXT_FLAGS = SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG`.
   - Both: `SDL_GL_DOUBLEBUFFER = 1`, `SDL_GL_DEPTH_SIZE = 24`, `SDL_GL_STENCIL_SIZE = 0`. No other attribute is set: no multisampling (MSAA) attributes, no colour sizes, no sRGB, no debug flag.
2. Flags: `SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY`. Size `w = settings_.winW, h = settings_.winH` (defaults 1180 × 820). In screenshot mode: add `SDL_WINDOW_HIDDEN` unless `touchFirst_` (a phone always shows its one window), and `w, h = shot_.width, shot_.height`. Otherwise, if `settings_.maximized && !touchFirst_`, add `SDL_WINDOW_MAXIMIZED`.
3. `window_ = SDL_CreateWindow(kAppName, std::max(w, 320), std::max(h, 240), flags)` — the title is `"Lanternleaf"`, the position whatever SDL chooses. Failure: message box with `SDL_GetError()` (no parent), `return false`.
4. Saved position: only if `!shot_.enabled && !touchFirst_ && settings_.winX != INT_MIN && !settings_.maximized`. The position is accepted if, for any display from `SDL_GetDisplays`, `SDL_GetDisplayUsableBounds` succeeds and the point `(winX + 60, winY + 20)` lies inside it: `winX + 60 >= r.x && winX + 60 < r.x + r.w && winY + 20 >= r.y && winY + 20 < r.y + r.h`. Then `SDL_SetWindowPosition(window_, winX, winY)`; otherwise SDL's position stays. The display list is freed with `SDL_free`. The saved size is not otherwise validated (only the 320 × 240 floor here and the minimum size below).
5. `gl_ = SDL_GL_CreateContext(window_)`; failure: message box `std::string("OpenGL 4.1 is required: ") + SDL_GetError()` (parent `window_`; the same text on GLES), `return false`.
6. `SDL_GL_MakeCurrent(window_, gl_)`; `SDL_GL_SetSwapInterval(1)` (vsync; result ignored).
7. Desktop only: `gladLoadGLLoader(reinterpret_cast<GLADloadproc>(SDL_GL_GetProcAddress))`; failure: message box `"Could not load OpenGL functions."` (parent `window_`), `return false`.
8. `applyMinimumWindowSize()`.
9. If `settings_.fullscreen && !shot_.enabled`: `SDL_SetWindowFullscreen(window_, true)` (on Android `fullscreen` defaults to true: immersive).
10. If `settings_.screenBrightness >= 0 && !shot_.enabled && platform::canSetScreenBrightness()`: `platform::setScreenBrightness(level * level)` with `level = settings_.screenBrightness`.
11. `return true`.

### 7.2 `applyMinimumWindowSize()` — 10 % of the monitor

Returns at once if `!window_ || touchFirst_ || shot_.enabled` (screenshot runs keep the exact size asked for; phones have one full-screen window). Otherwise:

```cpp
  const SDL_DisplayID display = SDL_GetDisplayForWindow(window_);
  SDL_Rect r;
  if (!display || !SDL_GetDisplayBounds(display, &r) || r.w <= 0 || r.h <= 0) return;
  const int minW = std::max(1, static_cast<int>(std::lround(r.w * 0.1)));
  const int minH = std::max(1, static_cast<int>(std::lround(r.h * 0.1)));
  int curW = 0, curH = 0;
  SDL_GetWindowMinimumSize(window_, &curW, &curH);
  if (curW == minW && curH == minH) return;
  SDL_SetWindowMinimumSize(window_, minW, minH);
  SDL_Log("minimum window size %dx%d (10%% of the display, %dx%d)", minW, minH, r.w, r.h);
```

The full display bounds (not the usable bounds) are used. Called from `createWindow` (the first call always logs, since the initial minimum is 0 × 0) and again on `SDL_EVENT_WINDOW_DISPLAY_CHANGED` (moved to another monitor) and `SDL_EVENT_DISPLAY_CURRENT_MODE_CHANGED` (its resolution changed); it logs only when the minimum actually changes. Example line: `minimum window size 192x108 (10% of the display, 1920x1080)`.

## 8. Fonts and hyphenation

### 8.1 `loadFonts()`

1. A local `loadBundled(file)`: `platform::loadAsset(std::string("fonts/") + file, data)`; on failure return −1; else `return fonts_.addFromMemory(std::move(data), file)` (the face is named after its file name).
2. Two families: `serif.name = "PT Serif"` with files `{"PTSerif-Regular.ttf", "PTSerif-Italic.ttf", "PTSerif-Bold.ttf", "PTSerif-BoldItalic.ttf"}` and `sans.name = "PT Sans"` with `{"PTSans-Regular.ttf", "PTSans-Italic.ttf", "PTSans-Bold.ttf", "PTSans-BoldItalic.ttf"}` — index = style (`(bold ? 2 : 0) | (italic ? 1 : 0)`). They are loaded interleaved: `for s in 0..3 { serif.faces[s] = loadBundled(serifFiles[s]); sans.faces[s] = loadBundled(sansFiles[s]); }` (so with every file present the face ids are serif 0, 2, 4, 6 and sans 1, 3, 5, 7).
3. `if (!serif.valid() || !sans.valid()) return false;` (only the regular face is required; missing styles fall back inside `FontFamily::face`).
4. `families_["PT Serif"] = serif; families_["PT Sans"] = sans;`
5. Fallback faces: for each path of `platform::fallbackFontFiles()` (in its order), `id = fonts_.addFromFile(path)`; if `id >= 0`, append to `fallbackFaces_`.
6. `bookShaper_` and `uiShaper_` = `std::make_unique<Shaper>(fonts_)`; both `setFallbacks(fallbackFaces_)`; `uiShaper_->setFamily(sans)` (the UI shaper — used for the welcome screen's smaller lines — is always PT Sans).
7. `if (!applyFontFamily(settings_.fontFamily)) applyFontFamily("PT Serif");` (so `settings_.fontFamily` becomes `"PT Serif"` when the saved family is unavailable).
8. `platform::loadAsset("fonts/PTSans-Regular.ttf", uiFontData_)` — a second copy of the PT Sans bytes for Dear ImGui (result ignored; an empty buffer means ImGui keeps its default font).
9. `return true`.

### 8.2 `availableFamilies()`

`{"PT Serif", "PT Sans"}` followed by the `family` of every entry of `platform::readingFonts()`, in that order (the Typeface list of the settings panel).

### 8.3 `applyFontFamily(family)`

1. Look `family` up in `families_`.
2. If absent: scan `platform::readingFonts()` for the first entry whose `family` equals it; build a `FontFamily f` with `f.name = family` and, for each style `s` with a non-empty `sf.files[s]`, `f.faces[s] = fonts_.addFromFile(sf.files[s], sf.faceIndex[s])`; if `f.valid()`, insert it into `families_`. Stop scanning after that first match, valid or not.
3. Still absent → `return false` (nothing changes).
4. `bookShaper_->setFamily(it->second)`; `settings_.fontFamily = family`; `++fontGeneration_`.
5. If `layout_` exists (not during `loadFonts`): finish a running turn, `layout_->invalidate()`, `updateGeometry()`, `viewValid_ = false`, `requestRedraw()`. (The view is rebuilt from the anchor on the next frame, so the reading position is kept.)
6. `return true`. It does not schedule a save (its caller in the settings panel does).

### 8.4 `loadHyphenation()`

A local `load(rel)` reads the asset with `platform::loadAsset` into a `std::string` (empty if missing). Then:

- `hyph_.english().load(load("hyphenation/hyph-en-us.pat.txt"), load("hyphenation/hyph-en-us.hyp.txt"), 2, 3)` — left min 2, right min 3; if it returns false: `SDL_Log("English hyphenation patterns not found")`.
- `hyph_.russian().load(load("hyphenation/hyph-ru.pat.txt"), load("hyphenation/hyph-ru.hyp.txt"), 2, 2)` — left min 2, right min 2; if false: `SDL_Log("Russian hyphenation patterns not found")`.

## 9. Dear ImGui: `initImGui()`

1. `IMGUI_CHECKVERSION(); ImGui::CreateContext();`
2. `io.IniFilename = shot_.enabled ? nullptr : imguiIni_.c_str();` — window positions and sizes persist in `imgui.ini` in the settings folder (loaded and saved by ImGui itself); screenshot runs neither read nor write it.
3. `io.ConfigWindowsMoveFromTitleBarOnly = true` (panels move only by their title bar; dragging inside scrolls or works the controls).
4. `ImGui_ImplSDL3_InitForOpenGL(window_, gl_)`.
5. Text-input hook (§3.2): `h.backend = ImGui::GetPlatformIO().Platform_SetImeDataFn` (the backend's function), `h.window = window_`; the two property sets are filled with `SDL_SetNumberProperty` / `SDL_SetBooleanProperty`:
   - `h.text = SDL_CreateProperties()` with `SDL_PROP_TEXTINPUT_TYPE_NUMBER = SDL_TEXTINPUT_TYPE_TEXT`, `SDL_PROP_TEXTINPUT_CAPITALIZATION_NUMBER = SDL_CAPITALIZE_NONE`, `SDL_PROP_TEXTINPUT_AUTOCORRECT_BOOLEAN = false`, `SDL_PROP_TEXTINPUT_MULTILINE_BOOLEAN = false` (single line: keyboards still autocorrect "multi-line" fields, SDL's default, despite the autocorrect flag);
   - `h.number = SDL_CreateProperties()` with `SDL_PROP_TEXTINPUT_TYPE_NUMBER = SDL_TEXTINPUT_TYPE_NUMBER`, `SDL_PROP_TEXTINPUT_CAPITALIZATION_NUMBER = SDL_CAPITALIZE_NONE`, `SDL_PROP_TEXTINPUT_AUTOCORRECT_BOOLEAN = false`, `SDL_PROP_TEXTINPUT_MULTILINE_BOOLEAN = false`;
   - `pio.Platform_SetImeDataFn = setImeData`.
6. `ImGui_ImplOpenGL3_Init("#version 300 es")` on GLES, `ImGui_ImplOpenGL3_Init("#version 410 core")` on the desktop.
7. If `uiFontData_` is non-empty: `ImFontConfig cfg; cfg.FontDataOwnedByAtlas = false;` `uiFont_ = io.Fonts->AddFontFromMemoryTTF(uiFontData_.data(), (int)uiFontData_.size(), 17.0f, &cfg)` — PT Sans Regular at 17 px, the first (default) font of the atlas; the bytes stay owned by `uiFontData_`. (The effective UI size and DPI scaling come from the style: `applyImGuiStyle` sets `FontSizeBase` and `FontScaleDpi`, see `10-user-interface.md`.)
8. `displayScale_ = SDL_GetWindowDisplayScale(window_)`, replaced by 1 if `<= 0`.
9. `applyImGuiStyle()`.

ImGui's keyboard navigation flags are not enabled.

## 10. Opening a book

### 10.1 `openBook(path)` → bool

1. `t0 = now()`; `auto doc = std::make_unique<Document>(); std::string err;`
2. `if (!loadBook(path, *doc, &err))`: `showError("Could not open \"" + fileNameOf(path) + "\": " + err)` and `return false`. The book already open (if any) stays as it was.
3. `tParsed = now()`.
4. If a book is open: `saveReadingPosition()` — the old book's position goes into its recent entry (it still uses the old `bookPath_`/`bookFingerprint_`).
5. `turning_ = false` — a running animation is dropped, not finished (the old book's anchor is not advanced).
6. Destroy every texture in `images_` and clear the map; `highlight_ = {}`; `findHits_.clear()`; `showFootnote_ = false`.
7. `doc_ = std::move(doc); bookPath_ = path; bookFingerprint_ = bookFingerprint(path);`
8. `if (bookShaper_->cacheSize() > 150000) bookShaper_->clear();` — shaped words are cached across books; this keeps memory bounded on long sessions.
9. `layout_->setDocument(doc_.get()); dropPageCache();`
10. `RecentBook& rb = settings_.touchRecent(path, bookFingerprint_);` (found by path, else by fingerprint — a renamed or moved file keeps its entry — moved or created at the front of the list, `lastOpened` set, list capped at 200; see `Settings.cpp`). `rb.title = doc_->meta.title; rb.authors = doc_->meta.authorsJoined();`
11. `anchorBlock_ = 0; anchorOffset_ = 0;` `nBlocks = (int)doc_->blocks.size()`; `restorable = rb.block > 0 || rb.offset > 0`; keep `savedBlock = rb.block`, `savedOffset = rb.offset`, `savedCount = rb.blockCount`, `savedPercent = rb.percent`; then `rb.blockCount = nBlocks; settings_.lastBook = path;`
12. `updateGeometry()`.
13. `if (restorable) restorePosition(savedBlock, savedOffset, savedCount, savedPercent); else rebuildView();`
14. `SDL_Log("opened %s: %s, %s, %d blocks, %llu chars, parse %.0f ms, first page %.0f ms", path.c_str(), doc_->meta.format.c_str(), doc_->meta.encoding.c_str(), nBlocks, (unsigned long long)doc_->totalChars, (tParsed - t0) * 1000.0, (now() - tParsed) * 1000.0)`.
15. Window title: `title = doc_->meta.title`; if `authorsJoined()` is non-empty, `title += " \xE2\x80\x94 " + authors` (space, U+2014 EM DASH, space); then `title += " \xC2\xB7 Lanternleaf"` (space, U+00B7 MIDDLE DOT, space, `Lanternleaf`); `SDL_SetWindowTitle(window_, title.c_str())`. Example: `Anna Karenina — Leo Tolstoy · Lanternleaf`; with an empty title it starts with the separator (`" · Lanternleaf"` or `" — Author · Lanternleaf"`).
16. `showLibrary_ = false; browser_.open = false;` (other panels stay open).
17. `applyScreenSaver(); saveSettingsNow(); requestRedraw(); return true;`

Not reset by `openBook`: `findQuery_`, `messages_`, `statusEdit_`, `toolbarPinned_`, the other panels. Re-opening the book that is already open keeps its place: step 4 stores the current position in its entry, which step 10 finds again.

### 10.2 `restorePosition(block, offset, blockCount, percent)`

```cpp
  if (!doc_) return;
  const int nBlocks = static_cast<int>(doc_->blocks.size());
  if (turning_) finishTurn();
  if ((blockCount == 0 || blockCount == nBlocks) && block >= 0 && block < nBlocks) {
    anchorBlock_ = block;
    anchorOffset_ = std::min<uint32_t>(offset, static_cast<uint32_t>(doc_->blocks[static_cast<size_t>(block)].text.size()));
    rebuildView();
  } else {
    goToPercent(percent);  // the book was parsed differently (another file version or app version)
  }
```

A stored block count of 0 (unknown) is trusted. The exact position is the byte offset inside the block, so it survives any change of font, size, margins or window.

## 11. Page geometry

### 11.1 `updateGeometry()`

Computes, in px, the font size, the margins, the number of pages on screen and their columns, and hands the layout parameters to `BookLayout`.

```cpp
  SDL_GetWindowSizeInPixels(window_, &fbW_, &fbH_);
  SDL_GetWindowSize(window_, &winW_, &winH_);
  float scale = SDL_GetWindowDisplayScale(window_);
  if (scale <= 0) scale = 1.0f;
  displayScale_ = scale;
  if (fbW_ <= 0 || fbH_ <= 0) return;

  safeLeft_ = safeTop_ = safeRight_ = safeBottom_ = 0;
  SDL_Rect safe;
  if (winW_ > 0 && winH_ > 0 && SDL_GetWindowSafeArea(window_, &safe) && safe.w > 0 && safe.h > 0) {
    const float sx = static_cast<float>(fbW_) / static_cast<float>(winW_);
    const float sy = static_cast<float>(fbH_) / static_cast<float>(winH_);
    safeLeft_ = std::max(0.0f, safe.x * sx);
    safeTop_ = std::max(0.0f, safe.y * sy);
    safeRight_ = std::max(0.0f, (winW_ - safe.x - safe.w) * sx);
    safeBottom_ = std::max(0.0f, (winH_ - safe.y - safe.h) * sy);
  }

  fontPx_ = std::round(settings_.fontSize * scale * 4.0f) / 4.0f;
  const float edge = std::max(18.0f * scale, fbH_ * 0.035f);
  marginTop_ = std::round(std::max(edge, safeTop_ + 8.0f * scale));
  marginBottom_ = std::round(std::max(edge, safeBottom_ + 8.0f * scale));
  if (barsShown_ && winH_ > 0) {
    const float ky = static_cast<float>(fbH_) / static_cast<float>(winH_);  // window units -> pixels
    const float gap = std::round(std::max(10.0f * scale, fontPx_ * 0.6f));
    marginTop_ = std::max(marginTop_, std::round(safeTop_ + topBarH_ * ky + gap));
    marginBottom_ = std::max(marginBottom_, std::round(safeBottom_ + bottomBarH_ * ky + gap));
  }
  const float marginX = std::round(std::max({22.0f * scale, fbW_ * settings_.margin,
                                             std::max(safeLeft_, safeRight_) + 10.0f * scale}));
  const float avail = std::max(80.0f, fbW_ - 2 * marginX);
  float gutter = std::round(std::max(3.0f * fontPx_, marginX * 1.5f));
  bool two = false;
  twoPagesFit_ = true;
  if (settings_.columns == "2") {
    if ((avail - gutter) / 2 < 12.0f * fontPx_) gutter = std::round(std::max(1.6f * fontPx_, marginX));
    two = (avail - gutter) / 2 >= 8.0f * fontPx_;
    twoPagesFit_ = two;
  } else if (settings_.columns == "auto") {
    const float minColumnEm = touchFirst_ ? 18.0f : 22.0f;
    two = fbW_ > fbH_ * 1.2f && (avail - gutter) / 2 >= minColumnEm * fontPx_;
  }
  columns_ = two ? 2 : 1;
  if (two) {
    columnW_ = std::floor((avail - gutter) / 2);
    columnX_[0] = marginX;
    columnX_[1] = marginX + columnW_ + gutter;
  } else {
    columnW_ = std::floor(std::min(avail, settings_.maxLineWidth * fontPx_));
    columnX_[0] = std::round((fbW_ - columnW_) * 0.5f);
    columnX_[1] = columnX_[0];
  }
```

Then a `LayoutParams p` with `fontSize = fontPx_`, `lineSpacing = settings_.lineSpacing`, `pageWidth = columnW_`, `pageHeight = std::max(fontPx_ * 3, std::floor(fbH_ - marginTop_ - marginBottom_))`, `paragraphIndent`, `paragraphSpacing`, `justify`, `hyphenate` from the settings, `fontGeneration = fontGeneration_`. If `layout_` exists and `!(p == layout_->params())`: `layout_->setParams(p); viewValid_ = false;`. If `layout_` exists and `view_.count != columns_`: `viewValid_ = false`. Finally, always (after the early return), `++layoutGeneration_` — views rendered ahead are out of date.

In words:
- **Font**: `settings_.fontSize` (logical px; dp on phones) × display scale, rounded to a quarter pixel.
- **Top and bottom margins**: at least 18 s and 3.5 % of the framebuffer height, and at least the safe-area inset + 8 s. While the toolbar and status bar show (`barsShown_`), the page lies between them: at least inset + bar height (window units × `fbH_/winH_`) + a gap of `round(max(10 s, 0.6 em))`. Hidden, the text has the whole screen.
- **Side margin** `marginX`: the largest of 22 s, `settings_.margin` × width (default 6 %) and the larger side inset + 10 s — the same on both sides.
- **Gutter** (the spine gap between two pages): `round(max(3 em, 1.5 × marginX))`.
- **`"2"` (book mode, as asked for)**: when a page would be narrower than 12 em the gutter shrinks to `round(max(1.6 em, marginX))`; each page may be as narrow as 8 em (about 18 characters a line, readable with hyphenation) before one page is shown instead; `twoPagesFit_` records whether two fit.
- **`"auto"`**: two pages only in landscape (`fbW_ > 1.2 fbH_`) and when each page gets at least 22 em (18 em on touch devices — a phone turned sideways has short, very wide pages) with the normal gutter.
- **anything else** (`"1"` or an unknown value): one page, at most `maxLineWidth` em wide (default 40 em), centred.
- **Page height**: the space between the margins, at least 3 em.
- When only the page height changes (the bars came or went), `BookLayout::setParams` keeps the line breaks and keeps the page count of the previous height for when it comes back (`07-fonts-shaping-layout.md`); App.cpp just compares the whole parameter set and invalidates the view.

`updateGeometry` neither finishes a turn nor rebuilds the view: callers finish a running turn where needed, and `iterate` rebuilds an invalid view from the anchor. Callers: `init`, `openBook`, `applyFontFamily`, `setColumns`, `setFontSize`, `handleEvent` (size and scale changes), and in AppUi.cpp `updateBars` and the settings panel.

### 11.2 `setColumns(mode)`

```cpp
  if (turning_) finishTurn();
  settings_.columns = mode;
  updateGeometry();
  if (mode == "2" && !twoPagesFit_) {
    showToast("Two pages need a wider screen: turn the device sideways or make the text smaller.");
  }
  scheduleSave();
  requestRedraw();
```

The toast uses the default 5 s. The `B` key calls `setColumns(columns_ == 2 ? "1" : "2")` — it decides by what is on screen, so in `"auto"` with two pages shown it chooses `"1"`, and with `"2"` asked for but not fitting it asks for `"2"` again (and shows the toast again).

## 12. Views and navigation

The reading position is the **anchor** `anchorBlock_`/`anchorOffset_` (block index and byte offset in `Block::text`). `viewStart_` is the first line on screen, `view_` the one or two pages shown, `viewValid_` whether `view_` matches the current layout. Relayouts invalidate the view and it is rebuilt from the anchor (so the position is kept); page turns and jumps move the anchor to the new view's start.

- **`makeView(start)`**: `View v; v.count = columns_; v.pages[0] = layout_->pageFrom(start); if (columns_ == 2) v.pages[1] = layout_->pageFrom(v.pages[0].end); return v;`
- **`rebuildView()`**:
  ```cpp
  if (!doc_ || !layout_) return;
  viewStart_ = layout_->posForOffset(anchorBlock_, anchorOffset_);
  view_ = makeView(viewStart_);
  if (view_.pages[0].empty() && layout_->blockCount() > 0) {
    viewStart_ = layout_->pageStartBefore(layout_->endPos());
    view_ = makeView(viewStart_);
  }
  viewValid_ = true;
  layout_->trimCache(viewStart_.block);
  requestRedraw();
  ```
  It does not move the anchor (also not when it falls back to the last page) and does not schedule a save.
- **`setViewStart(p, updateAnchor)`**: `viewStart_ = layout_->normalize(p); view_ = makeView(viewStart_); viewValid_ = true;` if `updateAnchor`: `anchorBlock_ = viewStart_.block; anchorOffset_ = layout_->offsetOf(viewStart_);` then `layout_->trimCache(viewStart_.block); scheduleSave(); requestRedraw();`. Every caller passes `true`.
- **`goNext()`**: `if (!doc_ || !viewValid_) return;` finish a running turn; `last` = last page of `view_`; `if (layout_->isEnd(last.end)) return;` `startTurn(true, last.end)`. Pressing "next" during an animation completes it at once and starts the next turn from there.
- **`goPrev()`**: `if (!doc_ || !viewValid_) return;` finish a running turn; `first = layout_->normalize(LinePos{0, 0}); if (viewStart_ <= first) return;` `target = layout_->pageStartBefore(viewStart_); if (view_.count == 2 && target > first) target = layout_->pageStartBefore(target);` `startTurn(false, target)`.
- **`goHome()`**: `if (!doc_) return; goToBlock(0, 0);` — no animation.
- **`goEnd()`**: `if (!doc_) return;` finish a running turn; `target = layout_->pageStartBefore(layout_->endPos())`; if `columns_ == 2`: `before = layout_->pageStartBefore(target); if (before < target) target = before;` `setViewStart(target, true)` — no animation; a spread shows the last two pages.
- **`goToBlock(block, offset)`**: `if (!doc_) return;` finish a running turn; `anchorBlock_ = std::clamp(block, 0, (int)doc_->blocks.size() - 1); anchorOffset_ = offset; rebuildView(); scheduleSave();` — no animation. Used by Home, the contents, footnotes' "Go to the note", in-book links, find hits and `goToPercent`.
- **`goToPercent(pct)`** — `pct` is a fraction:
  ```cpp
  if (!doc_ || doc_->blocks.empty()) return;
  pct = std::clamp(pct, 0.0, 1.0);
  if (pct >= 0.9995) {
    goEnd();
    return;
  }
  const uint64_t target = static_cast<uint64_t>(pct * static_cast<double>(doc_->totalChars));
  const auto& blocks = doc_->blocks;
  auto it = std::upper_bound(blocks.begin(), blocks.end(), target,
                             [](uint64_t t, const Block& b) { return t < b.charStart; });
  const int bi = std::max(0, static_cast<int>(it - blocks.begin()) - 1);
  const Block& b = blocks[static_cast<size_t>(bi)];
  uint64_t chars = target > b.charStart ? target - b.charStart : 0;
  size_t off = 0;
  while (chars > 0 && off < b.text.size()) {
    off = utf8NextPos(b.text, off);
    --chars;
  }
  goToBlock(bi, static_cast<uint32_t>(off));
  ```
  (Positions are measured in code points — `Block::charStart`, `Document::totalChars`.)
- **`percentAt(p)`**: 0 if `!doc_ || !layout_ || totalChars == 0 || blocks.empty()`; 1.0 if `p.block >= blocks.size()`; otherwise, with `b = blocks[max(0, p.block)]` and `off = min(layout_->offsetOf(p), b.text.size())`: `clamp((b.charStart + utf8Length(b.text[0, off))) / totalChars, 0, 1)`.
- **`currentPercent()`**: 0 if `!doc_ || totalChars == 0 || blocks.empty()`; if `viewValid_` and the last page of `view_` reaches the end of the book (`last.end.block >= blocks.size()`) → 1.0; otherwise the same computation as `percentAt` from the anchor: `b = blocks[clamp(anchorBlock_, 0, size − 1)]`, `off = min(anchorOffset_, b.text.size())`. This is what is saved in the recent list and what the Go-to panel starts from.
- **`viewPercent(v)`** (status bar; defined in the Rendering group): 0 if `!doc_ || totalChars == 0`; 1.0 if the last page of `v` reaches the end of the book (`last.end.block >= blocks.size()`); else `clamp(percentAt(v.pages[0].start), 0, 1)`.
- **`chapterTitleAt(block)`**: `""` without a book; `idx = doc_->tocIndexForBlock(block)`; `idx >= 0` → `doc_->toc[idx].title`, else (before the first entry) `doc_->meta.title`.

## 13. Page turns

`settings_.pageTurn`: `"curl"` (3D page curl), `"slide"`, `"fade"`, `"none"` (Instant, the default). Durations: `settings_.turnSeconds` (default 0.5 s; `Settings::load` clamps the stored value to 0.1–2 s, the settings slider offers 0.15–1.2 s).

### 13.1 `startTurn(forward, target)`

```cpp
  const std::string& mode = settings_.pageTurn;
  if (mode == "none" || fbW_ <= 0 || fbH_ <= 0) {
    const CachedView& c = forward ? cacheNext_ : cachePrev_;
    const bool ready = c.valid && c.start == target && c.signature == renderSignature();
    setViewStart(target, true);
    presentTex_ = ready ? c.rt.color : 0;
    ++(ready ? instantCached_ : instantDrawn_);
    return;
  }
  const View targetView = makeView(target);
  if (!rtA_.ensure(fbW_, fbH_, false) || !rtB_.ensure(fbW_, fbH_, false)) {
    setViewStart(target, true);
    return;
  }
  const View& sheet = forward ? view_ : targetView;
  const View& under = forward ? targetView : view_;
  glBindFramebuffer(GL_FRAMEBUFFER, rtA_.fbo);
  renderView(sheet, fbW_, fbH_);
  glBindFramebuffer(GL_FRAMEBUFFER, rtB_.fbo);
  renderView(under, fbW_, fbH_);
  glBindFramebuffer(GL_FRAMEBUFFER, 0);
  turning_ = true;
  turnFrozen_ = false;
  turnForward_ = forward;
  turnStart_ = now();
  turnTarget_ = target;
  turnStyle_ = mode == "slide" ? TurnStyle::Slide : mode == "fade" ? TurnStyle::Fade : TurnStyle::Curl;
  turnT_ = forward ? 0.0f : 1.0f;
  requestRedraw();
```

- Instant (`"none"`, or any mode while the framebuffer has no size): the new view is set at once; §14 explains the cache.
- Animated: `rtA_` always holds the **earlier** view and `rtB_` the **later** one (forwards: current, next; backwards: target, current). Both are colour-only render targets at framebuffer size (no depth), kept between turns and re-created only when the size changes. If they cannot be created the page changes without animation. Any other `pageTurn` value animates as the curl. There is no glyph-atlas overflow retry when drawing these two views.
- While turning, `view_`, `viewStart_` and the anchor still describe the page being left (the status bar shows it) and nothing is saved; they change in `finishTurn`.

### 13.2 `finishTurn()`

`if (!turning_) return; turning_ = false; turnFrozen_ = false; setViewStart(turnTarget_, true);`

A running turn is finished early by: `goNext`, `goPrev`, `goEnd`, `goToBlock`, `restorePosition`, `setColumns`, `setFontSize`, `applyFontFamily`, a framebuffer size change (`handleEvent`), and in AppUi.cpp `updateBars` (bars come or go), the settings panel (animation change, relayout) and the page jumps of the status bar and the Go-to panel. `openBook` drops it (`turning_ = false`).

### 13.3 Progress (in `iterate`)

```cpp
  if (turning_ && !turnFrozen_) {
    const float t = static_cast<float>((now() - turnStart_) / std::max(0.05f, settings_.turnSeconds));
    if (t >= 1.0f) {
      finishTurn();
    } else {
      turnT_ = turnForward_ ? t : 1.0f - t;
      requestRedraw(1);
    }
  }
```

`turnT_` is linear in time and runs 0 → 1 forwards, 1 → 0 backwards; easing is applied when drawing. `turnFrozen_` (screenshot `--turn`) stops it.

### 13.4 Drawing (in `renderFrame`, while `turning_ && rtA_.fbo && rtB_.fbo`)

The target is first cleared to the theme background (`glClearColor(bg.r, bg.g, bg.b, 1.0f); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);`). `w`, `h` = the frame size; textures are drawn with a white tint and `u0, v0, u1, v1 = 0, 1, 1, 0` (render targets are bottom-up).

| Style | What is drawn at `turnT_` |
|---|---|
| Slide | `e = round(easeInOut(turnT_) × w)`; `rtA_` at `x = −e`, `rtB_` at `x = w − e`, both `w × h`. Forwards the old view moves out to the left while the next comes in from the right; backwards the earlier view comes back in from the left. The whole view moves (both pages of a spread). |
| Fade | `p = turnForward_ ? turnT_ : 1 − turnT_` (0 → 1 in time in both directions); `from = forward ? rtA_ : rtB_` (the view being left), `to` = the other. `p < 0.5`: `from` with alpha `1 − easeInOut(2p)`; otherwise `to` with alpha `easeInOut(2p − 1)`. Halfway only the bare paper shows. |
| Curl | `PageTurn::Params`: `sheetTex = rtA_.color`, `underTex = rtB_.color`, `width = w`, `height = h`, `t = turnT_` (linear; `PageTurn` applies its own ease-in-out), `spineX = columns_ == 2 ? round((columnX_[0] + columnW_ + columnX_[1]) × 0.5) : 0`, `paper = theme_.background`, `backPrint = theme_.dark ? 0.08 : 0.13`, `shadows` left at its default (`true`); `turn_.draw(p)`. One page: the whole page peels off to the left; two pages (`spineX ≠ 0`): the right page flips over the spine like a book. Backwards, `t` runs from 1 to 0: the earlier sheet comes back and settles flat. |

The curl needs a depth buffer: the window's (24 bits) or, in screenshot mode, `rtShot_`'s.

## 14. Instant turns: views rendered ahead

With `pageTurn == "none"` the next and the previous views are rendered into textures right after a frame has been shown, so that a turn displays a finished picture in the very next frame: nothing is laid out, shaped or rasterised while the page changes.

### 14.1 `renderSignature()` — changes whenever a rendered view would look different

```cpp
  uint64_t h = 1469598103934665603ull;
  auto mix = [&h](uint64_t v) {
    h ^= v;
    h *= 1099511628211ull;
  };
  auto mixF = [&mix](float f) {
    uint32_t u = 0;
    std::memcpy(&u, &f, sizeof(u));
    mix(u);
  };
  mix(static_cast<uint64_t>(fbW_));
  mix(static_cast<uint64_t>(fbH_));
  mix(static_cast<uint64_t>(layoutGeneration_));
  mix(static_cast<uint64_t>(fontGeneration_));
  mix(static_cast<uint64_t>(columns_));
  mix(reinterpret_cast<uintptr_t>(doc_.get()));
  for (const Color& c : {theme_.background, theme_.text, theme_.secondary, theme_.accent}) {
    mixF(c.r);
    mixF(c.g);
    mixF(c.b);
  }
  mixF(theme_.gamma);
  mix(static_cast<uint64_t>(highlight_.block + 1));
  mix(highlight_.start);
  mix(highlight_.end);
  return h;
```

Because `layoutGeneration_` grows with every `updateGeometry()` call, any geometry recomputation (window size or scale, bars, text size, columns, typeface, layout settings, opening a book) invalidates the views rendered ahead; themes and brightness change the colours; a find highlight changes the last three values.

### 14.2 `fillPageCache()` — called after every presented frame

Called in `iterate` right after `SDL_GL_SwapWindow` (never in screenshot mode).

```
if (settings_.pageTurn != "none") {
  if (cacheNext_.rt.fbo || cachePrev_.rt.fbo) dropPageCache();   // only Instant uses it: free the memory
  return;
}
if (!doc_ || !viewValid_ || turning_ || fbW_ <= 0 || fbH_ <= 0) return;
sig = renderSignature();
fill(c, exists, start):
  if (!exists)                                          { c.valid = false; return; }
  if (c.valid && c.start == start && c.signature == sig) return;                 // still good
  if (!c.rt.ensure(fbW_, fbH_, false))                  { c.valid = false; return; }
  v = makeView(start);
  glBindFramebuffer(GL_FRAMEBUFFER, c.rt.fbo); glViewport(0, 0, fbW_, fbH_);
  renderView(v, fbW_, fbH_);
  if (r2d_.atlas().overflowed()) { r2d_.atlas().reset(); renderView(v, fbW_, fbH_); }  // glyphs dropped: fresh atlas, draw again
  glBindFramebuffer(GL_FRAMEBUFFER, 0);
  c.start = start; c.signature = sig; c.valid = true;
last = last page of view_;
fill(cacheNext_, !layout_->isEnd(last.end), last.end);
first = layout_->normalize(LinePos{0, 0}); prev = first; hasPrev = viewStart_ > first;
if (hasPrev) {                                          // the same target as goPrev()
  prev = layout_->pageStartBefore(viewStart_);
  if (view_.count == 2 && prev > first) prev = layout_->pageStartBefore(prev);
}
fill(cachePrev_, hasPrev, prev);
```

At most the two views are rendered, and only when their start or the signature changed; usually the call is only a check. Since every event yields frames, the views are ready one frame after any change, before the app goes idle. Neighbouring entries are not reused: after a turn both are rendered again for the new position.

### 14.3 Showing a cached view

`startTurn`'s instant path sets `presentTex_` to the cached colour texture when it is ready (valid, same start as the target, same signature). `renderFrame` then copies it 1:1 instead of drawing the page — pixel-identical to drawing it now, because it is the output of the same `renderView`. `iterate` sets `presentTex_ = 0` after that frame, so the following frames draw the page normally. When the entry is not ready the new view is simply drawn on the spot in the next frame. `presentTex_` is cleared only by that frame and by `dropPageCache`, not by a geometry change in between.

### 14.4 `dropPageCache()`

`cacheNext_.rt.destroy(); cachePrev_.rt.destroy(); cacheNext_.valid = cachePrev_.valid = false; presentTex_ = 0;` — called by `openBook`, by `fillPageCache` when the mode is not `"none"`, and by `shutdown`.

### 14.5 Statistics

`instantCached_` and `instantDrawn_` count the instant turns served from the cache and drawn on the spot (each instant-path `startTurn` increments exactly one of them, including the `--next` steps of screenshot mode). `shutdown` logs them when their sum is positive: `instant page turns: %d shown from the pages prepared ahead, %d drawn on the spot`.

## 15. Rendering

### 15.1 `imageTexture(index)` → `const gl::Texture*`

```
if (images_ contains index) return &that texture;
gl::Texture tex;                                    // stays empty (id 0) unless decoding works
if (doc_ && 0 <= index < doc_->images.size()):
  img = doc_->images[index];
  if (decodeImageRgba(img.bytes.data(), img.bytes.size(), rgba, w, h)):
    f = 1; while (w / f > maxTextureSize_ || h / f > maxTextureSize_) ++f;     // box-filter oversized pictures
    if (f > 1):
      nw = w / f; nh = h / f;                       // integer division; leftover edge pixels are dropped
      each output pixel (x, y), channel c (RGBA) = (sum of the f×f input pixels at (x*f + dx, y*f + dy)) / (f*f)
                                                    // unsigned integer division
      rgba = the small image; w = nw; h = nh;
    tex.createRgba(rgba.data(), w, h, true);        // with mipmaps
return &images_.emplace(index, tex).first->second;  // failures are cached too
```

Pictures are decoded lazily, synchronously, the first time a page shows them; their textures are destroyed when another book opens and at shutdown.

### 15.2 `drawPage(pg, x0, y0)` — one page, column left `x0`, text top `y0` (px)

For each `PageLine pl` of `pg.lines`:

1. `const BlockLayout& bl = layout_->block(pl.pos.block)`; skip the line if `pl.pos.line >= bl.lines.size()`; `L = bl.lines[pl.pos.line]`; `ly = y0 + pl.y`.
2. **Pictures** (`bl.image >= 0`): `t = imageTexture(bl.image)`; if `t && t->id`: `r2d_.image(t->id, x0 + bl.imageX, ly + bl.imageY, bl.imageW, bl.imageH, Color{1, 1, 1, 1})` — default texture coordinates, `mono = false`. Pictures keep their own colours in every theme, the night themes included (no tint, no monochrome: the colour theme is for the text). Nothing else is drawn for that line.
3. **Find highlight** (`highlight_.block == pl.pos.block`): over the runs with `r.end > highlight_.start && r.start < highlight_.end`, `hx0 = min(r.x)`, `hx1 = max(r.x + r.width)` (starting from 1e9 / −1e9); if `hx1 > hx0`: `pad = round(2 s)`, `r2d_.rect(x0 + hx0 - pad, ly, hx1 - hx0 + 2 * pad, L.height, theme_.accent.withAlpha(0.25f))`. One band per line, under the text, across all pieces of the match on that line (hyphenation pieces included).
4. **Runs**, in order:

```cpp
    const Color webColor = theme_.dark ? Color::hex(0x8AB4F8) : Color::hex(0x1A5FB4);
    int32_t underlineLink = -1;
    float underlineX0 = 0, underlineX1 = 0, underlineY = 0, underlineH = 0;
    auto flushUnderline = [&]() {
      if (underlineLink >= 0) r2d_.rect(underlineX0, underlineY, underlineX1 - underlineX0, underlineH, webColor);
      underlineLink = -1;
    };
    for (const PlacedRun& r : L.runs) {
      const bool web = (r.flags & kSpanLink) && r.link >= 0 && r.link < static_cast<int32_t>(doc_->links.size()) &&
                       isWebLink(doc_->links[static_cast<size_t>(r.link)]);
      const Color c = web ? webColor : (r.flags & (kSpanLink | kSpanNoteRef)) ? theme_.accent : theme_.text;
      r2d_.text(fonts_, *r.run, x0 + r.x, ly + r.baseline, r.size, c);
      if (r.flags & kSpanStrike) {
        r2d_.rect(x0 + r.x, std::round(ly + r.baseline - r.size * 0.3f), r.width,
                  std::max(1.0f, std::round(r.size * 0.055f)), c);
      }
      if (web && r.link == underlineLink) {
        underlineX1 = x0 + r.x + r.width;  // the same link goes on: underline the space between the words too
      } else {
        flushUnderline();
        if (web) {
          underlineLink = r.link;
          underlineX0 = x0 + r.x;
          underlineX1 = x0 + r.x + r.width;
          underlineY = std::round(ly + r.baseline + r.size * 0.12f);
          underlineH = std::max(1.0f, std::round(r.size * 0.06f));
        }
      }
    }
    flushUnderline();
```

So: body text in `theme_.text`; footnote markers and links inside the book in `theme_.accent`, not underlined; web addresses (http, https, ftp, mailto — `isWebLink`) blue in every theme (`#1A5FB4` on light themes, `#8AB4F8` on dark ones) with one continuous underline per line and link. Strike-through in the run's colour. There is no other decoration: separator blocks ("* * *"), titles and verses are ordinary text runs from the layout.

### 15.3 `drawWelcome(w, h)` — no book, or no valid view

Each line is drawn with `r2d_.drawText(shaper, text, style, x, y, size, colour)`, centred on `cx = w × 0.5` (`x = cx − textWidth / 2`, measured with `Renderer2D::textWidth` using the same shaper, style and size); `y` is the baseline.

| Line | Text | Shaper, style | Size | Colour | Baseline |
|---|---|---|---|---|---|
| title | `Lanternleaf` | `bookShaper_` (the current typeface), style 1 (italic) | `round(54 s)` | `theme_.text` | `h × 0.36` |
| tagline | `a quiet reader for FB2 and TXT books` | `uiShaper_` (PT Sans), style 1 (italic) | `round(18 s)` | `theme_.secondary` | previous + `round(40 s)` |
| hints (3 lines) | below | `uiShaper_`, style 0 | `round(16 s)` | `theme_.text` | first: previous + `round(56 s)`; each next + `round(30 s)` |

Desktop hints (two spaces after each key name; eight spaces between `books` and `F1`):

```
Ctrl+O  open a book, or drop a file onto this window
Ctrl+F  find books on your drives by name, author or text
Ctrl+L  recent books        F1  all keyboard shortcuts
```

Touch hints (`touchFirst_`):

```
Tap the middle of the screen for the menu
Menu > Find books: search this device for FB2 and TXT
Menu > Open a book: browse your folders
```

### 15.4 `renderView(v, w, h)` — into the currently bound framebuffer

1. `r2d_.begin(w, h)` (sets the viewport and blending); `glClearColor(theme_.background.r, .g, .b, 1.0f)`; `glClear(GL_COLOR_BUFFER_BIT)`; `r2d_.setTextGamma(theme_.gamma)`.
2. `if (!doc_ || !viewValid_)`: `drawWelcome(w, h); r2d_.flush(); return;`
3. `for (c = 0; c < v.count; ++c) drawPage(v.pages[c], columnX_[c], marginTop_);`
4. Two pages: the spine — a soft fold like an open book, a narrow crease and a wide, faint falloff:

```cpp
    const float sx = std::round((columnX_[0] + columnW_ + columnX_[1]) * 0.5f);
    const float wide = std::round((columnX_[1] - columnX_[0] - columnW_) * 0.32f);
    const float crease = std::max(2.0f, std::round(5.0f * displayScale_));
    const Color shade = theme_.dark ? Color{0, 0, 0, 0.0f} : Color{0.3f, 0.25f, 0.15f, 0.0f};
    const Color soft = shade.withAlpha(theme_.dark ? 0.0f : 0.045f);
    const Color core = theme_.dark ? Color::mix(theme_.background, theme_.secondary, 0.18f).withAlpha(0.6f)
                                   : shade.withAlpha(0.09f);
    r2d_.gradientH(sx - wide, 0, wide, static_cast<float>(h), shade, soft);
    r2d_.gradientH(sx, 0, wide, static_cast<float>(h), soft, shade);
    r2d_.gradientH(sx - crease, 0, crease, static_cast<float>(h), shade, core);
    r2d_.gradientH(sx, 0, crease, static_cast<float>(h), core, shade);
```

   (Full height; `wide` is 32 % of the gutter on each side of the spine. Light themes: a warm brown shadow, 4.5 % at the spine for the falloff and 9 % for the crease; dark themes: no falloff and a faint light crease.)
5. `r2d_.flush()`.

Colours come from `theme_ = adjustedTheme(theme, settings_.brightness)` (Themes.cpp: light themes dim the paper, dark themes the ink). Text gamma per theme: Day 0.86, Sepia 0.88, Dusk 1.0, Night amber 1.08, Night red 1.1. Nothing else is drawn on the page — chapter, page number and percentage are on the status bar, which comes and goes with the toolbar.

### 15.5 `renderFrame(fbo, w, h)`

```
glBindFramebuffer(GL_FRAMEBUFFER, fbo); glViewport(0, 0, w, h);
if (turning_ && rtA_.fbo && rtB_.fbo)  -> clear colour + depth to the background, draw the turn (§13.4)
else if (presentTex_)                  -> r2d_.begin(w, h); r2d_.image(presentTex_, 0, 0, w, h, Color{1,1,1,1}, 0, 1, 1, 0); r2d_.flush();
else                                   -> renderView(view_, w, h);
glViewport(0, 0, w, h);
ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());    // the UI on top, into the same framebuffer
```

### 15.6 `takeScreenshot()` → bool

```
px = vector of fbW_ * fbH_ * 4 bytes;
glBindFramebuffer(GL_FRAMEBUFFER, rtShot_.fbo); glPixelStorei(GL_PACK_ALIGNMENT, 1);
glReadPixels(0, 0, fbW_, fbH_, GL_RGBA, GL_UNSIGNED_BYTE, px); glBindFramebuffer(GL_FRAMEBUFFER, 0);
swap row y with row fbH_ - 1 - y for y < fbH_ / 2      // GL rows are bottom-up, the PNG is top-down
set every 4th byte (alpha) to 255
ok = writePngRgba(shot_.out.c_str(), px.data(), fbW_, fbH_);
SDL_Log("screenshot %s: %s", ok ? "written" : "FAILED", shot_.out.c_str());
return ok;
```

The image has the framebuffer size: the window size of `--size` times the display scale.

## 16. Links, footnotes and find in book

### 16.1 `followLink(link, mouseX, mouseY)` — the pointer position in window units

```
if (!doc_ || link < 0 || link >= doc_->links.size()) return;
target = doc_->links[link]; if (target.empty()) return;
if (target[0] == '#'):
  it = doc_->anchors.find(target.substr(1)); if not found return;
  a = it->second; if (a.block < 0 || a.block >= blocks.size()) return;
  if (blocks[a.block].notes):                          // a footnote: show it in the pop-up
    first = a.block; footnoteTitle_.clear();
    if (blocks[first].type == BlockType::Title && first + 1 < a.endBlock) { footnoteTitle_ = blocks[first].text; ++first; }
    footnoteText_ = doc_->plainText(first, std::max(a.endBlock, first + 1));
    footnoteBlock_ = a.block; footnoteX_ = mouseX; footnoteY_ = mouseY;
    showFootnote_ = true; requestRedraw();
  else:
    goToBlock(a.block, 0);                             // a link inside the book: jump there (no animation)
else if (isWebLink(target)):
  SDL_OpenURL(target.c_str());                         // the system browser / mail program
// any other target is ignored
```

The pop-up's title is the note's first block when that block is a title and the note has more blocks (in FB2 usually the note's number); the text is the plain text of the remaining blocks of the note (at least one block). The pop-up itself, its placement near the pointer and its "Go to the note" button (`goToBlock(footnoteBlock_, 0)`) are UI.

### 16.2 `runFind()` — find in this book

```cpp
  findHits_.clear();
  findTruncated_ = false;
  if (!doc_) return;
  const QueryMatcher qm(findQuery_);
  if (qm.phrase().empty()) return;
  for (int bi = 0; bi < static_cast<int>(doc_->blocks.size()); ++bi) {
    const Block& b = doc_->blocks[static_cast<size_t>(bi)];
    if (b.text.empty()) continue;
    const size_t pos = qm.findPhrase(b.text);
    if (pos == std::string_view::npos) continue;
    FindHit h;
    h.block = bi;
    h.offset = static_cast<uint32_t>(pos);
    const size_t endFolded = originalOffsetForFolded(std::string_view(b.text).substr(pos), qm.phrase().size());
    h.length = static_cast<uint32_t>(std::max<size_t>(endFolded, 1));
    h.snippet = makeSnippet(b.text, pos, h.length, 60);
    h.chapter = chapterTitleAt(bi);
    findHits_.push_back(std::move(h));
    if (findHits_.size() >= 1000) {
      findTruncated_ = true;
      break;
    }
  }
```

- The whole query is one phrase, matched after search folding (lower case, `ё` → `е`, typographic quotes and dashes folded to ASCII; `QueryMatcher`, `foldForSearch`), so the match ignores case.
- One hit per block: its first match. `offset` is the byte offset in the original text; `length` the byte length of the matched original text (at least 1).
- Snippet: about 60 characters of context, one line, with ellipses (`makeSnippet`); chapter: `chapterTitleAt(block)`.
- At most 1000 hits: after the 1000th hit the scan stops and `findTruncated_` is set (also when exactly 1000 blocks match).
- It runs synchronously on the main thread. Callers: the Find tab of the library panel, the library search when it opens a book found by its text, and screenshot `--find`. Choosing a hit sets `highlight_ = {block, offset, offset + length}` and calls `goToBlock` (done by the caller); the highlight is cleared by `Esc`/Back as the last thing `closeTopPanel` closes, and by `openBook`.

## 17. Input

### 17.1 `handleEvent(e)` → `SDL_AppResult`

1. `if (e.type == wakeEvent_) { requestRedraw(1); return SDL_APP_CONTINUE; }` — the wake event is not passed to ImGui.
2. `ImGui_ImplSDL3_ProcessEvent(&e)` — every other event goes to Dear ImGui first.
3. If `e.type == SDL_EVENT_MOUSE_BUTTON_UP && e.button.which == SDL_TOUCH_MOUSEID`: `ImGui::GetIO().AddMousePosEvent(-FLT_MAX, -FLT_MAX)`. A lifted finger is not a hovering mouse; without this the last button touched stays highlighted. (ImGui still sees the release at the finger's position first: its input queue keeps the order.)
4. `requestRedraw()` — 3 frames for every event.
5. `const ImGuiIO& io = ImGui::GetIO();` (its `WantCaptureMouse`/`WantCaptureKeyboard` are those computed in the last frame), then:

| Event | Action |
|---|---|
| `SDL_EVENT_QUIT`, `SDL_EVENT_WINDOW_CLOSE_REQUESTED` | `quitting_ = true; return SDL_APP_SUCCESS;` (SDL then calls `shutdown`) |
| `SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED`, `SDL_EVENT_WINDOW_RESIZED`, `SDL_EVENT_WINDOW_DISPLAY_SCALE_CHANGED` | `before = displayScale_; oldW = fbW_, oldH = fbH_; updateGeometry();` if `turning_` and the framebuffer size changed → `finishTurn()`; if `fabs(before − displayScale_) > 0.001` → `applyImGuiStyle()`; if `!settings_.fullscreen` and the window is not maximized (`SDL_GetWindowFlags(window_) & SDL_WINDOW_MAXIMIZED` clear) → `SDL_GetWindowSize(window_, &settings_.winW, &settings_.winH)` |
| `SDL_EVENT_WINDOW_MOVED` | if not full screen and not maximized → `SDL_GetWindowPosition(window_, &settings_.winX, &settings_.winY)` |
| `SDL_EVENT_WINDOW_DISPLAY_CHANGED`, `SDL_EVENT_DISPLAY_CURRENT_MODE_CHANGED` | `applyMinimumWindowSize()` |
| `SDL_EVENT_WINDOW_MAXIMIZED` | `settings_.maximized = true` |
| `SDL_EVENT_WINDOW_RESTORED` | `settings_.maximized = false` |
| `SDL_EVENT_WINDOW_FOCUS_LOST`, `SDL_EVENT_WILL_ENTER_BACKGROUND`, `SDL_EVENT_TERMINATING` | `saveSettingsNow()` |
| `SDL_EVENT_SCREEN_KEYBOARD_SHOWN` | `if (!SDL_TextInputActive(window_)) SDL_StopTextInput(window_);` — a keyboard no text field asked for (Android restores it after the app was restarted while it was open, and SDL shows it again on resume) would cover the page |
| `SDL_EVENT_SCREEN_KEYBOARD_HIDDEN` | `requestRedraw()` |
| `SDL_EVENT_DID_ENTER_FOREGROUND` | `storageAccessChecked_ = -100` (re-check file access at once: it may have been granted in the system settings); `fingers_.clear(); touch_ = Touch{};` |
| `SDL_EVENT_DROP_FILE` | `if (e.drop.data) openBook(e.drop.data);` |
| `SDL_EVENT_KEY_DOWN` (key repeats included) | if `!io.WantCaptureKeyboard`, or the key is `SDLK_F11`, `SDLK_ESCAPE` or `SDLK_AC_BACK` → `onKeyDown(e.key)` |
| `SDL_EVENT_MOUSE_BUTTON_DOWN` | if `e.button.which != SDL_TOUCH_MOUSEID` and any popup is open and `!pointOverUi(e.button.x, e.button.y)` → `returnToReading()` and nothing else (a click outside an open drop-down or menu: ImGui closes it, the panels close too; ImGui keeps the mouse while a popup is open, so `onMouseDown` would not see this click); otherwise, if `!io.WantCaptureMouse` → `onMouseDown(e.button)` |
| `SDL_EVENT_MOUSE_WHEEL` | if `!io.WantCaptureMouse` → `onWheel(e.wheel)` |
| `SDL_EVENT_PINCH_UPDATE` | trackpad pinch: if `e.pinch.scale > 0 && fingers_.size() < 2 && !io.WantCaptureMouse` → `zoomBy(e.pinch.scale)` |
| `SDL_EVENT_FINGER_DOWN`, `_MOTION`, `_UP`, `_CANCELED` | `onFinger(e.tfinger)` — always, whatever ImGui wants |
| anything else | nothing more |

Then `return SDL_APP_CONTINUE`. Window position and size changes are only recorded in `settings_`; they are written with the next save (no `scheduleSave` here). Touch-synthesised mouse events (`which == SDL_TOUCH_MOUSEID`) reach ImGui but never turn pages (§17.4); touch is handled from the finger events.

### 17.2 Keyboard: `onKeyDown(k)`

`ctrl`, `shift`, `alt` = `k.mod & SDL_KMOD_CTRL` / `SDL_KMOD_SHIFT` / `SDL_KMOD_ALT` (either side). One `switch (k.key)`; after it, always `requestRedraw()`.

| Key (`SDLK_…`) | Condition | Action |
|---|---|---|
| `RIGHT`, `DOWN`, `PAGEDOWN` | any modifiers | `goNext()` |
| `SPACE` | | Shift: `goPrev()`, otherwise `goNext()` |
| `LEFT`, `UP`, `PAGEUP`, `BACKSPACE` | any modifiers | `goPrev()` |
| `HOME` | | `goHome()` |
| `END` | | `goEnd()` |
| `EQUALS`, `PLUS` | Ctrl | `zoomBy(1.08f)` |
| `KP_PLUS` | any | `zoomBy(1.08f)` |
| `MINUS` | Ctrl | `zoomBy(1.0f / 1.08f)` |
| `KP_MINUS` | any | `zoomBy(1.0f / 1.08f)` |
| `0`, `KP_0` | Ctrl | `setFontSize(21.0f)` — 21 on every platform (also on Android, whose default is 19) |
| `O` | Ctrl | `openFileDialog()` |
| `F` | Ctrl | `showPanel(Panel::Library, shift ? 2 : 1); focusQuery_ = true;` — Ctrl+F finds books, Ctrl+Shift+F finds in this book |
| `L` | Ctrl | `showPanel(Panel::Library, 0)` — recent books |
| `T` | any modifiers (Ctrl+T too) | `togglePanel(Panel::Toc)` |
| `G` | Ctrl | `togglePanel(Panel::Goto)` |
| `COMMA` | Ctrl | `togglePanel(Panel::Settings)` |
| `F1` | any | `togglePanel(Panel::Help)` |
| `F10` | any | `toolbarPinned_ = !toolbarPinned_` |
| `F11` | any | `toggleFullscreen()` |
| `RETURN` | Alt | `toggleFullscreen()` |
| `C` | not Ctrl | `cycleTheme(shift ? -1 : 1)` |
| `B` | not Ctrl | `setColumns(columns_ == 2 ? "1" : "2")` — book (two pages) ↔ one page |
| `1` … `5` | Ctrl | `setTheme(themes()[k.key − SDLK_1].id)` if that index `< themes().size()` |
| `ESCAPE` | | `if (!closeTopPanel()) { if (toolbarPinned_) toolbarPinned_ = false; else if (settings_.fullscreen && !touchFirst_) toggleFullscreen(); }` |
| `AC_BACK` (Android Back) | | `if (!closeTopPanel()) { if (toolbarPinned_) toolbarPinned_ = false; else quitRequested_ = true; }` — on the bare page Back leaves the app (the position is saved); the next `iterate` returns `SDL_APP_SUCCESS` |
| any other key | | nothing (still `requestRedraw()`) |

Keys arrive here only while ImGui does not want the keyboard (for instance not while a text field is being edited), except F11, Esc and Back, which always do.

### 17.3 Closing things

**`closeTopPanel()`** (Esc, Android Back) closes exactly one thing — the first open one in this order — and returns `true`; `false` when nothing was open:

1. `statusEdit_ != StatusEdit::None` → `StatusEdit::None` (typing a page number or percentage: cancel it);
2. an ImGui context exists and any popup is open → `ImGui::ClosePopupsExceptModals()` (an open menu or drop-down goes first; the toolbar stays);
3. `showFootnote_` → false;
4. `messages_` non-empty → `clear()`;
5. `storagePromptOpen_` → false;
6. `browser_.open` → false;
7. `showAbout_`; 8. `showHelp_`; 9. `showGoto_`; 10. `showSettings_`; 11. `showToc_` → false;
12. `showLibrary_ && doc_` → `showLibrary_ = false` (without a book the library cannot be closed this way);
13. `highlight_.block >= 0` → `highlight_ = {}` (the find highlight goes);
14. otherwise `return false`.

**`readingModeBlocked()`** — something is open that a click on the page should close: `anyPanelOpen() || showFootnote_ || storagePromptOpen_ || <any popup open> || (touchFirst_ && toolbarPinned_ && doc_)` (on touch screens the pinned toolbar is a menu too).

**`returnToReading()`**: `showLibrary_ = showToc_ = showSettings_ = showGoto_ = showHelp_ = showAbout_ = false; browser_.open = false; showFootnote_ = false; storagePromptOpen_ = false; toolbarPinned_ = false; focusPanel_ = Panel::None;` if an ImGui context exists `ImGui::ClosePopupsExceptModals()`; `requestRedraw()`. It leaves `messages_`, `highlight_` and `statusEdit_` alone.

### 17.4 Clicks and taps

**`handleTap(px, py, touch)`** — framebuffer px:

1. `if (readingModeBlocked()) { returnToReading(); return; }` — a click or tap outside every open menu, panel and note closes them and returns to the page; it does not also turn the page.
2. `if (!doc_ || !viewValid_ || winW_ <= 0 || winH_ <= 0) { if (touch) toolbarPinned_ = !toolbarPinned_; return; }`
3. Links and footnote markers: `slop = touch ? 18 s : 8` px (markers are tiny: be generous with fingers). For each column `c < view_.count`: skip it if `px < columnX_[c] − slop` or `px > columnX_[c] + columnW_ + slop`; `HitResult hit; if (layout_->hitTest(view_.pages[c], px − columnX_[c], py − marginTop_, hit, slop) && hit.link >= 0)` → `followLink(hit.link, px × winW_/fbW_, py × winH_/fbH_)` and return.
4. Zones: `px < fbW_ × 0.3` → `goPrev()`; else if `touch && px < fbW_ × 0.7` → `toolbarPinned_ = true` (a centre tap shows the menu and the status bar; the next tap anywhere on the page hides them through step 1); else `goNext()`.

| Input | Left 30 % | 30–70 % | Right 30 % |
|---|---|---|---|
| mouse left click | previous page | next page | next page |
| finger tap | previous page | show toolbar and status bar | next page |

**`onMouseDown(b)`**:

- `b.which == SDL_TOUCH_MOUSEID` → return (touches are handled as gestures);
- right button (`SDL_BUTTON_RIGHT`) → `toolbarPinned_ = !toolbarPinned_`; return (keeps the toolbar and status bar open, or lets them go);
- `SDL_BUTTON_X1` → `goPrev()`, return; `SDL_BUTTON_X2` → `goNext()`, return;
- not the left button, or `winW_ <= 0 || winH_ <= 0` → return (the middle button does nothing);
- `handleTap(b.x × fbW_/winW_, b.y × fbH_/winH_, false)`.

**`pointOverUi(x, y)`** — window units: false without an ImGui context; otherwise true if any `ImGuiWindow* w` in `GImGui->Windows` with `w->WasActive && !w->Hidden && !(w->Flags & ImGuiWindowFlags_ChildWindow)` has `w->Rect().Contains(ImVec2(x, y))`. Every top-level window drawn in the last frame counts (toolbar, status bar, panels, pop-ups, tooltips, the toast).

### 17.5 Touch gestures: `onFinger(f)`

`px = f.x × fbW_`, `py = f.y × fbH_` (SDL's normalised coordinates to framebuffer px). `fingers_` maps finger ids to their last position; `touch_` follows the first finger.

**`SDL_EVENT_FINGER_DOWN`**: `fingers_[f.fingerID] = {px, py}`. If now `fingers_.size() == 1`: `touch_ = Touch{}`, `active = true`, `id = f.fingerID`, `x0 = x = px`, `y0 = y = py`, `t0 = now()`, `overUi = pointOverUi(f.x × winW_, f.y × winH_)`, `dismiss = !overUi && (anyPanelOpen() || showFootnote_ || storagePromptOpen_ || <any popup open>)` — outside an open panel, menu or note lifting the finger returns to the page (a swipe there does not turn it); the toolbar alone does not count, so pages can still be swiped while it shows. Otherwise (a second finger): `touch_.multi = true; pinchDist_ = 0;` — a pinch, never a tap or a swipe. Return.

**`SDL_EVENT_FINGER_MOTION`**: update `fingers_[f.fingerID]` if present. If `touch_.active && f.fingerID == touch_.id`: `x = px; y = py;` then

- brightness swipe start (Android; the left third of the page): if `!brightness && !multi && !overUi && !dismiss && doc_ && platform::canSetScreenBrightness() && x0 < fbW_ / 3.0f`, with `dx = px − x0`, `dy = py − y0`: if `fabs(dy) > 24 s && fabs(dy) > 2 fabs(dx)` → `brightness = true; brightnessY = py; brightnessFrom = settings_.screenBrightness >= 0 ? settings_.screenBrightness : std::sqrt(std::clamp(platform::systemScreenBrightness(), 0.0f, 1.0f));` (measured from where the swipe was recognised, so the level does not jump);
- during a brightness swipe (`brightness && !multi && fbH_ > 0`):

```cpp
        setScreenBrightness(touch_.brightnessFrom + (touch_.brightnessY - py) / (fbH_ * 0.6f));
        toast_ = "Screen brightness " + std::to_string(static_cast<int>(std::lround(settings_.screenBrightness * 100.0f))) + " %";
        toastUntil_ = now() + 1.5;
```

  (up is brighter; 60 % of the screen height spans the whole range; the toast text is set directly, e.g. `Screen brightness 42 %`, without a wake timer).

Then the pinch, for any finger: if `fingers_.size() >= 2 && !touch_.overUi`: `a` = the first and `b` = the second map entry (the two lowest finger ids), `d = hypot(a.x − b.x, a.y − b.y)`; if `pinchDist_ > 0 && d > 0`: `ratio = d / pinchDist_`, and only if `fabs(ratio − 1) > 0.04` → `zoomBy(ratio); pinchDist_ = d;` (a smaller change keeps the old reference distance, so slow pinches still add up); otherwise (no reference yet, or `d == 0`) `pinchDist_ = d`. Return.

**`SDL_EVENT_FINGER_UP` and `SDL_EVENT_FINGER_CANCELED`**: `fingers_.erase(f.fingerID)`. If `touch_.active && f.fingerID == touch_.id`:

- `brightness` → `showToast(toast_, 1.2)` (the level stays on screen a moment longer, then goes by itself);
- else if `dismiss && !multi && type == FINGER_UP` → `returnToReading()`;
- else if `!multi && !overUi && type == FINGER_UP`: `dx = x − x0, dy = y − y0, slop = 14 s, dt = now() − t0`;
  - if `fabs(dx) > max(40 s, fbW_ × 0.08) && fabs(dx) > 1.5 fabs(dy)` → a swipe: `dx < 0` (to the left) → `goNext()`, else `goPrev()`;
  - else if `fabs(dx) < slop && fabs(dy) < slop && dt < 0.6` → `handleTap(x0, y0, true)` (at the touch-down point);
  - anything else (a long press, a vertical drag outside the brightness zone) does nothing;
- `touch_.active = false`.

Always afterwards: `pinchDist_ = 0; if (fingers_.empty()) touch_.multi = false;`

| Gesture | Threshold | Effect |
|---|---|---|
| tap | moved < 14 s px in x and y, < 0.6 s | `handleTap` (zones of §17.4, links, footnotes) |
| horizontal swipe | abs(dx) > max(40 s, 8 % of the width) and abs(dx) > 1.5 abs(dy) | left → next page, right → previous page |
| brightness swipe (Android) | starts in the left third with abs(dy) > 24 s and abs(dy) > 2 abs(dx), with a book open, not over the UI and nothing to dismiss | level = start level + upward travel / (60 % of the height), clamped 0.01–1; toast `Screen brightness N %` |
| pinch | two or more fingers, not started over the UI; distance ratio change > 4 % | `zoomBy(ratio)` |
| touch outside an open panel / menu / note | — | lifting the finger returns to reading |
| touch starting on the UI | — | left to ImGui |
| `FINGER_CANCELED` | — | no tap or swipe |

### 17.6 Mouse wheel: `onWheel(w)`

```cpp
  float dy = w.y;
  if (w.direction == SDL_MOUSEWHEEL_FLIPPED) dy = -dy;
  if (SDL_GetModState() & SDL_KMOD_CTRL) {
    zoomBy(std::pow(1.08f, dy));
    return;
  }
  wheelAccum_ += dy;
  if (wheelAccum_ >= 1.0f) {
    wheelAccum_ = 0;
    goPrev();
  } else if (wheelAccum_ <= -1.0f) {
    wheelAccum_ = 0;
    goNext();
  }
```

Wheel up = previous page, wheel down = next page; fractional (touchpad) deltas accumulate to a whole notch and the accumulator is reset only when it triggers. Ctrl+wheel zooms by 1.08 per notch on every event (no threshold). (`zoomAccum_` is not used.)

## 18. Text size, screen brightness, full screen, screen saver

- **`setFontSize(logicalPx)`**: `logicalPx = std::clamp(logicalPx, 8.0f, 96.0f); if (std::fabs(logicalPx - settings_.fontSize) < 0.01f) return;` finish a running turn; `settings_.fontSize = logicalPx; updateGeometry(); scheduleSave(); requestRedraw();`. The anchor is untouched, so the reading position stays while the text reflows.
- **`zoomBy(factor)`**: `setFontSize(settings_.fontSize * factor)`.
- Zoom inputs and steps: Ctrl+Plus / keypad Plus and the toolbar's `A+` ×1.08; Ctrl+Minus / keypad Minus and `A-` ÷1.08; Ctrl+wheel 1.08^notches; trackpad pinch by `e.pinch.scale`; touch pinch by the distance ratio (4 % dead band); Ctrl+0 → 21. Limits 8–96 here (the settings file and `--font-size` accept 8–120; the settings slider 10–72).
- **`setScreenBrightness(level)`**: `if (!platform::canSetScreenBrightness()) return;` (desktop: nothing) `settings_.screenBrightness = level < 0 ? -1.0f : std::clamp(level, 0.01f, 1.0f);` `platform::setScreenBrightness(sb < 0 ? -1.0f : sb * sb)`; `scheduleSave(); requestRedraw();`. The level is what the reader sees on the slider; the screen gets level², so that a swipe changes the brightness evenly to the eye, with fine steps where it matters at night. −1 follows the system again.
- **`toggleFullscreen()`**: `settings_.fullscreen = !settings_.fullscreen; SDL_SetWindowFullscreen(window_, settings_.fullscreen); scheduleSave();` — F11, Alt+Enter, Esc (desktop, last in line), the toolbar, the menu and the settings. On Android it hides or shows the system bars.
- **`applyScreenSaver()`**: `if (settings_.keepScreenOn && doc_ && !shot_.enabled) SDL_DisableScreenSaver(); else SDL_EnableScreenSaver();` — keep the screen on while reading. Called after every successful `openBook` and by the settings checkbox; not at start-up without a book (SDL's own default applies until then).

## 19. Themes and the automatic night theme

- **`refreshTheme()`**: `theme_ = adjustedTheme(themes()[themeIndex(settings_.theme)], settings_.brightness)`.
- **`setTheme(id)`**: `settings_.theme = themes()[themeIndex(id)].id` (an unknown id becomes `"day"`); `refreshTheme(); applyImGuiStyle(); scheduleSave(); requestRedraw();`.
- **`cycleTheme(dir)`**: `n = themes().size()` (5); `i = (themeIndex(settings_.theme) + dir + n) % n; setTheme(themes()[i].id);`. Order: `day` → `sepia` → `dusk` → `night-amber` → `night-red` → `day` (`C` forwards, Shift+C backwards); Ctrl+1 … Ctrl+5 select Day, Sepia, Dusk, Night amber, Night red.
- **`checkAutoNight(force)`**:

```cpp
  if (!settings_.autoNight) {
    autoNightState_ = -1;
    return;
  }
  const std::time_t t = std::time(nullptr);
  std::tm lt{};
#ifdef _WIN32
  localtime_s(&lt, &t);
#else
  localtime_r(&t, &lt);
#endif
  const int hr = lt.tm_hour;
  const int from = settings_.nightFrom, to = settings_.nightTo;
  const bool night = from > to ? (hr >= from || hr < to) : (hr >= from && hr < to);
  const int state = night ? 1 : 0;
  if (force || state != autoNightState_) {
    autoNightState_ = state;
    setTheme(night ? settings_.nightTheme : settings_.dayTheme);
  }
```

  Defaults: night from 21 to 7 (21:00–06:59 local time), day theme `day`, night theme `night-amber`; `from == to` is never night. Forced at start-up and when the auto-night settings change (UI); otherwise checked at the start of every `iterate`, and `iterate` runs at least every 30 s (the minute timer), so the switch happens within about 30 s of the hour. Only a change of state switches: a theme chosen by hand stays until the next day/night change. Turning the option off only forgets the state; the theme stays. The switch is saved like any theme change.

## 20. Persistence

Files in `prefDir_`: `settings.json` (`Settings::save`, written atomically through a temporary file), `library-cache.json` (`MetaCache::save`, written only when it changed), `imgui.ini` (Dear ImGui's own), `lanternleaf.log` (§3.1).

**`saveReadingPosition()`**:

```cpp
  if (!doc_ || bookPath_.empty()) return;
  RecentBook* rb = settings_.findRecent(bookPath_, bookFingerprint_);
  if (!rb) rb = &settings_.touchRecent(bookPath_, bookFingerprint_);
  rb->block = anchorBlock_;
  rb->offset = anchorOffset_;
  rb->percent = currentPercent();
  rb->blockCount = static_cast<int>(doc_->blocks.size());
  rb->title = doc_->meta.title;
  rb->authors = doc_->meta.authorsJoined();
  settings_.lastBook = bookPath_;
```

The entry is found by path, then by fingerprint, and keeps its place in the list; if the reader removed it from the list meanwhile, `touchRecent` puts it back at the front.

**`saveSettingsNow()`**:

```cpp
  saveDirty_ = false;
  saveTimer_ = 0;
  lastSave_ = now();
  if (shot_.enabled && !shotAllowSave_) return;
  saveReadingPosition();
  settings_.lastQuery = query_;
  settings_.save(settingsFile_);
  metaCache_.save(metaCacheFile_);
```

(`saveTimer_` is forgotten, not removed: a pending timer still fires once and wakes the loop.)

**`scheduleSave()`**:

```cpp
  saveDirty_ = true;
  if (!saveTimer_) {
    saveTimer_ = SDL_AddTimer(
        1500,
        [](void* ud, SDL_TimerID, Uint32) -> Uint32 {
          static_cast<App*>(ud)->wake();
          return 0;
        },
        this);
  }
```

and in `iterate`: `if (saveDirty_ && now() - lastSave_ > 1.0) saveSettingsNow();`. So a change is written in the next frame when the last save is more than 1 s old; otherwise the one-shot 1500 ms timer wakes the loop and the save happens then — at most about one write per second, and no change waits more than about 1.5 s.

When the files are written:

| Trigger | What |
|---|---|
| any `scheduleSave()` (then via `iterate`) — in App.cpp: every page turn and jump (`setViewStart`, `goToBlock`), `setColumns`, `setFontSize`, `setScreenBrightness`, `toggleFullscreen`, `setTheme` (also cycling, Ctrl+1–5, auto night), new search folders (`pollAsync`); in the UI: its own changes | settings + reading position + cache |
| `SDL_EVENT_WINDOW_FOCUS_LOST`, `SDL_EVENT_WILL_ENTER_BACKGROUND`, `SDL_EVENT_TERMINATING` | the same, at once |
| the end of every successful `openBook` | the same, at once |
| `shutdown` (if the window and the GL context exist) | the same |
| a library search ends (`pollAsync`) | only `library-cache.json`, unconditionally (also in screenshot mode) |

Window position, size and the maximized state are only recorded in `settings_` and go with the next write. In screenshot mode nothing but the metadata cache is written unless `--allow-save` is given.

## 21. Main loop and frame pacing

### 21.1 `iterate()` → `SDL_AppResult`

1. `if (quitRequested_) return SDL_APP_SUCCESS;`
2. `pollAsync()` (§21.4).
3. `checkAutoNight(false)`.
4. Turn progress (§13.3).
5. `if (doc_ && !viewValid_) rebuildView();`
6. Page counting — page numbers show only on the status bar, so pages are counted (for the page height that goes with it) while it is on screen: if `countingPages()` (`doc_ && barsShown_`) `&& !layout_->countDone() && (!turning_ || shot_.enabled)`: `c0 = now(); layout_->countStep(shot_.enabled ? 1000.0 : 4.0);` (a time budget in ms per frame) `countWork_ += now() - c0;` and when `layout_->countDone()` becomes true: `SDL_Log("page count: %d pages, %.0f ms of work", layout_->pageCount(), countWork_ * 1000.0); countWork_ = 0; requestRedraw();`. Counting pauses during an animation (except in screenshot mode).
7. `if (saveDirty_ && now() - lastSave_ > 1.0) saveSettingsNow();`
8. `if (touchFirst_) storageAccess();` — notices that file access was granted (in the system settings) and refreshes what depended on it (cached, re-checked at most once a second; see `10-user-interface.md`).
9. Toolbar and status bar visibility — shown while the pointer is near the top or bottom edge (or on the bars), a panel or drop-down is open, a page number is being typed, or pinned:

```cpp
  float mx = 0, my = 0;
  SDL_GetMouseState(&mx, &my);
  const bool hasMouseFocus = SDL_GetMouseFocus() == window_;
  const float kw = fbW_ > 0 ? static_cast<float>(winW_) / static_cast<float>(fbW_) : 1.0f;
  const float topZone = std::max(56.0f, barsShown_ ? topBarH_ + safeTop_ * kw : 0.0f);
  const float bottomZone = std::max(56.0f, barsShown_ ? bottomBarH_ + safeBottom_ * kw : 0.0f);
  const bool hover = !touchFirst_ && hasMouseFocus && !shot_.enabled &&
                     (my < topZone || (doc_ && my > static_cast<float>(winH_) - bottomZone));
  showToolbar_ = toolbarPinned_ || !doc_ || anyPanelOpen() || hover || statusEdit_ != StatusEdit::None ||
                 (ImGui::GetCurrentContext() &&
                  ImGui::IsPopupOpen("", ImGuiPopupFlags_AnyPopupId | ImGuiPopupFlags_AnyPopupLevel));
```

   (window units: the zones are at least 56 units, or the bars' own height plus the safe inset while they show; the bottom zone only with a book; touch devices have no hover — a centre tap pins the toolbar instead; without a book the toolbar always shows.)
10. The ImGui frame: `ImGui_ImplOpenGL3_NewFrame(); ImGui_ImplSDL3_NewFrame(); ImGui::NewFrame(); updateBars(); if (doc_ && !viewValid_) rebuildView(); drawUi(); ImGui::Render();`. `updateBars` (AppUi.cpp) must run inside the frame, because it measures the bars with ImGui, and before `drawUi`: when the bars come or go it finishes a running turn and calls `updateGeometry`, which invalidates the view; the second `rebuildView` then lays the page out for the new height before the status bar and the page are drawn, so both show the same view.
11. Soft keyboard (touch): `if (touchFirst_ && GImGui->PlatformImeData.WantTextInput && ImGui::IsMouseReleased(ImGuiMouseButton_Left) && SDL_TextInputActive(window_) && !SDL_ScreenKeyboardShown(window_)) SDL_StartTextInputWithProperties(window_, g_textInput.active ? g_textInput.active : g_textInput.text);` — the reader put the keyboard away (Back) and taps the field again: SDL only shows the keyboard when text input starts, and it is still running, so it is asked for once more.
12. Render target: `GLuint fbo = 0;` (the window); in screenshot mode `rtShot_.ensure(fbW_, fbH_, true); fbo = rtShot_.fbo;` (off-screen, with a depth buffer).
13. `if (r2d_.atlas().fill() > 0.92f) r2d_.atlas().reset();`
14. `renderFrame(fbo, fbW_, fbH_);` then `if (r2d_.atlas().overflowed()) { r2d_.atlas().reset(); renderFrame(fbo, fbW_, fbH_); }` — the glyph atlas ran full in the middle of the page (large text, many styles): start a fresh atlas and draw the frame again before showing it, so a page with missing letters never flashes on screen.
15. `presentTex_ = 0;` — a pre-rendered view is shown for one frame; the following ones draw the same page.
16. Screenshot mode: §22 (may return). Otherwise `SDL_GL_SwapWindow(window_); fillPageCache();` (Instant turns: render the next and previous views ahead, after the frame is shown).
17. `if (redrawFrames_ > 0) --redrawFrames_;`
18. `if (!GImGui->InputEventsQueue.empty()) requestRedraw(1);` — Dear ImGui hands queued input over one key press per frame ("trickling"); keep drawing until its queue is empty, because soft keyboards deliver a whole word (or backspaces plus a corrected word) at once and the rest would otherwise wait for the next unrelated event.
19. `updateCallbackRate(); return SDL_APP_CONTINUE;`

### 21.2 `updateCallbackRate()`

```cpp
  const bool busy = turning_ || redrawFrames_ > 0 || shot_.enabled || (countingPages() && !layout_->countDone());
  const char* want = busy ? "0" : "waitevent";
  if (rateHint_ != want) {
    rateHint_ = want;
    SDL_SetHint(SDL_HINT_MAIN_CALLBACK_RATE, want);
  }
```

`"0"`: SDL calls `iterate` as often as it can (paced by vsync, swap interval 1); `"waitevent"`: SDL calls it only after an event. The app therefore draws continuously only while a page turns, while pages are counted with the status bar on screen, in screenshot mode, or for the requested redraw frames — otherwise it sleeps. `rateHint_` starts empty, so the hint is first set at the end of the first `iterate` (until then SDL's default rate applies).

### 21.3 Redraw requests and wake-ups

`redrawFrames_` starts at 3; `requestRedraw(n)` raises it to at least `n`; every `iterate` decrements it. Every event requests 3 frames, the wake event 1, a running animation 1 per frame, a non-empty ImGui input queue 1; the UI asks for 10 when a status-bar field opens.

Wake-ups (the user event `wakeEvent_`, pushed by `wake()`, thread-safe):

| Source | When |
|---|---|
| `minuteTimer_` | every 30 000 ms, repeating (auto night; expired toasts) |
| `saveTimer_` | 1500 ms after the first `scheduleSave()` since the last save, once |
| `showToast` (UI) | `seconds × 1000 + 50` ms after a toast, once |
| `search_` notify | from the search worker thread while a library search runs (throttled by `LibrarySearch`) |
| file and folder dialogs (UI) | when the reader picks something (after the result is queued in `pendingOpen_` / `pendingFolders_`) |

### 21.4 `pollAsync()` — results from dialogs and threads

```cpp
  std::vector<std::string> open, folders;
  {
    std::lock_guard<std::mutex> lock(asyncMutex_);
    open.swap(pendingOpen_);
    folders.swap(pendingFolders_);
  }
  if (!open.empty()) openBook(open.front());
  for (const std::string& f : folders) {
    if (std::find(settings_.searchRoots.begin(), settings_.searchRoots.end(), f) == settings_.searchRoots.end())
      settings_.searchRoots.push_back(f);
    scheduleSave();
  }
```

then, if `search_` exists: `nh = search_->takeHits()`; if non-empty, append them to `hits_`, `hitsSorted_ = false`, `requestRedraw()`. `running = search_->running()`; if `searchWasRunning_ && !running` (a search just ended): `p = search_->progress()`, `SDL_Log("search \"%s\" %s: %llu folders, %llu files, %llu books, %d found, %.2f s", query_.c_str(), p.cancelled ? "stopped" : "done", p.dirs, p.files, p.books, (int)hits_.size(), p.seconds)` and `metaCache_.save(metaCacheFile_)`. Finally `searchWasRunning_ = running`.

Only the first queued book is opened; folders already in the list are not added twice (but each still schedules a save). The producers are the SDL file and folder dialog callbacks of `openFileDialog` / `addFolderDialog` (AppUi.cpp), which run on another thread, push under `asyncMutex_` and call `wake()`.

## 22. Screenshot / automation mode

`--screenshot FILE` renders off-screen, writes a PNG and quits; it is used for visual checks (also on Android, where the arguments come from the launching intent). Everything that differs from a normal run:

- **Window** (§7): hidden on the desktop (shown on phones), exactly `--size` (default 1280 × 820, floor 200 × 200 per side, then the 320 × 240 floor of `createWindow`), no saved position, no maximize, no full screen, no brightness restore, no minimum window size.
- **Files**: no `imgui.ini`; `saveSettingsNow` writes nothing unless `--allow-save` (the metadata cache is still written when a library search ends).
- **Start-up** (§6.2): `--goto`, `--next`, `--turn`, `--panel`, `--search…`, `--find…` set the scene; the storage prompt is suppressed unless `--panel storage`.
- **Frames** (§21.1): no toolbar by hover; page counting gets up to 1000 ms per frame and continues during a turn; frames are drawn into `rtShot_` (framebuffer size, with depth) instead of the window; no swap and no instant-turn cache (every instant turn is "drawn on the spot"); the callback rate is always `"0"`; `applyScreenSaver` always enables the screen saver.

After each rendered frame (step 16 of §21.1):

```cpp
    const bool searchBusy = search_ && search_->running();
    const bool countBusy = countingPages() && !layout_->countDone();
    ++shot_.frame;
    if (shot_.frame >= 3 && shot_.clickPhase < shot_.clicks.size() * 3) {
      pushShotClickPhase();
      shot_.lastClickFrame = shot_.frame;
      requestRedraw();
    } else if (shot_.frame >= shot_.frames && shot_.frame >= shot_.lastClickFrame + 3 && !searchBusy &&
               !countBusy) {
      takeScreenshot();
      return SDL_APP_SUCCESS;
    }
    if (now() > 120.0) return SDL_APP_FAILURE;  // a search or page count that never finishes
```

- Scripted clicks start at frame 3, one step per frame (move, press, release for each `--click`, in order); `lastClickFrame` starts at −100.
- The screenshot is taken at the first frame that is at least `--frames` (default 4), at least 3 frames after the last click step, with no library search running and the page count finished (it only runs while the status bar shows). It captures the frame drawn in that same `iterate`. Example: no clicks → the 4th frame; one click → steps on frames 3, 4, 5 and the screenshot on frame 8.
- `iterate` returns `SDL_APP_SUCCESS` after the screenshot even when writing the PNG failed (the log says `FAILED`), and `SDL_APP_FAILURE` once more than 120 s have passed since start-up.

**`pushShotClickPhase()`**:

```cpp
  const size_t i = shot_.clickPhase / 3, phase = shot_.clickPhase % 3;
  ++shot_.clickPhase;
  const float x = shot_.clicks[i].first, y = shot_.clicks[i].second;
  SDL_Event e{};
  if (phase == 0) {
    e.type = SDL_EVENT_MOUSE_MOTION;
    e.motion.windowID = SDL_GetWindowID(window_);
    e.motion.which = 1;
    e.motion.x = x;
    e.motion.y = y;
  } else {
    e.type = phase == 1 ? SDL_EVENT_MOUSE_BUTTON_DOWN : SDL_EVENT_MOUSE_BUTTON_UP;
    e.button.windowID = SDL_GetWindowID(window_);
    e.button.which = 1;
    e.button.button = SDL_BUTTON_LEFT;
    e.button.down = phase == 1;
    e.button.clicks = 1;
    e.button.x = x;
    e.button.y = y;
  }
  SDL_PushEvent(&e);
  SDL_Log("screenshot click %zu: %s at %.0f,%.0f", i + 1, phase == 0 ? "move" : phase == 1 ? "press" : "release", x,
          y);
```

The events go through the normal path (`SDL_AppEvent` → `handleEvent` → ImGui and the click logic of §17), one step per frame, so the UI has seen the pointer over its windows before the button goes down, as with a real mouse. `which = 1` makes them mouse events, not touch.

## 23. Shutdown: `shutdown()`

```cpp
  if (search_) {
    search_->cancel();
    search_->wait();
  }
  if (instantCached_ + instantDrawn_ > 0) {
    SDL_Log("instant page turns: %d shown from the pages prepared ahead, %d drawn on the spot", instantCached_,
            instantDrawn_);
  }
  if (minuteTimer_) SDL_RemoveTimer(minuteTimer_);
  if (saveTimer_) SDL_RemoveTimer(saveTimer_);
  if (window_ && gl_) saveSettingsNow();
  if (gl_) {
    for (auto& kv : images_) kv.second.destroy();
    images_.clear();
    rtA_.destroy();
    rtB_.destroy();
    rtShot_.destroy();
    dropPageCache();
    turn_.shutdown();
    r2d_.shutdown();
    if (ImGui::GetCurrentContext()) {
      ImGui::GetPlatformIO().Platform_SetImeDataFn = g_textInput.backend;
      ImGui_ImplOpenGL3_Shutdown();
      ImGui_ImplSDL3_Shutdown();
      ImGui::DestroyContext();
    }
    if (g_textInput.text) SDL_DestroyProperties(g_textInput.text);
    if (g_textInput.number) SDL_DestroyProperties(g_textInput.number);
    g_textInput = TextInputHook{};
    SDL_GL_DestroyContext(gl_);
    gl_ = nullptr;
  }
  if (window_) SDL_DestroyWindow(window_);
  window_ = nullptr;
```

- The search worker is stopped and joined first; then the instant-turn statistics line — the last line the app writes to the log (nothing after it logs).
- The reading position and settings are saved (subject to the screenshot rule) before any GL object goes.
- The IME callback is given back to the backend before the ImGui backends shut down; `ImGui::DestroyContext` writes `imgui.ini` (not in screenshot mode).
- Every step is guarded, so `shutdown` is also safe after a failed `init` (for example: no context yet → no save and no GL clean-up; no ImGui context → no ImGui shutdown). The log file stays open and the log hook installed. Toast timers are not removed (SDL removes them when it quits).

## 24. The log file

`lanternleaf.log` in the settings folder: truncated at every start, one line per message containing exactly the message text, flushed at once; every message that reaches SDL's log output goes there and also to the default output (debugger, console, logcat). The messages of App.cpp:

| Format | When |
|---|---|
| `minimum window size %dx%d (10%% of the display, %dx%d)` | `createWindow` and display changes (desktop, not screenshot), when the minimum changes |
| `English hyphenation patterns not found` | `loadHyphenation`, English patterns missing or empty |
| `Russian hyphenation patterns not found` | the same for Russian |
| `Lanternleaf %s, OpenGL %s` | end of the set-up: version (e.g. `0.6.0`) and the `GL_VERSION` string (`unknown` if none) |
| `opened %s: %s, %s, %d blocks, %llu chars, parse %.0f ms, first page %.0f ms` | every book opened: path, format (`FB2`, `TXT`, `FB2 (zip)` …), encoding, block count, code points, parse time, time to the first page |
| `%s` | `showError`, e.g. `Could not open "book.fb2": <reason>` |
| `page count: %d pages, %.0f ms of work` | the background page count finished |
| `search "%s" %s: %llu folders, %llu files, %llu books, %d found, %.2f s` | a library search ended (`done` or `stopped`) |
| `screenshot click %zu: %s at %.0f,%.0f` | every scripted click step (`move`, `press`, `release`) |
| `screenshot %s: %s` | `written` or `FAILED`, then the PNG path |
| `instant page turns: %d shown from the pages prepared ahead, %d drawn on the spot` | `shutdown`, if at least one instant turn happened |

(AppUi.cpp adds `file access granted`.) A typical desktop start therefore begins with `minimum window size …`, then `Lanternleaf 0.6.0, OpenGL …`, then `opened …`.

## 25. Contract with AppUi.cpp and FileBrowser.cpp

Members defined in AppUi.cpp / FileBrowser.cpp that App.cpp calls: `showPanel`, `togglePanel` (keys), `anyPanelOpen` (`readingModeBlocked`, touch, toolbar visibility), `storageAccess` (`init`, `iterate`), `openFileDialog` (Ctrl+O), `openFileBrowser` (screenshot panels), `startLibrarySearch` (screenshot search), `applyImGuiStyle` (`initImGui`, `setTheme`, scale changes), `showToast` (`setColumns`, the brightness swipe), `updateBars` and `drawUi` (`iterate`). `countingPages()` and `requestRedraw()` are inline in `App.h`.

App.cpp members that the UI calls: `openBook`, `goToBlock`, `goToPercent`, `setViewStart`, `finishTurn`, `setColumns`, `setFontSize`, `zoomBy`, `setTheme`, `refreshTheme`, `checkAutoNight`, `toggleFullscreen`, `applyScreenSaver`, `setScreenBrightness`, `applyFontFamily`, `availableFamilies`, `runFind`, `chapterTitleAt`, `viewPercent`, `currentPercent`, `updateGeometry`, `scheduleSave`, `showError`, `wake`, `now`.

State written by the UI and read here: the panel flags, `browser_.open`, `storagePromptOpen_`, `statusEdit_`, `focusPanel_`, `barsShown_`/`topBarH_`/`bottomBarH_` (by `updateBars`), `highlight_` (a chosen find hit), `findQuery_`, `query_`, `libraryTab_`, `focusQuery_`, `messages_` (cleared by its OK button), `storageAccessChecked_` (set to −100 after asking for access), and the settings it edits (layout values, `pageTurn`, `turnSeconds`, `brightness`, `keepScreenOn`, auto-night values). App.cpp writes `toast_`/`toastUntil_` directly during a brightness swipe.

For reference, the behaviour of `updateBars` that this file relies on (specified in `10-user-interface.md`): `shown = showToolbar_ && doc_ != nullptr`; `top = shown ? toolbarBarHeight() : 0`, `bottom = shown ? statusBarBarHeight() : 0` (window units); if `shown`, `top` and `bottom` all equal the stored values, nothing happens; otherwise it stores them in `barsShown_`, `topBarH_`, `bottomBarH_`, cancels status-bar editing when hiding, finishes a running turn, calls `updateGeometry()` and `requestRedraw()`.

## Checklist

Start-up, window, files
- [ ] A first start on the desktop (no settings file) opens a 1180 × 820 window titled `Lanternleaf` with the Day theme, one page, Instant page turns, text size 21 and the library panel on its Find tab; with a recent list it opens the Recent tab instead when no book can be opened.
- [ ] `--settings-dir D` puts `settings.json`, `library-cache.json`, `imgui.ini` and `lanternleaf.log` in `D` (created if missing); without it SDL's preference folder for `Lanternleaf` is used.
- [ ] `lanternleaf.log` is emptied at every start; on the desktop it starts with `minimum window size WxH (10% of the display, WxH)` and then `Lanternleaf 0.6.0, OpenGL …`.
- [ ] The window cannot be made smaller than 10 % of its monitor (rounded, per side); moving it to another monitor re-applies the rule (a new log line only when the minimum changes).
- [ ] A saved position is used only if the point 60 units right and 20 units below the window's top-left corner is on some display's usable area; a maximized window starts maximized and keeps its earlier restored size and position in the settings.
- [ ] Without the `assets` folder the program shows `The bundled fonts could not be loaded. Is the 'assets' folder next to the program?` and exits.
- [ ] A book named on the command line is opened; otherwise the last book if the file still exists; a failing book shows `Could not open "<file name>": <reason>` and logs it.
- [ ] A saved typeface that is not installed falls back to PT Serif.

Opening a book and the reading position
- [ ] Reopening a book shows the same first line as when it was left, also after the text size, the window size or the typeface changed, and also after the file was renamed or moved (same content).
- [ ] If the book now parses into a different number of blocks, the position is restored by percentage.
- [ ] The window title becomes `<title> — <authors> · Lanternleaf` (just `<title> · Lanternleaf` without authors).
- [ ] Opening a book closes the library and the file browser, removes the find highlight, the find results and the footnote pop-up, and disables the screen saver when "keep the screen on" is set.

Geometry
- [ ] The text size on screen is the setting × the display scale, rounded to a quarter pixel.
- [ ] "Two pages" on a window where each page would be narrower than 8 em shows one page and the toast `Two pages need a wider screen: turn the device sideways or make the text smaller.` for 5 s.
- [ ] "Automatic" shows two pages only when the framebuffer is more than 1.2 times wider than tall and each page gets at least 22 em (18 em on phones).
- [ ] One page is at most `maxLineWidth` em wide (default 40) and centred.
- [ ] When the toolbar and status bar appear, the text moves between them (gap ≥ 10 s and ≥ 0.6 em) without losing the position; when they hide, the text uses the whole screen again.
- [ ] Two pages show a fold in the middle of the gap: a warm faint shadow on light themes, a faint light crease on dark themes.

Navigation and input
- [ ] Right, Down, Page Down and Space go forward; Left, Up, Page Up, Backspace and Shift+Space go back; Home and End go to the first and last page; nothing happens at either end.
- [ ] With two pages, "back" goes back two pages and End shows the last two pages.
- [ ] Mouse wheel down turns forward, up turns back (one page per whole notch); Ctrl+wheel changes the text size by 1.08 per notch.
- [ ] Ctrl+Plus/Ctrl+= and keypad Plus enlarge by 1.08, Ctrl+Minus and keypad Minus shrink, Ctrl+0 sets 21; the size never leaves 8–96.
- [ ] A left click in the left 30 % of the window goes back, anywhere else forward; mouse buttons X1/X2 go back/forward; right click and F10 pin and unpin the toolbar and status bar.
- [ ] Moving the mouse within 56 units of the top edge (or of the bottom edge with a book open) shows the toolbar and status bar; moving away hides them.
- [ ] On a touch screen: a tap in the left 30 % goes back, in the middle shows the toolbar and status bar, on the right goes forward; the next tap on the page hides them; a horizontal swipe left goes forward, right goes back; a two-finger pinch zooms.
- [ ] On Android a vertical swipe starting in the left third of the page changes the screen brightness (up brighter, 60 % of the screen height for the whole range) with the toast `Screen brightness N %`, which stays 1.2 s after the finger lifts.
- [ ] A click or tap outside an open panel, menu or footnote closes all of them and does not turn the page.
- [ ] Esc closes one thing per press in the order: status-bar field, menu/drop-down, footnote, messages, storage prompt, file browser, About, Help, Go to, Settings, Contents, Library (only with a book), find highlight; then unpins the toolbar; then leaves full screen (desktop). Android Back does the same and finally quits the app.
- [ ] T toggles the contents, Ctrl+G Go to, Ctrl+Comma the settings, F1 the help, Ctrl+L recent books, Ctrl+F find books, Ctrl+Shift+F find in this book, Ctrl+O the open dialog, F11 and Alt+Enter full screen, B one page ↔ two pages.
- [ ] Clicking a footnote marker opens the note in a pop-up near the pointer (fingers get an 18 s px tolerance, the mouse 8 px); an in-book link jumps without animation; a web link opens the system browser.
- [ ] Dropping a book file on the window opens it.

Rendering
- [ ] Body text uses the theme's text colour and gamma; footnote markers and in-book links the accent colour; web links are blue (`#1A5FB4` on Day/Sepia, `#8AB4F8` on Dusk/Night) with one continuous underline per line.
- [ ] Pictures keep their own colours in every theme; pictures larger than the GPU's maximum texture size are reduced by an integer box filter.
- [ ] A find hit is shown as a translucent accent band (alpha 0.25) behind the matched words, 2 s px wider on each side, one band per line.
- [ ] Without a book the page shows `Lanternleaf` (italic, 54 s px), the tagline `a quiet reader for FB2 and TXT books` and three hint lines (desktop or touch texts).

Page turns
- [ ] Curl, slide and fade take `turnSeconds` (default 0.5 s); a new key press during a turn completes it at once and starts the next.
- [ ] Slide moves the whole view to the left going forward and to the right going back, with a cubic ease-in-out; fade shows only the paper at the halfway point.
- [ ] With two pages the curl flips the right page over the spine; with one page the whole page peels off to the left.
- [ ] Instant mode: after the first turn, turns show a view prepared ahead; on quitting the log ends with `instant page turns: N shown from the pages prepared ahead, M drawn on the spot`.
- [ ] Switching from Instant to an animation frees the two cached views after the next frame.

Themes, brightness, screen
- [ ] C cycles Day → Sepia → Dusk → Night amber → Night red → Day, Shift+C backwards, Ctrl+1 … Ctrl+5 select them directly; the choice is saved.
- [ ] With "switch themes by the clock" on (default 21:00–07:00), the night theme appears within about 30 s after the start hour even when the app is idle, and the day theme after the end hour; a theme chosen by hand stays until the next switch.
- [ ] A screen brightness chosen in the app is applied as level² at the next start (Android).

Persistence and pacing
- [ ] A page turn is written to `settings.json` within about 1.5 s, and at once when the window loses focus or the app goes to the background.
- [ ] Window size and position are remembered only from changes made while not maximized and not in full screen.
- [ ] An idle app draws nothing (SDL waits for events) and wakes at least every 30 s.
- [ ] While the status bar shows and pages are being counted the app keeps drawing until the count is done, then logs `page count: N pages, X ms of work`.
- [ ] Folders added with the folder dialog are appended to the search roots once each.
- [ ] A finished library search logs `search "<query>" done: … folders, … files, … books, … found, … s` and saves the metadata cache.
- [ ] Find in this book returns at most one result per block (its first match), at most 1000 results (then `findTruncated_` is set), ignoring case and `ё`/`е`.

Screenshot mode
- [ ] `--screenshot out.png --size 800x600 book.fb2` writes an 800 × 600 PNG (times the display scale) after 4 frames, logs `screenshot written: out.png` and exits successfully, without changing any settings file.
- [ ] `--size 100x50` gives a 320 × 240 window (parsing raises each side to at least 200, `createWindow` to at least 320 × 240); `--frames 0` acts as 1.
- [ ] `--goto 50` starts the view at the line holding the character at 50 % of the book; `--next 3` then moves three views further, without animation.
- [ ] `--turn 0.4` shows a forward turn frozen at t = 0.4 (the curl unless the page-turn setting is slide or fade).
- [ ] `--panel toc|settings|help|goto|library|toolbar|browser|folders|about|storage` opens that panel (or pins the toolbar, or shows the storage prompt).
- [ ] `--search Q --search-root D [--search-content]` shows the search results once the search has finished; `--find P` shows the find results, with `--find-go` the page of the first match with its highlight instead.
- [ ] `--click x,y` sends move, press and release on frames 3, 4 and 5 (logged as `screenshot click 1: move at x,y` …) and the screenshot is taken at least 3 frames later.
- [ ] `--allow-save` lets the run write `settings.json`; `--theme`, `--font-size`, `--columns`, `--page-turn` and `--font` override the loaded settings for the run (and are saved in a normal run).
- [ ] A run that has not finished after 120 s exits with a failure status.
