# 05 — Hyphenation (Liang) and line breaking (Knuth–Plass)

**Scope.** This part specifies two implementation files: `src/core/Hyphenator.cpp` (Frank Liang's TeX pattern
hyphenation: `Hyphenator`, `HyphenationService`) and `src/core/LineBreaker.cpp` (paragraph line breaking on the
abstract box/glue/penalty model: `breakLinesOptimal` = Knuth–Plass "total fit", `breakLinesGreedy` = first fit,
`lbLineWidth`, `lbStats`). Their declarations are in `src/core/Hyphenator.h` and `src/core/LineBreaker.h`, which the
implementer has verbatim; they are referred to by name and not repeated. The Unicode helpers used here
(`utf8Decode`, `trimView`, `isSpaceCp`, `toLowerCp`, `isCyrillicCp`, `isLatinLetterCp`) are declared in
`src/core/Unicode.h` and specified with `Unicode.cpp` in another part. Both files are pure computation: no I/O, no
threads, no global state apart from the `lbStats()` counters. Their callers (`App::loadHyphenation` in `App.cpp`, the
paragraph layout in `BookLayout.cpp`) are specified elsewhere; only the contracts they rely on are restated here.

---

## 1. `src/core/Hyphenator.cpp`

### 1.1 File layout

```
#include "core/Hyphenator.h"

#include <algorithm>

#include "core/Unicode.h"

namespace ll {
namespace { edgeKey }              // file-local helper
Hyphenator::child
Hyphenator::load
Hyphenator::hyphenate
HyphenationService::hyphenate
}  // namespace ll
```

The only comment in the file is the one on the early return in `HyphenationService::hyphenate`
(`// digits / other scripts: leave the word alone`).

### 1.2 The trie

Patterns are stored in a trie of integer nodes. Node 0 is the root; it exists after every `load`.

- `values_[node]` — index into `pool_` of the digit vector of the pattern that ends at `node`, or `-1` when no
  pattern ends there. `values_.size()` is the number of nodes; a new node gets the index `values_.size()` and the
  value `-1`.
- `edges_` — maps an edge key to the child node index. The key packs the parent node and the code point
  (code points need at most 21 bits):

  ```cpp
  uint64_t edgeKey(int node, char32_t c) { return (static_cast<uint64_t>(node) << 21) | static_cast<uint64_t>(c); }
  ```

- `child(node, c)` — finds `edgeKey(node, c)` in `edges_`; returns the child index, or `-1` if there is no such edge.
- `pool_` — digit vectors. A pattern of k letters owns a vector of k + 1 values: entry j is the digit written
  immediately before letter j, entry k the digit after the last letter; positions without a digit hold 0.
- `exceptions_` — lower-cased word → list of allowed break positions.

### 1.3 Input format accepted by `load`

Both texts are UTF-8 and are decoded with `utf8Decode` (a malformed byte becomes U+FFFD and is then treated like
any other character). Processing is line based and identical for both texts:

- Lines are separated by `'\n'` only. Each line is trimmed with `trimView` (ASCII space, tab, CR and LF, and the
  UTF-8 NBSP sequence `C2 A0`, at both ends), so CRLF files load the same as LF files.
- An empty trimmed line is ignored. A trimmed line whose first byte is `'%'` is ignored (TeX comment). A `'%'` in
  any other position is not a comment; it is an ordinary character of the line.
- There is no other syntax: no `\patterns{…}` wrapper, no braces, no `\hyphenation` keyword (such text would be read
  as pattern letters).

**Pattern line.** Code point by code point:

- `'0'`…`'9'`: sets the digit of the current inter-letter position (the position after the letters read so far).
  A second digit at the same position overwrites the first: `a12b` is the same as `a2b`.
- White space (`isSpaceCp`) anywhere inside the line is skipped. Consequently several space-separated patterns on
  one line merge into a single pattern (`a1b c1d` is the one pattern `abcd` with digits 0,1,0,1,0).
- Every other code point is a pattern **letter**, lower-cased with `toLowerCp`. This includes `'.'` (the word-edge
  marker, see 1.5), `'-'`, apostrophes, and a U+FEFF byte-order mark if a file started with one.
- A line that yields no letter (for example only digits) is ignored and not counted.

**Exception line.** Code point by code point:

- `'-'` (U+002D only) records a break position equal to the number of letters read so far.
- White space is skipped (so words separated by spaces merge into one word).
- Every other code point, digits included, is a letter, lower-cased with `toLowerCp`.
- A line without letters is ignored. A word without any `'-'` is stored with an empty break list, which means
  "never hyphenate this word". A later line with the same word replaces the earlier entry.

**The shipped files** (`assets/hyphenation/`, unmodified hyph-utf8 files: LF line endings, no BOM, no comments, no
blank lines, one entry per line):

| File | Entries | Characters that occur |
|------|---------|-----------------------|
| `hyph-en-us.pat.txt` | 4938 patterns | `a`–`z`, `.`, digits `1`–`6` |
| `hyph-en-us.hyp.txt` | 14 lines (`present`, `presents`, `project`, `projects` have no `-`) | `a`–`z`, `-` |
| `hyph-ru.pat.txt` | 7021 patterns | Cyrillic `а`–`я`, `ё`, `.`, `-`, digits `1`–`8` |
| `hyph-ru.hyp.txt` | 184 lines (e.g. `бездн`, `вопль` have no `-`) | lower-case Cyrillic letters, `-` |

`hyph-ru.pat.txt` contains a block of patterns that include `-` as a letter (`8-7`, `--8`, `.а-8`, `-а8а8`,
`8а8а-`, …). They are loaded like any other pattern (they add trie nodes and are counted by `patternCount()`), but
since `HyphenationService` never passes a word containing `-` (it rejects every non-letter), they never match in
the application.

### 1.4 `Hyphenator::load(patterns, exceptions, leftMin, rightMin)`

1. Reset everything: `edges_.clear()`, `values_.assign(1, -1)` (root only, no value), `pool_.clear()`,
   `exceptions_.clear()`, `patternCount_ = 0`, `leftMin_ = leftMin`, `rightMin_ = rightMin` (stored as given, not
   validated). A failed load therefore leaves an empty hyphenator, never the previous state.
2. Iterate the lines of `patterns` with this helper (also used for the exceptions):

   ```cpp
   auto forEachLine = [](std::string_view text, auto&& fn) {
     size_t i = 0;
     while (i < text.size()) {
       size_t e = text.find('\n', i);
       if (e == std::string_view::npos) e = text.size();
       std::string_view line = trimView(text.substr(i, e - i));
       if (!line.empty() && line[0] != '%') fn(line);
       i = e + 1;
     }
   };
   ```

3. For each pattern line, split letters and digits:

   ```cpp
   std::u32string letters;
   std::vector<uint8_t> digits(1, 0);
   for (size_t i = 0; i < line.size();) {
     const char32_t c = utf8Decode(line, i);
     if (c >= U'0' && c <= U'9') {
       digits.back() = static_cast<uint8_t>(c - U'0');
     } else if (!isSpaceCp(c)) {
       letters.push_back(toLowerCp(c));
       digits.push_back(0);
     }
   }
   if (letters.empty()) return;   // line ignored, not counted
   ```

   `digits.size()` is always `letters.size() + 1`.
4. Insert into the trie: start at node 0; for each letter, take `child(node, c)`; if it is `-1`, create the node
   (`next = values_.size()`, `values_.push_back(-1)`, `edges_.emplace(edgeKey(node, c), next)`); move to it.
5. At the final node:
   - if `values_[node] < 0`: `values_[node] = pool_.size()` and the digit vector is moved into `pool_`;
   - otherwise (the same letter sequence was seen before) merge element-wise by maximum:
     `v[k] = std::max(v[k], digits[k])` for `k < min(v.size(), digits.size())` (the sizes are equal anyway).
6. `++patternCount_` for every accepted line, duplicates included (so the count is the number of non-ignored
   lines: 4938 for `hyph-en-us.pat.txt`, 7021 for `hyph-ru.pat.txt`).
7. Iterate the lines of `exceptions`:

   ```cpp
   std::u32string word;
   std::vector<int> breaks;
   for (size_t i = 0; i < line.size();) {
     const char32_t c = utf8Decode(line, i);
     if (c == U'-') {
       breaks.push_back(static_cast<int>(word.size()));
     } else if (!isSpaceCp(c)) {
       word.push_back(toLowerCp(c));
     }
   }
   if (!word.empty()) exceptions_[word] = std::move(breaks);
   ```

   The break list keeps file order, including a position 0 for a leading `-` and duplicates for `--`.
8. Return `patternCount_ > 0`. Exceptions are stored even when no pattern was loaded, but they are then never used
   (see 1.5, step 1).

### 1.5 `Hyphenator::hyphenate(word, breaks)`

Contract: `word` must already be lower case (trie letters and exception keys are lower case; an upper-case letter
simply finds no pattern). Positions are **appended** to `breaks`, which is never cleared. A position `pos` means "a
hyphen may be inserted between `word[pos-1]` and `word[pos]`".

1. `n = word.size()` (code points). If `n < leftMin_ + rightMin_` or `patternCount_ == 0`, return without appending.
2. Exception lookup by exact match of the whole word (`exceptions_.find(std::u32string(word))`). If found: append
   every stored position `b` with `b >= leftMin_ && b <= n - rightMin_`, in stored order, and **return** — patterns
   are not consulted for that word (an empty list therefore suppresses hyphenation).
3. Build `s = U"." + word + U"."` (`len = n + 2`) and `levels`, `len + 1` bytes of 0. `levels[x]` is the value of the
   gap before `s[x]`. Apply every matching pattern:

   ```cpp
   for (int i = 0; i < len; ++i) {
     int node = 0;
     for (int j = i; j < len; ++j) {
       node = child(node, s[j]);
       if (node < 0) break;
       const int vi = values_[node];
       if (vi >= 0) {
         const std::vector<uint8_t>& v = pool_[vi];
         for (size_t k = 0; k < v.size(); ++k) {
           uint8_t& lv = levels[static_cast<size_t>(i) + k];
           if (v[k] > lv) lv = v[k];
         }
       }
     }
   }
   ```

   Every start position `i` (including the leading and trailing `'.'`) is tried, and every prefix of the walk that
   ends a pattern contributes; values combine by maximum. Patterns beginning with `'.'` can only match at `i = 0`,
   patterns ending with `'.'` only at the end of the word.
4. Emit odd gaps in ascending order:

   ```cpp
   for (int pos = leftMin_; pos <= n - rightMin_; ++pos) {
     if (levels[static_cast<size_t>(pos) + 1] & 1) breaks.push_back(pos);
   }
   ```

   (`levels[pos + 1]` is the gap between `s[pos] = word[pos-1]` and `s[pos+1] = word[pos]`.)

leftMin/rightMin are applied only in these three places (the length test in step 1, the exception filter in step 2,
the loop bounds in step 4); there is no other clamping.

### 1.6 `HyphenationService::hyphenate(letters, breaks)`

Chooses the hyphenator by script and lower-cases the word:

```cpp
if (letters.size() < 4) return;
bool cyr = false, lat = false;
for (char32_t c : letters) {
  if (isCyrillicCp(c)) cyr = true;
  else if (isLatinLetterCp(c)) lat = true;
  else return;  // digits / other scripts: leave the word alone
}
if (cyr == lat) return;
std::u32string lower(letters);
for (char32_t& c : lower) c = toLowerCp(c);
(cyr ? ru_ : en_).hyphenate(lower, breaks);
```

- Fewer than 4 code points: nothing (this test comes before the hyphenator's own `leftMin + rightMin` test).
- Any code point that is neither Cyrillic (`isCyrillicCp`: U+0400–U+0481, U+048A–U+052F, U+1C80–U+1C88,
  U+A640–U+A69F) nor Latin (`isLatinLetterCp`: ASCII letters, U+00C0–U+024F except × and ÷, U+1E00–U+1EFF) — a
  digit, apostrophe, hyphen, combining mark, Greek letter … — leaves the whole word unhyphenated.
- A word mixing both scripts (`cyr && lat`) is left alone.
- All-Cyrillic words (Russian, but also Ukrainian/Belarusian letters such as і ї є ґ ў) use `russian()`; all-Latin
  words (also with accented letters, which simply match no English pattern) use `english()`.
- Results are those of `Hyphenator::hyphenate`: appended positions, indices into `letters`.

### 1.7 What the callers rely on

- `App::loadHyphenation` loads `hyphenation/hyph-en-us.pat.txt` + `hyphenation/hyph-en-us.hyp.txt` into
  `english()` with leftMin 2, rightMin 3, and `hyphenation/hyph-ru.pat.txt` + `hyphenation/hyph-ru.hyp.txt` into
  `russian()` with 2, 2 (the values listed in `assets/hyphenation/README.md`); it only logs when `load` returns
  false.
- `BookLayout` calls `HyphenationService::hyphenate` only when the block style allows hyphenation, for words of at
  least 5 bytes that contain no soft hyphen and are not web addresses, once per run of at least 5 letters
  (classified by `isLetterCp`, original case; combining marks after a letter neither join nor end the run). It clears
  its result vector before each call and turns every returned position p into a hyphenation break before letter p
  of the run.
- `Hyphenator::hyphenate` and `HyphenationService::hyphenate` are `const` and use only local state, so concurrent
  calls are safe once loading is finished; `load` must not run concurrently with them.

---

## 2. `src/core/LineBreaker.cpp`

### 2.1 File layout

```
#include "core/LineBreaker.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace ll {
namespace { kInf, isLegalBreak, isForced }   // file-local
lbStats
lbLineWidth
breakLinesOptimal
breakLinesGreedy
}  // namespace ll
```

All arithmetic inside both algorithms is done in `double` (item fields are `float` and are widened); only the
ratio stored in `LbBreak::ratio` is narrowed back to `float`. `LbItem::tag` is never read here. `stretch`/`shrink`
are read only from glue items; `penalty`/`flagged` only from penalty items.

### 2.2 File-local helpers

```cpp
constexpr double kInf = std::numeric_limits<double>::infinity();

bool isLegalBreak(const std::vector<LbItem>& items, int b) {
  const LbItem& it = items[b];
  if (it.type == LbItem::Glue) return b > 0 && items[b - 1].type == LbItem::Box && it.stretch < kLbFillStretch;
  if (it.type == LbItem::Penalty) return it.penalty < kLbInfPenalty;
  return false;
}

bool isForced(const LbItem& it) { return it.type == LbItem::Penalty && it.penalty <= -kLbInfPenalty; }
```

Consequences: a glue is a break only directly after a box — glue after glue or after a penalty is never a break
(a caller forbids the break at a space by putting a penalty ≥ `kLbInfPenalty` before the glue: that penalty is
illegal and makes the glue illegal too); the paragraph-final fill glue (stretch ≥ `kLbFillStretch`) is never a
break; every penalty below `kLbInfPenalty` is a break, forced ones included; a box never is.

### 2.3 `lbStats()`

Returns a reference to a function-local `static LbStats` (all counters 0 at first use). The counters are plain,
non-atomic `uint64_t`s and are never reset by this module:

- `optimalOk` — incremented when `breakLinesOptimal` succeeds on a non-empty item list;
- `optimalFail` — incremented every time `breakLinesOptimal` returns false;
- `greedy` — incremented on every `breakLinesGreedy` call, also for an empty item list.

`breakLinesOptimal` with an empty list touches no counter.

### 2.4 `lbLineWidth(widths, line)`

```cpp
if (widths.empty()) return 1e9f;
return widths[std::min<size_t>(static_cast<size_t>(std::max(line, 0)), widths.size() - 1)];
```

The line index is clamped to `[0, size-1]`: the last width applies to every later line, a negative index gives the
first width, and an empty vector means "practically unlimited" (`1e9f`).

### 2.5 `breakLinesOptimal(items, lineWidths, p, out)`

Contract: on success returns true and fills `out` with one `LbBreak` per line, in paragraph order; `item` is the
index of the glue or penalty at which the line ends, `ratio` the adjustment ratio of that line. On failure returns
false and leaves `out` empty. The last break of a successful result is always the last item (`n - 1`).

**Step 0.** `out.clear()`; `n = items.size()`; if `n == 0` return true (empty `out`, no counter touched).

**Step 1 — prefix sums** (vectors of `n + 1` doubles, element 0 = 0):

```cpp
sw[i + 1] = sw[i] + (it.type != LbItem::Penalty ? it.width : 0.0);   // boxes and glue
sy[i + 1] = sy[i] + (it.type == LbItem::Glue ? it.stretch : 0.0);
sz[i + 1] = sz[i] + (it.type == LbItem::Glue ? it.shrink : 0.0);
```

`sw[b]` is the natural width of items `0 … b-1`; penalty widths never enter the sums.

**Step 2 — breakpoint nodes.** A local struct, fields in this order:

```cpp
struct Node {
  int pos;
  int line;
  int fitness;
  double tw, ty, tz;
  double demerits;
  int prev;
  float ratio;
};
```

| Field | Meaning |
|-------|---------|
| `pos` | item index of the break; −1 for the paragraph start |
| `line` | number of lines before the line that starts here (index passed to `lbLineWidth` for that line) |
| `fitness` | fitness class (0…3) of the line that ends here |
| `tw`, `ty`, `tz` | `sw`/`sy`/`sz` values where the next line starts (after discarding, see step 5) |
| `demerits` | total demerits from the paragraph start to here |
| `prev` | index of the predecessor node, −1 for the start |
| `ratio` | adjustment ratio of the line that ends here (`float`) |

All nodes live in a `std::vector<Node> nodes` (reserved to `n / 2 + 8`, performance only) and are never removed
from it. The start node is `Node{-1, 0, 1, 0, 0, 0, 0, -1, 0}` — note its fitness class 1 ("decent"). A separate
`std::vector<int> active` holds the indices of the active nodes; it starts as `{0}`. Its order matters for ties: it
is the creation order of the surviving nodes.

**Step 3 — scan.** For `b = 0 … n-1`, skip `b` unless `isLegalBreak(items, b) || isForced(items[b])` (the second
term is redundant: forced penalties are legal). Let `it = items[b]` and `forced = isForced(it)`. Prepare four
candidate slots, one per fitness class: `struct Cand { double d = kInf; int node = -1; double r = 0; } cand[4];`.

**Step 4 — try every active node.** Iterate `active` with an index `ai`, erasing in place:

```cpp
for (size_t ai = 0; ai < active.size();) {
  const Node& a = nodes[active[ai]];
  double L = sw[b] - a.tw;
  if (it.type == LbItem::Penalty) L += it.width;
  const double W = lbLineWidth(lineWidths, a.line);
  double r;
  if (L < W) {
    const double Y = sy[b] - a.ty;
    r = Y > 1e-9 ? (W - L) / Y : kInf;
  } else if (L > W) {
    const double Z = sz[b] - a.tz;
    r = Z > 1e-9 ? (W - L) / Z : -kInf;
  } else {
    r = 0;
  }
  const bool deactivate = r < -1 || forced;
  if (r >= -1 && r <= p.tolerance) {
    const double bad = 100.0 * std::pow(std::fabs(r), 3.0);
    const double base = p.linePenalty + bad;
    double d = base * base;
    if (it.type == LbItem::Penalty && !forced) {
      if (it.penalty >= 0) d += double(it.penalty) * it.penalty;
      else d -= double(it.penalty) * it.penalty;
    }
    if (it.type == LbItem::Penalty && it.flagged && a.pos >= 0 && items[a.pos].type == LbItem::Penalty &&
        items[a.pos].flagged)
      d += p.flaggedDemerits;
    const int fc = r < -0.5 ? 0 : (r <= 0.5 ? 1 : (r <= 1.0 ? 2 : 3));
    if (std::abs(fc - a.fitness) > 1) d += p.fitnessDemerits;
    d += a.demerits;
    if (d < cand[fc].d) cand[fc] = Cand{d, active[ai], r};
  }
  if (deactivate) {
    active.erase(active.begin() + static_cast<std::ptrdiff_t>(ai));
  } else {
    ++ai;
  }
}
```

In words:

- **Line length.** `L` = natural width from the start of the line to the break: the glue at a glue break is not
  part of the line (`sw[b]` stops before it); the width of a penalty break (a hyphen) is added.
  `W = lbLineWidth(lineWidths, a.line)`.
- **Adjustment ratio.** Stretching (`L < W`): `r = (W - L) / Y` with `Y` the stretch of the glue inside the line;
  if `Y <= 1e-9`, `r = +∞`. Shrinking (`L > W`): `r = (W - L) / Z`; if `Z <= 1e-9`, `r = -∞`. Exact fit: `r = 0`
  regardless of stretch/shrink. The fill glue's huge stretch makes the last line's `r` tiny.
- **Deactivation.** The node is removed from `active` (after being considered) when `r < -1` (the line is already
  over-full, and any later break would be worse) or when the breakpoint is forced (no line may span a forced break).
  An `r = +∞` (too loose, no stretch) node stays active.
- **Tolerance test (feasibility).** Only `-1 <= r <= p.tolerance` (both inclusive) produces a candidate.
- **Badness** `bad = 100·|r|³` — no upper cap.
- **Demerits** `d = (linePenalty + bad)²`; for a non-forced penalty break add `penalty²` when `penalty >= 0`, subtract
  `penalty²` when it is negative; forced breaks add nothing for the penalty.
- **Flagged demerits.** `+ flaggedDemerits` when the break is a flagged penalty and the previous break (`a.pos`) is
  also a flagged penalty. This also applies when the current break is the forced final penalty and that penalty is
  flagged (both `BookLayout` and the tests use a flagged final penalty), so a hyphen at the end of the second-to-last
  line costs `flaggedDemerits` once more. The paragraph start (`a.pos = -1`) is never flagged.
- **Fitness classes**: 0 = tight (`r < -0.5`), 1 = decent (`-0.5 <= r <= 0.5`), 2 = loose (`0.5 < r <= 1.0`),
  3 = very loose (`r > 1.0`). `+ fitnessDemerits` when the classes of this line and of the previous line (`a.fitness`)
  differ by more than 1. The start node counts as class 1, so only a very loose first line pays it.
- **Total** `d += a.demerits`.
- **Candidate per class.** The slot of class `fc` keeps the node with the strictly smallest total; on equal totals
  the node met first in `active` order wins. Candidates are kept per fitness class only, not per line number.

**Step 5 — new active nodes.** If at least one slot has `node >= 0`, compute the totals where the next line starts —
glue and non-forced penalties directly after the break vanish:

```cpp
double tw = sw[b], ty = sy[b], tz = sz[b];
for (int i = b; i < n; ++i) {
  const LbItem& x = items[i];
  if (x.type == LbItem::Box) break;
  if (x.type == LbItem::Glue) {
    tw += x.width;
    ty += x.stretch;
    tz += x.shrink;
  } else if (isForced(x) && i > b) {
    break;
  }
}
```

The scan starts at the break item itself (so the breaking glue is discarded), skips glue and non-forced penalties,
and stops at the first box or at a forced penalty after `b` (the item at `b` itself never stops it). The source puts
this comment above the loop:

```cpp
      // Totals after the break: discardable items (glue, penalties) at the start of the next line vanish.
```

Then, for `fc = 0, 1, 2, 3` with `cand[fc].node >= 0`, append

```cpp
Node{b, nodes[cand[fc].node].line + 1, fc, tw, ty, tz, cand[fc].d, cand[fc].node, static_cast<float>(cand[fc].r)}
```

to `nodes` and its index to the end of `active`. At most four nodes are created per breakpoint, in class order.

**Step 6 — failure during the scan.** After steps 4–5 of every examined breakpoint: if `active` is empty,
`++lbStats().optimalFail` and return false. This happens when every active node was deactivated (over-full lines,
or a forced break) and no feasible candidate created a new node — for example a box wider than the line, or a
forced break that no feasible line can reach.

**Step 7 — result.** After the scan, pick among the active nodes those with `pos == n - 1`, and among them the one
with the smallest `demerits` (strict `<`; the first in `active` order wins ties). If there is none,
`++lbStats().optimalFail` and return false (this happens when the last item is not a legal break, or is a non-forced
break that no feasible line reached). Otherwise trace back:

```cpp
for (int k = best; k > 0; k = nodes[k].prev) out.push_back(LbBreak{nodes[k].pos, nodes[k].ratio});
std::reverse(out.begin(), out.end());
++lbStats().optimalOk;
return true;
```

The start node (index 0) produces no entry.

Behaviour an implementer familiar with TeX must reproduce rather than "fix": badness is not capped at 10000; the
fitness classes are numbered tight→very loose as 0→3; fitness demerits apply when classes differ by more than one;
candidates are not separated by line number even when `lineWidths` has several entries; there is no looseness, no
emergency stretch and no second pass inside this function (the caller retries with a larger tolerance and falls back
to `breakLinesGreedy`).

### 2.6 `breakLinesGreedy(items, lineWidths, out)`

Contract: first fit, always returns at least one break for a non-empty list (none for an empty one). Breaks have the
same meaning as in 2.5.

```
out.clear(); ++lbStats().greedy;
n = items.size(); start = 0; line = 0;
while (start < n) {
  W = lbLineWidth(lineWidths, line)   (double); w = 0; lastBreak = -1;
  scan (below) → lastBreak
  if (lastBreak < 0) fallback (below)
  ratio (below); out.push_back(LbBreak{lastBreak, float(r)});
  start = lastBreak + 1;
  while (start < n && items[start].type != LbItem::Box && !isForced(items[start])) ++start;
  if (isForced(items[lastBreak])) break;
  ++line;
}
```

The scan of one line, verbatim:

```cpp
for (; b < n; ++b) {          // b starts at `start`
  const LbItem& it = items[b];
  if (it.type == LbItem::Box) {
    w += it.width;
    if (w > W + 0.01 && lastBreak >= 0) break;
  } else if (it.type == LbItem::Glue) {
    if (isLegalBreak(items, b) && b > start && w <= W + 0.01) lastBreak = b;
    w += it.width;
  } else if (isForced(it)) {
    if (w <= W + 0.01 || lastBreak < 0) lastBreak = b;
    break;
  } else if (it.penalty < kLbInfPenalty && b > start && w + it.width <= W + 0.01) {
    lastBreak = b;
  }
}
```

- The fitting slack is `0.01` (absolute) everywhere.
- A glue break is remembered if the content before the glue fits (the glue's own width is added afterwards); a
  non-forced penalty break if the content plus the penalty width fits. Neither may be the first item of the line
  (`b > start`). Penalties ≥ `kLbInfPenalty` and illegal glue (fill glue, glue not preceded by a box) are never
  remembered; illegal glue still adds its width to `w`. Penalty widths are never added to `w`.
- A box that overflows ends the scan only if a break was already remembered.
- A forced penalty always ends the scan; it becomes the break if the content fits or if nothing was remembered,
  otherwise the remembered break wins and the forced penalty is reached again on a later line.
- Odd but exact: if the first box(es) of a line do not fit, no later glue or penalty can satisfy the fit test, so
  nothing is remembered until the forced penalty — **the entire rest of the paragraph becomes one over-full line**
  ending at the forced break.

Fallback, used only when the scan ran off the end of the list without remembering a break (i.e. no forced penalty was
reached). It sits inside `if (lastBreak < 0) { … }`, whose first line is the comment shown:

```cpp
// Even the first box does not fit: overflow up to the next legal break.
for (int k = start; k < n; ++k) {
  if ((isLegalBreak(items, k) && k > start) || isForced(items[k])) {
    lastBreak = k;
    break;
  }
}
if (lastBreak < 0) lastBreak = n - 1;
```

Without a final forced penalty the last line also behaves unusually: the scan runs off the end with a remembered
glue, so the line ends at that glue even though everything fits, and the remainder becomes one more line that ends
at the fallback break (`n - 1` if nothing else qualifies).

Ratio of the line (preceded in the source by the comment `// Adjustment ratio for justification.`): over the items
from `start` to `lastBreak - 1`, `L` = widths of boxes and glue, `Y`/`Z` = glue stretch/shrink; if
`items[lastBreak]` is a penalty, add its width to `L`. Then

```cpp
double r = 0;
if (L < W) r = Y > 1e-9 ? (W - L) / Y : 0;
else if (L > W) r = Z > 1e-9 ? std::max(-1.0, (W - L) / Z) : 0;
```

`r` is clamped at −1 when shrinking, is 0 when there is nothing to stretch/shrink, and is not clamped from above.

After a break, `start` skips glue and non-forced penalties, stopping at a box or a forced penalty. Processing ends
after the first line whose break is a forced penalty; items after it are never laid out.

### 2.7 What the callers rely on

`BookLayout` (specified elsewhere) builds one item list per paragraph: boxes for text pieces (an optional indent box
first), glue for spaces with `stretch = width·0.5`, `shrink = width·0.33`, a `kLbInfPenalty` penalty before the glue
of a space that must not break, flagged penalties for hyphenation (120, width = hyphen), soft hyphens (50, width =
hyphen) and explicit hyphens/dashes (50, width 0), unflagged penalties 0 for zero-width breaks and 100 between pieces of
an over-wide word, and finally a fill glue (width 0, stretch `kLbFillStretch`, shrink 0) plus a flagged forced penalty
(`-kLbInfPenalty`). `lineWidths` is `{avail}` or `{avail, avail - hang}`. Justified paragraphs call
`breakLinesOptimal` with `tolerance = 2.0f`, then with `6.0f` if that fails (other `LbParams` fields at their
defaults), then `breakLinesGreedy`; other alignments use `breakLinesGreedy` only. The layout uses `LbBreak::ratio` to
widen/narrow glue and `lbLineWidth` with the line index.

---

## 3. Tests that constrain this part (`tests/core_tests.cpp`)

- `testHyphenation` — loads the four shipped files (`load` must return true for both languages with (2, 3) and
  (2, 2)), then via `HyphenationService::hyphenate`: `hyphenation` → `hy-phen-ation` (pattern path, English, rightMin
  3), `Table` → `Ta-ble` (lower-casing, exception path, bounds check `2 <= 2 <= 5-3`), `переносы` → `пе-ре-но-сы`
  (Russian patterns), `abc` unchanged (fewer than 4 code points), `Москва2` unchanged (a digit rejects the word).
  It also prints `computer`, `программирование`, `Достоевский`, `несчастливая` without checking them.
- `testLineBreaker` — ten boxes of width 10 separated by glue 3 (+1.5/−1), fill glue and a flagged forced penalty,
  line width 40: `breakLinesOptimal` must succeed with 4 breaks, the last at the final item; `breakLinesGreedy` must
  give 4 breaks. A single box of width 100: optimal must return false, greedy must give exactly 1 break.
- `testTextLayout` (only with `LL_TESTS_WITH_TEXT`) — real paragraphs through `BookLayout`: no line may overflow, every
  justified non-final line must be flush (|right edge − page width| ≤ 0.75), at least one line must end with a
  hyphen, and a long URL in a narrow column must break without hyphens. These depend on the exact demerits, tolerance
  retry and hyphenation results. It prints the `lbStats()` counters.

## Checklist

Hyphenator (direct calls; `br` starts empty unless stated):

- `load("a1b", "", 1, 1)` → true, `patternCount() == 1`; `hyphenate(U"ab", br)` → `br == {1}`.
- `load("a1b\na2b", "", 1, 1)` → `patternCount() == 2`; `hyphenate(U"ab")` → `{}` (merged value max(1,2) = 2 is even).
- `load("a1b\na3b", "", 1, 1)` → `hyphenate(U"ab")` → `{1}`.
- `load("a12b", "", 1, 1)` → `hyphenate(U"ab")` → `{}` (the later digit 2 overwrites 1).
- `load("% comment\n\n  a1b \r\n", "", 1, 1)` → true, `patternCount() == 1`, `hyphenate(U"ab")` → `{1}`.
- `load("12\n", "", 1, 1)` → false (digit-only line ignored), `empty() == true`.
- `load("A1B", "", 1, 1)` → `hyphenate(U"ab")` → `{1}`; `hyphenate(U"AB")` → `{}`.
- `load("a1b c1d", "", 1, 1)` → `patternCount() == 1`; `hyphenate(U"abcd")` → `{1, 3}`; `hyphenate(U"ab")` → `{}`.
- `load(".a1b", "", 1, 1)` → `hyphenate(U"ab")` → `{1}`; `hyphenate(U"cab")` → `{}` (word-start pattern only).
- `load("a1b", "", 2, 2)` → `hyphenate(U"ab")` → `{}` (n = 2 < 4).
- `load("x1y", "ab-cd-e", 2, 2)` → `hyphenate(U"abcde")` → `{2}` (4 > 5 − 2 is filtered).
- `load("a1b", "a-b\nab", 1, 1)` → `hyphenate(U"ab")` → `{}` (the second line replaced the exception with "no breaks").
- `load("", "a-b", 1, 1)` → false; `hyphenate(U"ab")` → `{}` (exceptions unused without patterns).
- `br = {99}`, after `load("a1b", "", 1, 1)`: `hyphenate(U"ab", br)` → `br == {99, 1}` (append only).
- Shipped files: English `patternCount() == 4938`, Russian `patternCount() == 7021`.

HyphenationService (shipped files, English (2, 3), Russian (2, 2)):

- `hyphenation` → `{2, 6}`; `Table` → `{2}`; `переносы` → `{2, 4, 6}`.
- `abc` → `{}`; `Москва2` → `{}`; a word mixing Latin `M` with Cyrillic `осква` → `{}`; `don't` → `{}` (apostrophe).
- `present` → `{}` (exception without breaks).

Line breaking (`P` = flagged forced penalty `{Penalty, true, 0, 0, 0, -kLbInfPenalty}`, `F` = fill glue
`{Glue, false, 0, kLbFillStretch, 0, 0}`, `g` = glue `{Glue, false, 3, 1.5f, 1, 0}`, `Bw` = box of width w):

- `lbLineWidth({100, 80}, 0) == 100`, `(…, 1) == 80`, `(…, 7) == 80`, `(…, -2) == 100`; `lbLineWidth({}, 3) == 1e9f`.
- Ten `B10` joined by `g`, then `F`, `P` (21 items), widths `{40}`: optimal → true, breaks at items `{5, 11, 17, 20}`,
  ratios `4/3, 4/3, 4/3, 0.0003` (as float); greedy → the same items and ratios.
- `{B100, F, P}`, widths `{40}`: optimal → false, `out` empty, `optimalFail` +1; greedy → `{ {2, 0} }`.
- `{B40, F, P}`, widths `{40}`: optimal → true, `{ {2, 0} }` (exact fit, r = 0).
- `{B10, g, B10, F, P}`, widths `{}` (1e9): optimal → false (only line has r ≈ 9999.85 > 2); greedy → one break at
  item 4 with r ≈ 9999.85.
- `{B50, g, B10, g, B10, F, P}`, widths `{40}`: optimal → false; greedy → `{ {6, -1} }` (whole paragraph on one line).
- `{B10, P, B10, F, P}`, widths `{40}`: greedy → `{ {1, 0} }` only (stops after the first forced break).
- `{B10, g, B10}` (no forced end), widths `{100}`: greedy → `{ {1, 0}, {2, 0} }`.
- Empty item list: optimal → true, `out` empty, counters unchanged; greedy → `out` empty, `greedy` +1.
- Fitness class boundaries: r = −0.6 → 0, r = −0.5 → 1, r = 0.5 → 1, r = 0.51 → 2, r = 1.0 → 2, r = 1.01 → 3.
- Demerits of a line with r = 1, `linePenalty` 10, ending at a non-forced penalty 120: `(10 + 100)² + 120² = 26500`,
  then `+ flaggedDemerits` / `+ fitnessDemerits` if those conditions hold, then `+ a.demerits`; with penalty −50 the
  first part is `12100 − 2500 = 9600`; ending at a forced penalty it is `12100`.
