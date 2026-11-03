# 06 — Library search, query matching, transliteration and the metadata cache

**Scope.** This part specifies `src/core/LibrarySearch.cpp`: the transliteration skeleton (`translitSkeleton`), the
query matcher (`QueryMatcher`), the folded-offset mapping and snippet helpers (`originalOffsetForFolded`,
`makeSnippet`), the persistent metadata cache (`MetaCache`) and the background library scanner (`LibrarySearch`).
All declarations — `QueryMatcher`, `MetaRecord`, `MetaCache`, `MatchFlag`, `SearchOptions`, `SearchHit`,
`LibrarySearch` and its `Progress` — are in `src/core/LibrarySearch.h`, which the implementer has verbatim; they are
referred to by name and not repeated. The module calls helpers declared in `src/core/Unicode.h`,
`src/core/BookLoader.h`, `src/core/FileUtil.h` and `src/core/Document.h` (specified in other parts); the behaviour of
those helpers that this file depends on is summarised in section 1. The callers (`App.cpp`, `AppUi.cpp`) are
specified elsewhere; only their contracts are restated in section 8.

---

## 1. File layout and dependencies

```
#include "core/LibrarySearch.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <filesystem>
#include <functional>

#include "core/BookLoader.h"
#include "core/FileUtil.h"
#include "core/Unicode.h"

namespace fs = std::filesystem;          // file scope, before namespace ll

namespace ll {
// ---- transliteration skeleton ----…   translitSkeleton
// ---- matcher ----…                    QueryMatcher::QueryMatcher, QueryMatcher::matchField,
//                                       QueryMatcher::findPhrase, originalOffsetForFolded, makeSnippet
// ---- cache ----…                      MetaCache::load, save, get, put, size
// ---- search ----…                     LibrarySearch::~LibrarySearch, isSkippedDirName, start, cancel, wait,
//                                       progress, takeHits, maybeNotify, pushHit, isNonBookTextName,
//                                       processFile, run
}  // namespace ll
```

The four section comments have the form `// ---- <name> ` followed by dashes up to a total line length of 96
characters, with the names `transliteration skeleton`, `matcher`, `cache`, `search`. `<functional>` provides
`std::boyer_moore_horspool_searcher`. JSON is nlohmann-json 3.12 (`nlohmann::json`, whose objects are `std::map`
based, so keys are always serialised in byte-wise sorted order).

Behaviour of external helpers that this file relies on:

- `foldForSearch(s)` (Unicode): decodes UTF-8; **drops** U+00AD (soft hyphen, `kSoftHyphen`), U+200B–U+200D,
  U+FEFF and combining marks (`isCombiningMarkCp`); maps every other code point through `foldForSearchCp`
  (lower case, `ё`→`е`, typographic quotes → `'` or `"`, dashes → `-`, all white space incl. NBSP → `' '`, common
  Latin diacritics stripped; always one code point to one code point); writes a `' '` only if the previous written
  code point was not a `' '` (runs of white space collapse to one space; a leading space is kept).
- `trimCopy` trims ASCII white space and NBSP at both ends; `collapseSpaces` collapses runs of `isSpaceCp` white space
  (newlines included) into one `' '` and drops leading and trailing white space; `utf8PrevPos`/`utf8NextPos` step one
  code point; `toLowerUtf8` lower-cases with `toLowerCp`; `iequalsAscii` compares with ASCII case folding.
- `formatFromName` (BookLoader): by ASCII-case-insensitive suffix, in this order: `.fb2.zip` → `Fb2Zip`, `.txt.zip` →
  `TxtZip`, `.zip` → `Zip`, `.fb2` → `Fb2`, `.txt` → `Txt`, otherwise `Unknown`; `isSupportedBookName` is
  `formatFromName != Unknown`. `fileStemOf` takes the part after the last `/` or `\` and strips up to two of the
  extensions `.zip`, `.fb2`, `.txt` (case-insensitive), e.g. `Tolstoy_Anna.fb2.zip` → `Tolstoy_Anna`.
- `loadBookMeta(path, meta, err)` reads metadata cheaply (zip archives, even mis-named ones, are unpacked: first
  `.fb2` entry, else the largest `.txt`); returns false for unreadable files, archives without a book, and files
  named `.zip`/`.fb2.zip`/`.txt.zip` that are not zip archives.
  `loadBookText(path, text, meta, err)` returns the whole readable text plus metadata. Both set `meta.title` to the
  file stem when the book has none, and append ` (zip)` to `meta.format` for archives.
- `BookMeta::authorsJoined()` joins the non-empty authors with `", "`.
- `readFile`, `writeFileAtomic` (writes `<path>.tmp` and renames), `pathFromUtf8`/`pathToUtf8` (UTF-8 ↔
  `fs::path`, never through the ANSI code page).

---

## 2. `translitSkeleton(folded)`

Purpose: a crude Latin "skeleton" that makes Cyrillic names and their Latin transliterations comparable
(`Толстой` ~ `Tolstoy` ~ `Tolstoj` all give `tolstoi`). The argument is normally already folded by `foldForSearch`,
but the function lower-cases every code point itself, so raw text works too. Two stages.

### 2.1 Stage 1 — code points to an intermediate string `lat`

For each code point `c = toLowerCp(utf8Decode(folded, i))`:

- `c < 0x80`: append `c` if it is `a`–`z` or `0`–`9`, otherwise append `' '` (every other ASCII character —
  space, punctuation, `_`, `'`, `"`, `-`, `.` — becomes a space).
- otherwise look `c` up in this table (verbatim from the source) and append the mapped string (possibly empty):

```cpp
switch (c) {
  case 0x430: m = "a"; break;
  case 0x431: m = "b"; break;
  case 0x432: m = "v"; break;
  case 0x433: m = "g"; break;
  case 0x434: m = "d"; break;
  case 0x435: case 0x451: case 0x44D: case 0x454: m = "e"; break;
  case 0x436: m = "zh"; break;
  case 0x437: m = "z"; break;
  case 0x438: case 0x439: case 0x44B: case 0x456: case 0x457: m = "i"; break;
  case 0x43A: m = "k"; break;
  case 0x43B: m = "l"; break;
  case 0x43C: m = "m"; break;
  case 0x43D: m = "n"; break;
  case 0x43E: m = "o"; break;
  case 0x43F: m = "p"; break;
  case 0x440: m = "r"; break;
  case 0x441: m = "s"; break;
  case 0x442: m = "t"; break;
  case 0x443: case 0x45E: m = "u"; break;
  case 0x444: m = "f"; break;
  case 0x445: m = "h"; break;
  case 0x446: m = "c"; break;
  case 0x447: m = "ch"; break;
  case 0x448: case 0x449: m = "sh"; break;
  case 0x44A: case 0x44C: m = ""; break;
  case 0x44E: m = "iu"; break;
  case 0x44F: m = "ia"; break;
  case 0x491: m = "g"; break;
  default: break;
}
```

The same table with the letters:

| Code points | Letters | Appended |
|-------------|---------|----------|
| U+0430 | а | `a` |
| U+0431 | б | `b` |
| U+0432 | в | `v` |
| U+0433 | г | `g` |
| U+0434 | д | `d` |
| U+0435, U+0451, U+044D, U+0454 | е ё э є | `e` |
| U+0436 | ж | `zh` |
| U+0437 | з | `z` |
| U+0438, U+0439, U+044B, U+0456, U+0457 | и й ы і ї | `i` |
| U+043A | к | `k` |
| U+043B | л | `l` |
| U+043C | м | `m` |
| U+043D | н | `n` |
| U+043E | о | `o` |
| U+043F | п | `p` |
| U+0440 | р | `r` |
| U+0441 | с | `s` |
| U+0442 | т | `t` |
| U+0443, U+045E | у ў | `u` |
| U+0444 | ф | `f` |
| U+0445 | х | `h` |
| U+0446 | ц | `c` |
| U+0447 | ч | `ch` |
| U+0448, U+0449 | ш щ | `sh` |
| U+044A, U+044C | ъ ь | (nothing) |
| U+044E | ю | `iu` |
| U+044F | я | `ia` |
| U+0491 | ґ | `g` |

Upper-case Cyrillic reaches the table through `toLowerCp` (Ё→ё, Є→є, І→і, Ї→ї, Ў→ў, Ґ→ґ).

- no table entry and `isLetterCp(c)`: append `'?'` — a placeholder for letters of other scripts (Greek, CJK,
  Cyrillic letters outside the table such as ђ ј љ, Latin letters that folding did not strip such as ß æ), so that
  neighbouring words do not merge. Source comment: `// other scripts: keep a placeholder so words do not merge`.
- otherwise (non-ASCII non-letters: `…`, `«`, `№`, …): append `' '`.

### 2.2 Stage 2 — Latin normalisation into `out`

Every character is emitted through `put`:

```cpp
auto put = [&](char ch) {
  if (ch == ' ') {
    if (!out.empty() && out.back() != ' ') out.push_back(' ');
    return;
  }
  if (!out.empty() && out.back() == ch) return;  // collapse doubled letters
  out.push_back(ch);
};
```

So leading spaces vanish, runs of spaces become one, and any character equal to the last emitted one is dropped —
letters, digits and `'?'` alike (`анна` → `ana`, `100` → `10`, `??` → `?`). A space between two equal letters
prevents the collapse.

`lat` is then scanned left to right; at each position the rules are tried **in this order** on the remaining text
(`lat`, not `out`):

```cpp
for (size_t i = 0; i < lat.size();) {
  const std::string_view r = std::string_view(lat).substr(i);
  if (r.substr(0, 4) == "shch") { put('s'); put('h'); i += 4; continue; }
  if (r.substr(0, 3) == "sch") { put('s'); put('h'); i += 3; continue; }
  if (r.substr(0, 2) == "kh") { put('h'); i += 2; continue; }
  if (r.substr(0, 2) == "ts" || r.substr(0, 2) == "tz") { put('c'); i += 2; continue; }
  if (r.substr(0, 2) == "ph") { put('f'); i += 2; continue; }
  if (r.substr(0, 2) == "ck") { put('k'); i += 2; continue; }
  const char ch = lat[i++];
  switch (ch) {
    case 'w': put('v'); break;
    case 'x': put('k'); put('s'); break;
    case 'q': put('k'); break;
    case 'y':
    case 'j': put('i'); break;
    default: put(ch); break;
  }
}
while (!out.empty() && out.back() == ' ') out.pop_back();
return out;
```

| Rule (in order) | Result |
|-----------------|--------|
| `shch` | `sh` |
| `sch` | `sh` |
| `kh` | `h` |
| `ts`, `tz` | `c` |
| `ph` | `f` |
| `ck` | `k` |
| `w` | `v` |
| `x` | `ks` |
| `q` | `k` |
| `y`, `j` | `i` |
| anything else | itself |

Note what is *not* a rule: `ch`, `zh`, `sh` stay as they are (so Cyrillic `ч` and Latin `ch` agree), and digraphs are
only recognised inside `lat` (a space between `k` and `h` prevents `kh`). Trailing spaces are removed at the end.
The result contains only `a`–`z`, `0`–`9`, `?` and single inner spaces.

### 2.3 Examples (hand-derived)

| Input | Skeleton |
|-------|----------|
| `Толстой`, `tolstoy`, `Tolstoj` | `tolstoi` |
| `Достоевский`, `Dostoevsky` | `dostoevski` |
| `Цветаева`, `Tsvetaeva` | `cvetaeva` |
| `Чехов`, `Chekhov` | `chehov` |
| `Щука`, `Shchuka` | `shuka` |
| `Хрущёв`, `Khrushchev` | `hrushev` |
| `Царь`, `Tsar` | `car` |
| `Юрий`, `Yuri`, `Jurij` | `iuri` |
| `Tolstoy_Anna-Karenina.fb2` | `tolstoi ana karenina fb2` |
| `  Hello,   World! ` | `helo world` |
| `Philipp` | `filip` |
| `Deutsch` | `deuch` (`ts`→`c`, then `c` collapses) |
| `Alexander` | `aleksander` |
| `ПЕТР` | `petr` |
| `straße` | `stra?e` |
| `αθηνα` | `?` |
| `100` | `10` |

---

## 3. `QueryMatcher`

### 3.1 Constructor

```
phrase_ = trimCopy(foldForSearch(query));
split phrase_ at every ' ' (the folded phrase has single spaces only);
for each piece t:
    strip from both ends every character of the set  "  '  ,  .  ;  :  !  ?  (  )  -
    if t is not empty and terms_.size() < 32:
        terms_.push_back(t); skeletons_.push_back(translitSkeleton(t));
```

The punctuation test, verbatim:

```cpp
auto isPunct = [](char c) {
  return c == '"' || c == '\'' || c == ',' || c == '.' || c == ';' || c == ':' || c == '!' || c == '?' ||
         c == '(' || c == ')' || c == '-';
};
```

- Only leading and trailing punctuation is stripped; inner punctuation stays (`anna-karenina` is one term).
  Typographic quotes and dashes were already folded to `"`, `'` and `-`, so `«Война»` gives the term `война` and a
  lone `—` gives no term. Characters outside the set (`[`, `…`, `/`, `*`, …) are kept.
- Terms beyond the 32nd are dropped silently (then `allTermsMask()` is `0xFFFFFFFF`).
- `phrase_` keeps all punctuation: it is the whole folded, trimmed query and is what `findPhrase` looks for.
- `empty()` is true when no term survived: `""`, `"   "`, `"--"`, `"?!"` … (the phrase itself may be non-empty).
- There is no minimum term length for literal matching; a one-letter term is a valid term.

### 3.2 `matchField(field)`

```
if field is empty or terms_ is empty: return 0
f = foldForSearch(field)
sk = (computed lazily, at most once) translitSkeleton(f)
mask = 0
for t in 0 .. terms_.size()-1:
    if f contains terms_[t] (std::string::find):            mask |= 1u << t; continue
    if skeletons_[t].size() >= 3 and sk contains skeletons_[t]: mask |= 1u << t
return mask
```

- Matching is plain substring search in folded text (case, `ё`/`е`, quotes, dashes, diacritics and white space are
  normalised by folding); there are no word boundaries (`мир` matches `Мирный`).
- The skeleton fallback is used only for terms whose skeleton has **at least 3 characters**; it compares the term
  skeleton with the skeleton of the whole folded field (`Tolstoy` matches `Толстой`, `толстой` matches
  `Tolstoy_Anna`). The field skeleton is computed only when some term needs it.
- Bit t corresponds to the t-th term in query order.

### 3.3 `findPhrase(text)`

```
if phrase_ is empty: return npos
f = foldForSearch(text)                    // the whole text
p = first occurrence of phrase_ in f:
      phrase_.size() >= 4 → std::search(f.begin(), f.end(),
                                        std::boyer_moore_horspool_searcher(phrase_.begin(), phrase_.end()))
      otherwise           → f.find(phrase_)
if not found: return std::string_view::npos
return originalOffsetForFolded(text, p)
```

Both search paths return the leftmost occurrence; the searcher choice is for speed only (byte length 4 is the
threshold). The result is a byte offset into the original `text`. Because folding collapses white space, a phrase
matches across double spaces and line breaks (`счастливые семьи` is found in `Все  СЧАСТЛИВЫЕ\nсемьи`).
Punctuation in the query must appear in the text (`hello world` is not found in `hello, world`).

---

## 4. `originalOffsetForFolded(s, target)`

Maps a byte offset in `foldForSearch(s)` back to a byte offset in `s`. It replays the folding exactly. The source
starts the function with this two-line comment:

```cpp
  // Mirrors foldForSearch(): returns the start of the first source character that produces output at or
  // after `target` (dropped characters and collapsed spaces are skipped).
```

Body:

```cpp
size_t out = 0;
bool lastSpace = false;
for (size_t i = 0; i < s.size();) {
  const size_t start = i;
  const char32_t c = utf8Decode(s, i);
  if (c == kSoftHyphen || (c >= 0x200B && c <= 0x200D) || c == 0xFEFF || isCombiningMarkCp(c)) continue;
  const char32_t f = foldForSearchCp(c);
  if (f == U' ' && lastSpace) continue;
  if (out >= target) return start;
  lastSpace = f == U' ';
  out += f < 0x80 ? 1 : (f < 0x800 ? 2 : (f < 0x10000 ? 3 : 4));
}
return s.size();
```

`out` counts the UTF-8 bytes the folded output has produced so far. Dropped characters (U+00AD, U+200B–U+200D,
U+FEFF, combining marks) and collapsed spaces never stop the scan, so the result is the start of the first
output-producing character at or after the target; a target at or beyond the folded length gives `s.size()`.

---

## 5. `makeSnippet(text, pos, matchLen, radius)`

`radius` defaults to 70 (header). Steps:

1. `pos = min(pos, text.size())`.
2. `b = pos`, then up to `radius` times, while `b > 0`: `b = utf8PrevPos(text, b)` (radius counts code points).
3. `e = min(text.size(), pos + matchLen)`, then up to `radius` times, while `e < text.size()`:
   `e = utf8NextPos(text, e)`.
4. Result: `"…"` (U+2026, bytes `E2 80 A6`) if `b > 0`, then `collapseSpaces(text.substr(b, e - b))`, then `"…"` if
   `e < text.size()`.

The window is flattened to one line (newlines and tabs become single spaces, leading/trailing white space of the
window is dropped); the ellipses depend only on whether the window touches the ends of `text`. `matchLen` is a byte
count (callers pass the folded phrase length).

---

## 6. `MetaCache`

A map from a file path (UTF-8, exactly as the scanner produced it) to a `MetaRecord`, guarded by the mutex `m_`,
with a `dirty_` flag. It lets later searches skip re-reading book metadata.

### 6.1 File format

A single compact JSON object (no whitespace, UTF-8, non-ASCII characters written unescaped, keys sorted
byte-wise because nlohmann objects are maps):

```json
{"files":{"<path>":{"au":"<authors>","b":false,"fo":"<format>","la":"<lang>","s":<size>,"se":"<series>","t":<mtime>,"ti":"<title>"}},"version":1}
```

| Key | Meaning | Written | Read with default |
|-----|---------|---------|-------------------|
| `version` | always `1` | always | ignored by `load` |
| `files` | object: path → record | always | required (must be an object) |
| `s` | file size in bytes (`uint64_t`) | always | `uint64_t(0)` |
| `t` | modification time (`int64_t`, native file-clock ticks) | always | `int64_t(0)` |
| `b` | `isBook` | only when `false` | `true` |
| `ti` | title | only when non-empty | `""` |
| `au` | authors (joined with `", "`) | only when non-empty | `""` |
| `se` | series | only when non-empty | `""` |
| `la` | language | only when non-empty | `""` |
| `fo` | format, e.g. `FB2`, `TXT`, `FB2 (zip)` | only when non-empty | `""` |

Example of two records: `{"files":{"C:\\Books\\a.fb2":{"au":"Лев Николаевич Толстой","fo":"FB2","la":"ru","s":12345,"se":"Классика","t":133771234567890000,"ti":"Анна Каренина"},"C:\\Books\\x.zip":{"b":false,"s":42,"t":133771234567890000}},"version":1}`.

### 6.2 `load(file)`

1. `readFile(file, data)`; on failure return false (map untouched).
2. `nlohmann::json::parse(data, nullptr, false)` (no exceptions); if the result is discarded or not an object,
   return false.
3. Inside `try { … } catch (...) { return false; }`:
   - find `"files"`; if missing or not an object, return false (map untouched);
   - lock `m_`, `map_.clear()`, then for every member (in the JSON object's sorted key order) build a `MetaRecord`
     with `v.value("s", uint64_t(0))`, `v.value("t", int64_t(0))`, `v.value("b", true)`,
     `v.value("ti", std::string())` and `"au"`, `"se"`, `"la"`, `"fo"` likewise, and store it as `map_[key]`;
   - `dirty_ = false`.
4. Return true.

A member that is not an object, or a value of the wrong type (e.g. `"s":"x"`), makes `value()` throw; the exception
is caught and `load` returns false — the map has then already been cleared and holds only the members read before
the bad one, and `dirty_` keeps its previous value. `version` is never checked. A successful load replaces the whole
map (no merge).

### 6.3 `save(file)`

1. Lock `m_`. If `!dirty_`, return true immediately — nothing is written, not even a missing file is created.
2. Build `files` (a JSON object) from every record as in the table of 6.1 (`{"s", size}`, `{"t", mtime}`, then the
   optional keys), and `j = {{"version", 1}, {"files", files}}`.
3. `out = j.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace)` — compact, UTF-8 output, invalid UTF-8 in
   strings replaced by U+FFFD instead of throwing.
4. `dirty_ = false` (before writing: a failed write is not retried by a later `save` unless something new is put).
5. Unlock, then return `writeFileAtomic(file, out)`.

### 6.4 `get`, `put`, `size`

- `get(path, size, mtime, out)`: under the lock; returns false if `path` is unknown or if the stored `size` or `mtime`
  differs from the arguments (exact comparison — this is the cache validation); otherwise copies the record to `out`
  and returns true. A stale record is not removed.
- `put(path, rec)`: under the lock; `map_[path] = rec` (insert or replace) and `dirty_ = true`.
- `size()`: under the lock; number of records (books and non-books).

### 6.5 Thread safety

Every member function takes `m_` (it is `mutable`, so `get`/`size` are `const`). The worker thread calls `get`/`put`
while the UI thread may call `save`; `save` serialises under the lock but writes the file after releasing it.

---

## 7. `LibrarySearch`

One instance owns at most one worker thread. Hits are produced by the worker and collected by the UI with
`takeHits()`; counters are atomics; `hits_`, `currentDir_`, `finished_`, `cancelled_`, `startTime_`, `endTime_` are
guarded by `m_`.

### 7.1 Lifetime: destructor, `start`, `cancel`, `wait`, `running`

- `~LibrarySearch()`: `cancel(); wait();`.
- `start(opt)`:
  1. `cancel(); wait();` — stops and joins a previous scan (its unread hits are discarded in the next step).
  2. Under the lock: `hits_.clear()`, `currentDir_.clear()`, `finished_ = false`, `cancelled_ = false`,
     `startTime_ = steady_clock::now()`.
  3. `files_ = dirs_ = books_ = matches_ = 0`, `cancel_ = false`, `running_ = true`.
  4. `worker_ = std::thread([this, o = std::move(opt)]() mutable { run(std::move(o)); });`
  `lastNotify_` is not reset.
- `cancel()`: `cancel_ = true` only; it does not wait. `running()` stays true until the worker has finished.
- `wait()`: joins the worker if it is joinable.
- `running()` (header): `running_`, set true by `start` and false by the worker at its very end.

### 7.2 `progress()` and `takeHits()`

- `progress()`: loads `files_`, `dirs_`, `books_`, `matches_` (atomics, outside the lock), then under the lock copies
  `currentDir_`, `finished_`, `cancelled_` and computes `seconds = duration<double>(end - startTime_).count()` with
  `end = finished_ ? endTime_ : steady_clock::now()`. Before the first `start`, `startTime_` is the clock epoch, so
  `seconds` is the time since the steady-clock epoch.
- `takeHits()`: under the lock, swaps `hits_` with an empty vector and returns what was there — the hits found since
  the previous call, in discovery order.

### 7.3 Notification and `pushHit`

- `maybeNotify(force)`: if no callback is set (`notify_` empty) return; if `force` or
  `now - lastNotify_ > std::chrono::milliseconds(120)` (strictly greater), set `lastNotify_ = now` and call
  `notify_()`. It runs on the worker thread only; `setNotify` must be called before `start`. `lastNotify_` starts at
  the clock epoch, so the first call of the first scan always notifies; `start` does not reset it, so the first
  unforced call of a later scan is suppressed if it comes within 120 ms of the previous notification.
- `pushHit(h)`: append to `hits_` under the lock, then `++matches_`, then `maybeNotify(false)`.

`maybeNotify(false)` is called once per directory taken from the stack and once per hit; `maybeNotify(true)` once at
the end of the scan.

### 7.4 `isSkippedDirName(name)` (static)

True when `name` is empty, when its first byte is `'.'` or `'$'`, or when it equals (whole name, `iequalsAscii`) one
of these 21 names, verbatim:

```cpp
static const char* kSkip[] = {"windows",       "program files", "program files (x86)",
                              "programdata",   "system volume information", "recovery",
                              "appdata",       "msocache",      "perflogs",
                              "windowsapps",   "config.msi",    "node_modules",
                              "__pycache__",   "site-packages", "vcpkg_installed",
                              "steamapps",     "onedrivetemp",  "intel",
                              "amd",           "nvidia",        "drivers"};
```

It is applied (when `skipSystemDirs`) to the name of every subdirectory met during the walk, at any depth — never to
the root folders themselves or to the components of their paths (a root under `AppData\Local\Temp` is scanned).

### 7.5 `isNonBookTextName(stem)` (static)

`s = toLowerUtf8(stem)`; true if `s` **contains** any of

```cpp
{"licens", "licenc", "eula", "readme", "read_me", "read me", "changelog", "third-party",
 "third_party", "thirdparty", "copying", "copyright", "credits", "release notes",
 "release_notes", "releasenotes", "requirements"}
```

or **starts with** any of

```cpp
{"install", "setup", "notice", "changes", "version", "log_", "log-"}
```

(`s.rfind(prefix, 0) == 0`); otherwise false. Substring matching is literal (`Eulalia` contains `eula` → true).

### 7.6 `processFile(opt, qm, path, name, size, mtime)`

Called for every regular file whose `name` passes `isSupportedBookName`; `path` is the full UTF-8 path, `name` the
file name.

```
fmt = formatFromName(name)
if size == 0: return
if fmt == Txt and (size < opt.minTxtBytes
                   or (opt.skipNonBookTxt and isNonBookTextName(fileStemOf(name)))): return
++books_
stem    = fileStemOf(name)
offline = opt.skipContent && opt.skipContent(path)
haveRec = cache_.get(path, size, mtime, rec)
```

The size/name filters apply to plain `.txt` only (not to `.txt.zip`, `.fb2.zip`, `.zip`, `.fb2`); only a zero size
excludes every format. `books_` counts the files that pass these filters, before any metadata is read.

`ensureMeta()` (a lambda; makes `rec` valid and tells whether the file is a book):

```
if haveRec: return rec.isBook
rec = MetaRecord{}; rec.size = size; rec.mtime = mtime
if offline:                       // do not trigger a cloud download just for metadata
    rec.title = stem; haveRec = true; return true          // NOT stored in the cache
if loadBookMeta(path, m, &err):
    rec.title = m.title; rec.authors = m.authorsJoined(); rec.series = m.series
    rec.lang = m.lang; rec.format = m.format
else:
    rec.isBook = false
cache_.put(path, rec); haveRec = true
return rec.isBook
```

A cached record (valid size and mtime) is used even for an offline file. A record with `isBook == false` means the
file is never listed until its size or mtime changes.

Matching:

```
matched = 0; hit = {}
if qm.empty():
    matched = kMatchAny
else:
    all = qm.allTermsMask(); mask = 0; flags = 0
    if opt.byFileName:
        m = qm.matchField(stem);           if m: mask |= m; flags |= kMatchName
    if opt.byMeta and mask != all and ensureMeta():
        m = qm.matchField(rec.title);      if m: mask |= m; flags |= kMatchTitle
        m = qm.matchField(rec.authors);    if m: mask |= m; flags |= kMatchAuthor
        m = qm.matchField(rec.series);     if m: mask |= m; flags |= kMatchSeries
    if mask == all: matched = flags
    if not matched and opt.byContent and not offline and not cancel_:
        if loadBookText(path, text, &m, &err):
            if not haveRec:
                rec = MetaRecord{size, mtime, title/authorsJoined/series/lang/format from m}   // isBook true
                cache_.put(path, rec); haveRec = true
            pos = qm.findPhrase(text)
            if pos != npos:
                matched = kMatchText
                hit.snippet = makeSnippet(text, pos, qm.phrase().size())      // radius 70
if not matched: return
if not ensureMeta(): return              // e.g. a .zip that does not contain a book
hit.path = path; hit.size = size; hit.matched = matched
hit.title = rec.title.empty() ? stem : rec.title
hit.authors = rec.authors; hit.series = rec.series; hit.format = rec.format
pushHit(move(hit))
```

Consequences that must be reproduced:

- **All terms must match**, but they may come from different fields: the union of the per-field masks must equal
  `allTermsMask()`. `matched` is then the set of fields that matched at least one term.
- Metadata is read only when the file name did not already match every term (`mask != all`); then all three
  metadata fields are tested (no short-circuit between them). Query `Tolstoy` on `Tolstoy.fb2` gives only
  `kMatchName`; query `tolstoy karenina` on `Tolstoy.fb2` with title `Анна Каренина` and author
  `Лев Николаевич Толстой` gives `kMatchName | kMatchTitle | kMatchAuthor` (7).
- The text is searched only when name and metadata did not match, and only for the whole folded phrase (not for
  separate terms); a content hit has `matched == kMatchText` exactly and carries the snippet. Name/metadata hits have
  an empty snippet. Text that cannot be loaded is simply not matched (nothing is cached for it).
- An offline file (cloud placeholder per `skipContent`): its metadata is not read (title = stem, so with `byMeta` the
  stem is also matched as the title), its text is never searched, nothing is cached for it, and its hit has empty
  authors/series/format — unless a valid cached record exists.
- **Empty query** (`qm.empty()`): every candidate book is listed with `matched == kMatchAny` (32), whatever
  `byFileName`/`byMeta`/`byContent` say; metadata is loaded (or taken from the cache) for each one because of the
  final `ensureMeta()`.
- A matching file whose metadata load fails (`isBook == false`, e.g. an archive without a book) is not listed.
- Archives: this file never opens a zip itself. Names ending in `.zip`, `.fb2.zip` or `.txt.zip` are candidates by
  name alone (no size or name filter except the zero size), their stem loses `.zip` and then `.fb2`/`.txt`, and
  unpacking happens inside `loadBookMeta`/`loadBookText` (whose format strings then end in ` (zip)`, e.g.
  `FB2 (zip)`); an archive without a `.fb2`/`.txt` entry is cached as a non-book.
- `hit.title` falls back to the stem only when the record's title is empty (possible for records loaded from a cache
  file without `ti`); `loadBookMeta`/`loadBookText` already substitute the stem.

### 7.7 `run(opt)` — the worker

1. `const QueryMatcher qm(opt.query);` (built on the worker thread).
2. **Roots** (comment in the source: `// Drop roots nested inside other roots so nothing is scanned twice.`):
   - `norm(p)`: copy byte by byte, `'/'` → `'\\'`, ASCII `A`–`Z` → `a`–`z` (other bytes unchanged), then append
     `'\\'` if the result is empty or does not end with `'\\'`;
   - `roots = opt.roots`, sorted with `std::sort` by byte length ascending (comparator `a.size() < b.size()`);
   - keep a root unless its normalised form starts with the normalised form of an already kept root
     (`n.compare(0, k.size(), k) == 0`) — this drops duplicates and nested roots, while `C:\Books2` is not nested in
     `C:\Books` thanks to the trailing separator. Kept roots keep their original spelling.
3. A stack of `fs::path`: push the kept roots in reverse order (`pathFromUtf8`), so the first kept (shortest) root is
   scanned first.
4. While the stack is not empty and `!cancel_`:
   - pop `dir` from the back; `++dirs_`; under the lock `currentDir_ = pathToUtf8(dir)`; `maybeNotify(false)`;
   - `fs::directory_iterator it(dir, fs::directory_options::skip_permission_denied, ec)`; if `ec`, continue with the
     next stack entry (the directory still counts in `dirs_`; a missing root or a file given as root ends here);
   - iterate while `it != end && !cancel_`; each entry inside `try { … } catch (...) { }` (comment:
     `// Unconvertible names, races with deleted files ... skip the entry.`):
     - `st = e.symlink_status(ec2)`; if `ec2`, ignore the entry. Symbolic links (and junctions or any other type) are
       neither followed nor processed;
     - directory: `name = pathToUtf8(e.path().filename())`; collect `e.path()` in `subdirs` unless
       `opt.skipSystemDirs && isSkippedDirName(name)`;
     - regular file: `++files_` (every regular file counts); `name = pathToUtf8(e.path().filename())`; if
       `isSupportedBookName(name)`: `size = e.file_size(ec2)` (0 on error),
       `mtime = static_cast<int64_t>(e.last_write_time(ec2).time_since_epoch().count())` (0 on error), then
       `processFile(opt, qm, pathToUtf8(e.path()), name, size, mtime)`;
     - after the entry: `it.increment(ec)`; on error stop listing this directory (subdirectories collected so far are
       still scanned);
   - push `subdirs` in reverse order, so they are visited in listing order.
   Result: depth-first pre-order; each directory's files are processed (in the order the OS lists them, no sorting)
   before any of its subdirectories. Hit paths are `pathToUtf8(e.path())`, i.e. the root as given joined with the
   names by `std::filesystem`; the same string is the cache key.
5. Under the lock: `finished_ = true`, `cancelled_ = cancel_.load()` (true if a cancel was requested at any time
   before this point, even after the last directory), `currentDir_.clear()`, `endTime_ = now`.
6. `running_ = false`.
7. `maybeNotify(true)`.

Cancellation is checked before each directory, before each directory entry and before the text search of a file; a
metadata or text load that has started is completed. File modification times are compared only with themselves, so
their tick unit (MSVC: 100 ns since 1601; other standard libraries differ) does not matter.

### 7.8 Progress counters summary

| Counter | Incremented when |
|---------|------------------|
| `dirs` | a directory is taken from the stack (roots included, also when it cannot be opened) |
| `files` | a regular (non-symlink) file is listed, whatever its name |
| `books` | a supported book name passed the zero-size and `.txt` filters |
| `matches` | a hit is pushed |

---

## 8. What the callers rely on

- `App` creates one `MetaCache`, loads it from `<prefDir>library-cache.json` at start-up, creates one
  `LibrarySearch` on it and calls `setNotify` (waking the event loop) before any search. It saves the cache when it
  notices that a search has stopped and whenever it saves its own state (settings and reading position); at
  shutdown it calls `cancel()` and `wait()`. A `save` while the worker runs is safe (section 6.5).
- `App::startLibrarySearch` fills `SearchOptions` from the settings: query, roots, `byFileName`, `byMeta`,
  `byContent`, `skipSystemDirs`, `minTxtBytes = ignoreTinyTxt ? 16 * 1024 : 1`, `skipNonBookTxt = ignoreTinyTxt`,
  `skipContent = platform::isCloudPlaceholder` (Windows: the file has `FILE_ATTRIBUTE_OFFLINE`,
  `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` or `FILE_ATTRIBUTE_RECALL_ON_OPEN`; other platforms: never). Each frame it
  moves `takeHits()` into its list, shows `progress()` (`dirs`, `files`, `books`, `currentDir`, `seconds`,
  `cancelled`), and the Stop button calls `cancel()`.
- `App::runFind` (search inside the open book) uses `QueryMatcher(findQuery)`: skips when `phrase()` is empty, calls
  `findPhrase` per block, gets the match length in original bytes with
  `originalOffsetForFolded(text.substr(pos), phrase().size())` (at least 1) and builds the snippet with
  `makeSnippet(text, pos, length, 60)`.

---

## 9. Tests that constrain this part (`tests/core_tests.cpp`)

- `testMatching`
  - `translitSkeleton(foldForSearch("Толстой"))` equals the skeletons of `tolstoy` and `Tolstoj` (table entries
    т о л с й, rules `y`/`j` → `i`, built-in lower-casing); `Достоевский` = `Dostoevsky` (`ий` → `ii` → collapse);
    `Цветаева` = `Tsvetaeva` (`ts` → `c`); `Чехов` = `Chekhov` (`kh` → `h`, `ch` kept).
  - `QueryMatcher("толстой каренина")`: `termCount() == 2`;
    `matchField("Tolstoy_Anna-Karenina.fb2") == allTermsMask()` (skeleton fallback; `_`, `-`, `.` become spaces;
    `nn` collapses); `matchField("Лев Толстой") == 1u` (literal match, bit order);
    `matchField("Something else") == 0u`.
  - `QueryMatcher("счастливые семьи").findPhrase("Все  СЧАСТЛИВЫЕ\nсемьи похожи")` equals the byte offset of
    `СЧАСТЛИВЫЕ` (8): white-space collapsing, case folding, offset mapping.
  - `makeSnippet(text, pos, 10, 5)` contains `СЧАСТЛИВЫЕ` (window grows by code points beyond `pos + matchLen`).
  - `QueryMatcher("").empty()`.
  - `isNonBookTextName`: `LICENSE`, `grid-third-party-licenses`, `ReadMe`, `InstallLog` → true; `Война и мир`,
    `Pride and Prejudice` → false.
- `testLibrarySearch` (temporary folder with `Загрузки/book1.fb2` in windows-1251,
  `Загрузки/deep/Неизвестный - Записки.txt` in KOI8-R (> 16 KiB), `small.txt` (4 bytes), `node_modules/hidden.fb2`,
  `Tolstoy_Anna.fb2.zip`; one shared `MetaCache`, a new `LibrarySearch` per run, `start` + `wait`,
  `progress().finished` must be true):
  - empty query → exactly 3 hits (`node_modules` skipped, the tiny `.txt` ignored, the zip included);
  - `толстой` → 2 hits, each with `kMatchAuthor` or `kMatchName` (author of the FB2; skeleton match of the zip's stem
    `Tolstoy_Anna`);
  - `записки` with `byMeta = false` → 1 hit (file-name match);
  - `уникальная фраза для поиска` with `byContent = true` → 1 hit with `matched == kMatchText` and a snippet
    containing `Уникальная фраза` (original case);
  - `zzzqqq` with `byContent = true` → no hit (no name, field or text contains it; its skeleton `zk` is shorter than
    3, so skeleton matching is not even tried);
  - afterwards `cache.size() >= 3`, `save` returns true, a fresh `MetaCache::load` returns true with the same size.

## Checklist

Transliteration:

- `translitSkeleton("Толстой")`, `("tolstoy")`, `("Tolstoj")` → `tolstoi`.
- `("Достоевский")`, `(foldForSearch("Dostoevsky"))` → `dostoevski`; `("Цветаева")`, `("Tsvetaeva")` → `cvetaeva`.
- `("Чехов")`, `("Chekhov")` → `chehov`; `("Щука")`, `("Shchuka")` → `shuka`; `("Хрущёв")`, `("Khrushchev")` →
  `hrushev`; `("Царь")`, `("Tsar")` → `car`; `("Юрий")`, `("Yuri")`, `("Jurij")` → `iuri`.
- `("  Hello,   World! ")` → `helo world`; `("100")` → `10`; `("Deutsch")` → `deuch`; `("Philipp")` → `filip`;
  `("Bock")` → `bok`; `("Alexander")` → `aleksander`; `("straße")` → `stra?e`; `("αθηνα")` → `?`; `("")` → `""`.

Query matcher:

- `QueryMatcher("  «Война»   и  мир! ")` → `termCount() == 3` (`война`, `и`, `мир`), `phrase() == "\"война\" и мир!"`.
- `QueryMatcher("--")` → `empty()`, `phrase() == "--"`; `QueryMatcher("a — b").termCount() == 2`.
- 40 words → `termCount() == 32`, `allTermsMask() == 0xFFFFFFFF`; 3 words → `allTermsMask() == 7`.
- `QueryMatcher("ёж").matchField("Ezh") == 1` (skeleton `ezh`, length 3);
  `QueryMatcher("ой").matchField("oi") == 0` (skeleton `oi` too short);
  `QueryMatcher("мир").matchField("Мирный") == 1`; `QueryMatcher("Tolstoy").matchField("Толстой") == 1`;
  `matchField("") == 0`.
- `QueryMatcher("ab").findPhrase("xAB") == 1`; `QueryMatcher("елка").findPhrase("Ёлка") == 0`;
  `QueryMatcher("hello world").findPhrase("hello, world") == npos`; `QueryMatcher("").findPhrase("x") == npos`;
  `QueryMatcher("перенос").findPhrase("пере\u00ADнос") == 0` (soft hyphen ignored).

Offsets and snippets:

- `originalOffsetForFolded("a\xC2\xADb", 1) == 3`; `("Ab", 5) == 2`; `("\xC2\xABx\xC2\xBB", 1) == 2`;
  `("a  b", 2) == 3`; `("abc", 0) == 0`.
- `makeSnippet("abcdef", 2, 1, 1) == "…bcd…"`;
  `makeSnippet("Все  СЧАСТЛИВЫЕ\nсемьи похожи", 8, 10, 5) == "Все СЧАСТЛИВЫЕ…"`;
  `makeSnippet("a\n\nb", 0, 1) == "a b"`; `makeSnippet("abc", 10, 1, 1) == "…c"`.

Metadata cache:

- `put("p", {size 5, mtime 7, title "T"})`; `get("p", 5, 7, r)` → true, `r.title == "T"`, `r.isBook`;
  `get("p", 5, 8, r)` → false; `get("p", 6, 7, r)` → false; `get("q", 5, 7, r)` → false.
- After that `save(f)` writes exactly `{"files":{"p":{"s":5,"t":7,"ti":"T"}},"version":1}` and returns true; a
  record with `isBook = false` and no strings is written as `{"b":false,"s":5,"t":7}`.
- `save` on a cache with nothing new → true, no file written.
- `load` of `{"files":{"p":{"s":5,"t":7}}}` → true, record with `isBook == true` and empty strings, `size() == 1`.
- `load` of `[]`, `{"files":[]}`, `{}`, `not json`, or a missing file → false, map unchanged.
- `load` of `{"files":{"a":{"s":1,"t":1},"b":{"s":"x"}}}` → false, and the map then holds only `a`.

Scanner:

- `isSkippedDirName`: `""`, `".git"`, `"$Recycle.Bin"`, `"Windows"`, `"WINDOWS"`, `"Program Files (x86)"`,
  `"Node_Modules"`, `"Intel"`, `"drivers"` → true; `"Books"`, `"windows.old"`, `"Загрузки"` → false.
- `isNonBookTextName`: `"LICENSE"`, `"ReadMe"`, `"InstallLog"`, `"Setup_Guide"`, `"Log_2020"`, `"Versions of me"`,
  `"Eulalia"`, `"My changelog"`, `"Credits"` → true; `"Catalog-1"`, `"The Notice"`, `"Война и мир"` → false.
- Roots `{"C:\\A", "c:/a/b"}` → only `C:\A` is scanned; `{"C:\\Books", "C:\\Books2"}` → both; a non-existent root →
  finished with `dirs == 1`, `files == 0`.
- A 20 KiB `LICENSE.txt` counts in `files` but not in `books`; a 100-byte `a.txt` is ignored with the default
  `minTxtBytes` (16384) and processed with `minTxtBytes = 1`; a 0-byte `x.fb2` never counts as a book.
- Empty query → every listed hit has `matched == 32` and an empty snippet.
- `Tolstoy.zip` without a book inside, query `tolstoy` → no hit; the cache gets a record with `isBook == false`.
- Query `tolstoy karenina`, file `Tolstoy.fb2` (title `Анна Каренина`, author `Лев Николаевич Толстой`) →
  `matched == 7`; query `Tolstoy` on the same file → `matched == kMatchName` (1).
- `notify_` is called at most once per 120 ms during the scan, plus once (forced) at the end; after `wait()`,
  `running() == false` and `progress().finished == true`; `cancel()` during a scan → once the worker has finished,
  `progress().finished == true` and `progress().cancelled == true`, and `progress().seconds` stays constant.
