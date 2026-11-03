# 03 — Core foundation: Unicode, encodings, XML, document model, files, images

This part specifies six translation units of the portable `ll_core` library: `src/core/Unicode.cpp`, `src/core/Encoding.cpp`, `src/core/XmlReader.cpp`, `src/core/Document.cpp`, `src/core/FileUtil.cpp` and `src/core/ImageCodec.cpp`. Together they provide UTF-8 handling and character classes, charset detection and conversion, the forgiving XML pull parser, the book-model helpers (web-address linking, span lookup, TOC lookup, plain text), small file helpers and the stb-based image codec. Their headers (`Unicode.h`, `Encoding.h`, `XmlReader.h`, `Document.h`, `FileUtil.h`, `ImageCodec.h`), `core/BookLoader.h` (which declares `pathFromUtf8`) and `tests/core_tests.cpp` are in `ai/files/` verbatim. Their declarations are referred to by name here and not repeated. The goal is identical observable behaviour: for every input, each function must return exactly what the original returns. That includes how it treats malformed data and every quirk described below. The quirks are part of the copy; do not "fix" them. None of these files uses SDL, OpenGL, locales or mutable global state. Everything is in `namespace ll`, and file-local helpers sit in an anonymous namespace inside it.

## 0. Notation

- Bytes are written `0xNN` and code points `U+XXXX`. Every range is inclusive.
- "ASCII letter" means `A`–`Z` and `a`–`z`. "ASCII-lowercasing" changes only `A`–`Z` (+0x20).
- A "continuation byte" is a byte with `(b & 0xC0) == 0x80` (0x80–0xBF).
- In pseudocode, `s[a:b]` is the byte range `a ≤ k < b`. `find`/`rfind` behave like `std::string_view::find`/`rfind` (they return `npos` when the target is absent).

---

## 1. `src/core/Unicode.cpp`

### 1.1 Purpose and layout

Dependency-free UTF-8 encoding and decoding, simple case mapping, character classes, search folding and small string helpers. The file includes only `"core/Unicode.h"`. Definition order:

1. `utf8Decode`, `utf8Append`, `utf8ToU32`, `u32ToUtf8`, `utf8Validate`, `utf8Length`, `utf8AlignBack`, `utf8NextPos`, `utf8PrevPos`
2. `toLowerCp`, `toUpperCp`
3. `isSpaceCp`, `isLatinLetterCp`, `isCyrillicCp`, `isCombiningMarkCp`, `isLetterCp`, `isDigitCp`, `isDashCp`, `isOpeningPunctCp`
4. An anonymous namespace holding `stripLatinDiacritic`
5. `foldForSearchCp`, `foldForSearch`, `toLowerUtf8`, `trimView`, `trimCopy`, `collapseSpaces`, `iequalsAscii`, `endsWithNoCase`, `startsWith`

### 1.2 `utf8Decode(s, i)`

Precondition (not checked): `i < s.size()`. The function reads `s[i]` unconditionally.

Definitions:
- `b0 = (unsigned char)s[i]` and `n = s.size()`.
- `cont(k)`: −1 if `i + k >= n`; `s[i+k] & 0x3F` if `s[i+k]` is a continuation byte; −1 otherwise.
- `c1 = cont(1)`, `c2 = cont(2)`, `c3 = cont(3)`. All of the ones a row needs are evaluated before testing.

| lead byte `b0` | accepted when | value returned | `i +=` |
|---|---|---|---|
| 0x00–0x7F | always | `b0` | 1 |
| 0xC2–0xDF | `c1 ≥ 0` | `((b0 & 0x1F) << 6) \| c1` | 2 |
| 0xE0–0xEF | `c1, c2 ≥ 0` **and** value ≥ 0x800 **and** value not in 0xD800–0xDFFF | `((b0 & 0x0F) << 12) \| (c1 << 6) \| c2` | 3 |
| 0xF0–0xF4 | `c1, c2, c3 ≥ 0` **and** 0x10000 ≤ value ≤ 0x10FFFF | `((b0 & 0x07) << 18) \| (c1 << 12) \| (c2 << 6) \| c3` | 4 |
| any other lead, or the row's condition fails | — | U+FFFD (`kReplacementChar`) | **1** |

These inputs all return U+FFFD and consume exactly one byte:
- overlong forms (lead 0xC0/0xC1; E0 followed by 80–9F; F0 followed by 80–8F)
- encoded surrogates (ED A0–BF ..)
- values above U+10FFFF (F4 90.. and leads F5–FF)
- stray continuation bytes
- sequences cut short by the end of input or by a non-continuation byte

Decoding then resumes at the next byte. If that byte is a continuation byte, it yields another U+FFFD. A correctly encoded U+FFFD (EF BF BD) is a normal 3-byte sequence.

### 1.3 `utf8Append(out, cp)`

- `cp < 0x80`: appends the single byte `cp`.
- `cp < 0x800`: appends `0xC0 | (cp >> 6)`, `0x80 | (cp & 0x3F)`.
- `cp < 0x10000`: a surrogate (0xD800–0xDFFF) is first replaced by U+FFFD. Then appends `0xE0 | (cp >> 12)`, `0x80 | ((cp >> 6) & 0x3F)`, `0x80 | (cp & 0x3F)`.
- `cp ≤ 0x10FFFF`: appends `0xF0 | (cp >> 18)`, `0x80 | ((cp >> 12) & 0x3F)`, `0x80 | ((cp >> 6) & 0x3F)`, `0x80 | (cp & 0x3F)`.
- otherwise: appends U+FFFD (implemented as the recursive call `utf8Append(out, kReplacementChar)`).

U+0000 is appended as a 0x00 byte (no special case).

### 1.4 Conversions and positions

- **`utf8ToU32(s)`**: reserves `s.size()` elements, then appends `utf8Decode` results until `s` is consumed.
- **`u32ToUtf8(s)`**: reserves `2 * s.size()` bytes, then calls `utf8Append` for each element.
- **`utf8Validate(s, multiByteSeqs, errors)`** walks the input:
  - A byte < 0x80 is skipped and counted nowhere.
  - Otherwise it records `before = i` and calls `utf8Decode(s, i)`. If that returned U+FFFD **and** `i - before == 1`, it increments `errors`; otherwise it increments `multi`.
  - At the end it stores both counts through whichever pointers are non-null and returns `errors == 0`.
  - A well-formed EF BF BD counts as a multi-byte sequence. Every bad byte is a separate error: "\xE2\x82" at the end of input is 2 errors.
- **`utf8Length(s)`**: the number of `utf8Decode` steps needed to consume `s`. Each malformed byte counts as one code point.
- **`utf8AlignBack(s, pos)`**:
  - If `pos >= s.size()`, it returns `s.size()`.
  - Otherwise it steps back (`--pos`) while `pos > 0`, fewer than 3 steps have been taken, and `s[pos]` is a continuation byte. It returns `pos`.
  - So it never moves more than 3 bytes, and does not check that the byte it stops on is a lead byte.
- **`utf8NextPos(s, pos)`**: returns `s.size()` if `pos >= s.size()`. Otherwise it runs `utf8Decode(s, pos)` and returns the advanced `pos`. Starting on a continuation byte, this gives `pos + 1`.
- **`utf8PrevPos(s, pos)`**:
  - `pos == 0` returns 0.
  - Otherwise it clamps `pos` to `s.size()` and returns `utf8AlignBack(s, pos - 1)`.
  - With an empty `s` and `pos > 0`, the result is 0 (`utf8AlignBack` gets `SIZE_MAX` and returns `s.size()`).

### 1.5 Case mapping: `toLowerCp`, `toUpperCp`

These are simple 1:1 mappings written as range checks. The tables are exhaustive: a code point not covered by any row is returned unchanged.

**`toLowerCp(c)`**

| input | result |
|---|---|
| U+0041–U+005A | +0x20 |
| U+00C0–U+00D6, U+00D8–U+00DE | +0x20 |
| U+0100–U+0137 except U+0130 | even → +1; odd → unchanged |
| U+0130 (İ) | U+0069 `i` |
| U+0139–U+0148 | odd → +1; even → unchanged |
| U+014A–U+0177 | even → +1; odd → unchanged |
| U+0178 (Ÿ) | U+00FF |
| U+0179–U+017E | odd → +1; even → unchanged |
| U+0386 | U+03AC |
| U+0388–U+038A | +37 (→ U+03AD–U+03AF) |
| U+038C | U+03CC |
| U+038E–U+038F | +63 (→ U+03CD–U+03CE) |
| U+0391–U+03A1, U+03A3–U+03A9 | +0x20 |
| U+0400–U+040F | +0x50 |
| U+0410–U+042F | +0x20 |
| U+0460–U+0481 | even → +1; odd → unchanged |
| U+048A–U+04BF | even → +1; odd → unchanged |
| U+04C0 | U+04CF |
| U+04C1–U+04CE | odd → +1; even → unchanged |
| U+04D0–U+052F | even → +1; odd → unchanged |

Unchanged by the rules above include: U+00D7, U+00DF, U+00FF, U+0131, U+0138, U+0149, U+017F, all of U+0180–U+036F, U+0370–U+0385, U+0387, U+038B, U+038D, U+0390, U+03A2, U+03AA–U+03FF, U+0430–U+045F, U+0482–U+0489, U+04CF, and everything from U+0530 up.

**`toUpperCp(c)`**

| input | result |
|---|---|
| U+0061–U+007A | −0x20 |
| U+00E0–U+00F6, U+00F8–U+00FE | −0x20 |
| U+00FF (ÿ) | U+0178 |
| U+0100–U+0137 except U+0131 | odd → −1; even → unchanged |
| U+0131 (ı) | U+0049 `I` |
| U+0139–U+0148 | even → −1; odd → unchanged |
| U+014A–U+0177 | odd → −1; even → unchanged |
| U+0179–U+017E | even → −1; odd → unchanged |
| U+03AC | U+0386 |
| U+03AD–U+03AF | −37 |
| U+03B1–U+03C1, U+03C3–U+03C9 | −0x20 |
| U+03C2 (ς) | U+03A3 |
| U+03CC | U+038C |
| U+03CD–U+03CE | −63 |
| U+0430–U+044F | −0x20 |
| U+0450–U+045F | −0x50 |
| U+0460–U+0481 | odd → −1; even → unchanged |
| U+048A–U+04BF | odd → −1; even → unchanged |
| U+04C1–U+04CE | even → −1; odd → unchanged |
| U+04CF | U+04C0 |
| U+04D0–U+052F | odd → −1; even → unchanged |

Unchanged by the rules above include: U+00B5, U+00DF, U+00F7, U+0130, U+0138, U+0149, U+0178, U+017F, U+0180–U+036F, U+0390, U+03B0, U+03CA, U+03CB, U+0400–U+042F, U+0482–U+0489, U+04C0, and everything from U+0530 up.

### 1.6 Character classes

- **`isSpaceCp(c)`** is true exactly for:
  - U+0009, U+000A, U+000B, U+000C, U+000D, U+0020
  - U+1680
  - U+2000–U+200A **except U+2007**
  - U+2028, U+2029, U+205F, U+3000

  It is false for U+00A0 (NBSP), U+2007, U+202F, U+0085, U+200B and U+FEFF.
- **`isLatinLetterCp(c)`**:
  - `c < 0x80`: `(c | 32)` in `'a'..'z'`, which is exactly the ASCII letters.
  - U+00C0–U+024F except U+00D7 and U+00F7: true.
  - U+1E00–U+1EFF: true.
  - Everything else is false, including U+00AA, U+00B5 and U+00BA.
- **`isCyrillicCp(c)`**: U+0400–U+0481, U+048A–U+052F, U+1C80–U+1C88, U+A640–U+A69F. U+0482–U+0489 are excluded.
- **`isCombiningMarkCp(c)`**: U+0300–U+036F, U+0483–U+0489, U+1AB0–U+1AFF, U+1DC0–U+1DFF, U+20D0–U+20FF, U+FE20–U+FE2F.
- **`isLetterCp(c)`** is true when any of these holds (checked in this order; the result is their union):
  1. `isLatinLetterCp(c) || isCyrillicCp(c)`
  2. `c` is U+00AA, U+00B5 or U+00BA
  3. U+0250–U+02AF (IPA)
  4. U+0386–U+03FF except U+0387 (Greek; U+0370–U+0385 are **not** letters)
  5. U+1F00–U+1FFF (Greek Extended)
  6. U+0531–U+0587 (Armenian)
  7. U+05D0–U+05EA (Hebrew)
  8. U+0620–U+064A (Arabic)
  9. U+10A0–U+10FF (Georgian)
  10. U+3040–U+9FFF (the whole block from Hiragana through CJK, including everything in between)
  11. U+AC00–U+D7A3 (Hangul)

  Everything else is false.
- **`isDigitCp(c)`**: `'0'..'9'` only.
- **`isDashCp(c)`**: U+002D, U+2010, U+2012, U+2013, U+2014, U+2015, U+2212. U+2011 (non-breaking hyphen) and U+00AD are **not** dashes.
- **`isOpeningPunctCp(c)`** is true exactly for:
  - `"` U+0022, `'` U+0027, `(`, `[`, `{`
  - `«` U+00AB, `„` U+201E, `“` U+201C, `‘` U+2018, `‚` U+201A, `‹` U+2039

  Everything else is false, including `»`, `”`, `’`, `›` and `<`.

### 1.7 Search folding

**`stripLatinDiacritic(c)`** (file-local, anonymous namespace):

- `c < 0xE0`: returns `c` unchanged.
- `c ≤ 0xFF`: looks `c` up in the map below (index `c - 0xE0`):
  ```cpp
  static const char kMap[] = "aaaaaaaceeeeiiiidnooooo/ouuuuyty";  // 0xE0..0xFF
  ```
  - If the map character is `'/'` (index of U+00F7 ÷), returns `c`.
  - If `c` is U+00E6, U+00F0 or U+00FE (æ ð þ), returns `c`.
  - Otherwise returns the ASCII map character.

  Result: à–å → `a`; ç → `c`; è–ë → `e`; ì–ï → `i`; ñ → `n`; ò–ö and ø → `o`; ù–ü → `u`; ý and ÿ → `y`. æ, ð, þ and ÷ are kept.
- U+0100 ≤ `c` ≤ U+017F: the first matching row below, else `c` unchanged.

  | range | result |
  |---|---|
  | U+0101–U+0105 | `a` |
  | U+0107–U+010D | `c` |
  | U+010F, U+0111 | `d` |
  | U+0113–U+011B | `e` |
  | U+011D–U+0123 | `g` |
  | U+0125, U+0127 | `h` |
  | U+0129–U+0131 | `i` |
  | U+0135 | `j` |
  | U+0137 | `k` |
  | U+013A–U+0142 | `l` |
  | U+0144–U+0148 | `n` |
  | U+014D–U+0151 | `o` |
  | U+0155–U+0159 | `r` |
  | U+015B–U+0161 | `s` |
  | U+0163–U+0167 | `t` |
  | U+0169–U+0173 | `u` |
  | U+0175 | `w` |
  | U+0177 | `y` |
  | U+017A–U+017E | `z` |
- Above U+017F: returns `c` unchanged.

**`foldForSearchCp(c)`** applies the first matching step:

1. `c = toLowerCp(c)`.
2. U+0451 (ё) → U+0435 (е). Since Ё is lowercased first, both Ё and ё become е.
3. U+2018, U+2019, U+201A, U+201B, U+2032, U+0060, U+00B4 → U+0027 `'`.
4. U+201C, U+201D, U+201E, U+201F, U+00AB, U+00BB, U+2033 → U+0022 `"`.
5. U+2010, U+2011, U+2012, U+2013, U+2014, U+2015, U+2212 → U+002D `-`.
6. U+00A0, U+2007, U+202F → U+0020.
7. `isSpaceCp(c)` → U+0020.
8. Otherwise → `stripLatinDiacritic(c)`.

Combined result for the Latin ranges (input in either case):

| input | folded |
|---|---|
| U+00C0–U+00C5, U+00E0–U+00E5 | `a` |
| U+00C6, U+00E6 | U+00E6 æ |
| U+00C7, U+00E7 | `c` |
| U+00C8–U+00CB, U+00E8–U+00EB | `e` |
| U+00CC–U+00CF, U+00EC–U+00EF | `i` |
| U+00D0, U+00F0 | U+00F0 ð |
| U+00D1, U+00F1 | `n` |
| U+00D2–U+00D6, U+00D8, U+00F2–U+00F6, U+00F8 | `o` |
| U+00D7, U+00F7 | unchanged |
| U+00D9–U+00DC, U+00F9–U+00FC | `u` |
| U+00DD, U+00FD, U+00FF, U+0178 | `y` |
| U+00DE, U+00FE | U+00FE þ |
| U+00DF ß | unchanged |
| U+0100–U+0105 | `a` |
| U+0106–U+010D | `c` |
| U+010E–U+0111 | `d` |
| U+0112–U+011B | `e` |
| U+011C–U+0123 | `g` |
| U+0124–U+0127 | `h` |
| U+0128–U+0131 (U+0130 via `toLowerCp` → `i`) | `i` |
| U+0132, U+0133 | U+0133 ĳ |
| U+0134, U+0135 | `j` |
| U+0136, U+0137 | `k` |
| U+0138, U+0149, U+017F | unchanged |
| U+0139–U+0142 | `l` |
| U+0143–U+0148 | `n` |
| U+014A, U+014B | U+014B ŋ |
| U+014C–U+0151 | `o` |
| U+0152, U+0153 | U+0153 œ |
| U+0154–U+0159 | `r` |
| U+015A–U+0161 | `s` |
| U+0162–U+0167 | `t` |
| U+0168–U+0173 | `u` |
| U+0174, U+0175 | `w` |
| U+0176, U+0177 | `y` |
| U+0179–U+017E | `z` |

Other effects of the composition:
- Greek and Cyrillic are only lowercased: σ/ς are not unified, й and accents on Greek letters stay.
- U+00AD, U+FFFD and other characters fall through unchanged.

**`foldForSearch(s)`** reserves `s.size()` bytes, keeps a flag `lastSpace = false`, and then for each code point `c` decoded with `utf8Decode`:

1. If `c` is U+00AD, in U+200B–U+200D, U+FEFF, or `isCombiningMarkCp(c)`: drop it (`continue`). This test uses the raw code point, before folding, and does not touch `lastSpace`.
2. `c = foldForSearchCp(c)`.
3. If `c == U' '`: drop it if `lastSpace` is already set, otherwise set `lastSpace = true`. Any other `c` clears `lastSpace`.
4. `utf8Append(out, c)`.

So runs of white space (including tab, newline, NBSP and U+202F) become one space. The string is **not** trimmed: one leading and one trailing space survive. Malformed bytes become U+FFFD.

### 1.8 String helpers

- **`toLowerUtf8(s)`**: reserves `s.size()`, then for every decoded code point does `utf8Append(out, toLowerCp(cp))`. A malformed byte becomes EF BF BD.
- **`trimView(s)`** trims tokens in two loops:
  - Front loop: if `s` is non-empty and its first byte is `' '`, `'\t'`, `'\r'` or `'\n'`, remove 1 byte. Else, if `s.size() ≥ 2` and it starts with 0xC2 0xA0 (UTF-8 NBSP), remove 2 bytes. Else stop.
  - Back loop: the same at the end (single ASCII byte first, then a trailing C2 A0 pair).
  - `\f`, `\v` and every other Unicode space are not trimmed.
- **`trimCopy(s)`**: `std::string(trimView(s))`.
- **`collapseSpaces(s)`** builds `out` with a flag `pendingSpace = false`. For each code point (with `start` = its first byte index, decoded with `utf8Decode`):
  - If `isSpaceCp(cp)`: set `pendingSpace = !out.empty()` and continue.
  - Otherwise: if `pendingSpace`, append `' '` and clear the flag. Then append the **original bytes** `s[start:i]`.

  Malformed bytes are therefore copied through raw, not as U+FFFD. Leading and trailing white space disappears, and each interior run becomes one ASCII space. NBSP is not white space here and is kept.
- **`iequalsAscii(a, b)`**: the sizes must be equal; then compares byte by byte after ASCII-lowercasing both bytes.
- **`endsWithNoCase(s, suffix)`**: `s.size() >= suffix.size() && iequalsAscii(s.substr(s.size() - suffix.size()), suffix)`.
- **`startsWith(s, prefix)`**: case-sensitive byte prefix test.

### 1.9 Tests that constrain this file

- `testUnicode` checks:
  - The `utf8ToU32`/`u32ToUtf8` round trip of `"Ёж «ёлка» — Straße"`, and its `utf8Length` = 18.
  - `toLowerUtf8("ПРИВЕТ Мир ЁЖ") == "привет мир ёж"`.
  - `foldForSearch("ЁЛКА  «Ёжик»\tCafé") == "елка \"ежик\" cafe"`: ё→е, guillemets → `"`, tab → space, two spaces → one, é → e.
  - `toUpperCp(U'я') == U'Я'` and `toLowerCp(U'Ї') == U'ї'`.
  - Exactly 6 `utf8Decode` steps for `"a\xC3(b\xE2\x82"`. This pins the one-byte-per-error rule and the handling of a truncated sequence at the end.
  - `utf8Validate` of that string returns false with errors > 0.
  - `collapseSpaces("  a \t b\n\nc  ") == "a b c"`.
- `testMatching` relies on `foldForSearch` (Cyrillic and Latin lowercasing) through `translitSkeleton` and `QueryMatcher` (LibrarySearch). `findPhrase` relies on `foldForSearchCp` being 1:1.
- `testEncodings`, `testFb2`, `testTxt` and `testWebAddresses` use `utf8Decode`, `utf8Validate`, `utf8AlignBack`, `utf8Append` and `utf8Length` indirectly.

---

## 2. `src/core/Encoding.cpp`

### 2.1 Purpose and layout

The file detects the charset of book bytes and converts them to UTF-8. It includes `<algorithm>`, `<cstdint>` and `"core/Unicode.h"`.

The anonymous namespace (first in the file) contains, in this order: the six code-page tables, `singleByteToCp`, `kRuFreq`, `struct Score`, `scoreRussian` and `looksUtf16`. The public functions follow: `charsetName`, `charsetFromName`, `detectBom`, `detectCharset`, `decodeToUtf8`, `bytesToUtf8`.

### 2.2 Single-byte code pages

These tables are verbatim; they are `const char16_t` arrays in the anonymous namespace:

```cpp
const char16_t kCp1251Hi[64] = {  // 0x80..0xBF, 0xC0..0xFF are U+0410..U+044F
    0x0402, 0x0403, 0x201A, 0x0453, 0x201E, 0x2026, 0x2020, 0x2021, 0x20AC, 0x2030, 0x0409, 0x2039, 0x040A, 0x040C,
    0x040B, 0x040F, 0x0452, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0xFFFD, 0x2122, 0x0459, 0x203A,
    0x045A, 0x045C, 0x045B, 0x045F, 0x00A0, 0x040E, 0x045E, 0x0408, 0x00A4, 0x0490, 0x00A6, 0x00A7, 0x0401, 0x00A9,
    0x0404, 0x00AB, 0x00AC, 0x00AD, 0x00AE, 0x0407, 0x00B0, 0x00B1, 0x0406, 0x0456, 0x0491, 0x00B5, 0x00B6, 0x00B7,
    0x0451, 0x2116, 0x0454, 0x00BB, 0x0458, 0x0405, 0x0455, 0x0457};

const char16_t kKoi8rHi[64] = {  // 0x80..0xBF
    0x2500, 0x2502, 0x250C, 0x2510, 0x2514, 0x2518, 0x251C, 0x2524, 0x252C, 0x2534, 0x253C, 0x2580, 0x2584, 0x2588,
    0x258C, 0x2590, 0x2591, 0x2592, 0x2593, 0x2320, 0x25A0, 0x2219, 0x221A, 0x2248, 0x2264, 0x2265, 0x00A0, 0x2321,
    0x00B0, 0x00B2, 0x00B7, 0x00F7, 0x2550, 0x2551, 0x2552, 0x0451, 0x2553, 0x2554, 0x2555, 0x2556, 0x2557, 0x2558,
    0x2559, 0x255A, 0x255B, 0x255C, 0x255D, 0x255E, 0x255F, 0x2560, 0x2561, 0x0401, 0x2562, 0x2563, 0x2564, 0x2565,
    0x2566, 0x2567, 0x2568, 0x2569, 0x256A, 0x256B, 0x256C, 0x00A9};

const char16_t kKoi8rLetters[32] = {  // 0xC0..0xDF lowercase; 0xE0..0xFF = same - 0x20
    0x044E, 0x0430, 0x0431, 0x0446, 0x0434, 0x0435, 0x0444, 0x0433, 0x0445, 0x0438, 0x0439,
    0x043A, 0x043B, 0x043C, 0x043D, 0x043E, 0x043F, 0x044F, 0x0440, 0x0441, 0x0442, 0x0443,
    0x0436, 0x0432, 0x044C, 0x044B, 0x0437, 0x0448, 0x044D, 0x0449, 0x0447, 0x044A};

const char16_t kCp866Box[48] = {  // 0xB0..0xDF
    0x2591, 0x2592, 0x2593, 0x2502, 0x2524, 0x2561, 0x2562, 0x2556, 0x2555, 0x2563, 0x2551, 0x2557,
    0x255D, 0x255C, 0x255B, 0x2510, 0x2514, 0x2534, 0x252C, 0x251C, 0x2500, 0x253C, 0x255E, 0x255F,
    0x255A, 0x2554, 0x2569, 0x2566, 0x2560, 0x2550, 0x256C, 0x2567, 0x2568, 0x2564, 0x2565, 0x2559,
    0x2558, 0x2552, 0x2553, 0x256B, 0x256A, 0x2518, 0x250C, 0x2588, 0x2584, 0x258C, 0x2590, 0x2580};

const char16_t kCp866Tail[16] = {  // 0xF0..0xFF
    0x0401, 0x0451, 0x0404, 0x0454, 0x0407, 0x0457, 0x040E, 0x045E,
    0x00B0, 0x2219, 0x00B7, 0x221A, 0x2116, 0x00A4, 0x25A0, 0x00A0};

const char16_t kCp1252Hi[32] = {  // 0x80..0x9F, 0xA0..0xFF = Latin-1
    0x20AC, 0xFFFD, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160,
    0x2039, 0x0152, 0xFFFD, 0x017D, 0xFFFD, 0xFFFD, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022,
    0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0xFFFD, 0x017E, 0x0178};
```

**`singleByteToCp(unsigned char b, Charset cs)`** is a `switch (cs)` that is reached only for `b ≥ 0x80` (a byte `b < 0x80` returns `b` for every charset):

- **Cp1251**: `b ≥ 0xC0` → `U+0410 + (b − 0xC0)`; otherwise `kCp1251Hi[b − 0x80]`.
- **Koi8R**: `b < 0xC0` → `kKoi8rHi[b − 0x80]`; `b < 0xE0` → `kKoi8rLetters[b − 0xC0]`; otherwise `kKoi8rLetters[b − 0xE0] − 0x20`.
- **Cp866**:
  - `b < 0xA0` → `U+0410 + (b − 0x80)`
  - `b < 0xB0` → `U+0430 + (b − 0xA0)`
  - `b < 0xE0` → `kCp866Box[b − 0xB0]`
  - `b < 0xF0` → `U+0440 + (b − 0xE0)`
  - otherwise `kCp866Tail[b − 0xF0]`
- **Iso8859_5**:
  - `b < 0xA0` → `b` (C1 controls U+0080–U+009F)
  - 0xA0 → U+00A0; 0xAD → U+00AD; 0xF0 → U+2116; 0xFD → U+00A7
  - otherwise `U+0400 + (b − 0xA0)`
- **Cp1252**, which shares the case with `default:` and so covers every other enum value: `b < 0xA0` → `kCp1252Hi[b − 0x80]`; otherwise `b` (ISO-8859-1).

How each charset relates to its standard:
- **Windows-1251** is Microsoft's table exactly (0x88 → €, 0xA5/0xB4 → Ґ/ґ, 0xB9 → №), with one deviation: the byte the code page leaves unassigned, 0x98, decodes to U+FFFD.
- **KOI8-R** is RFC 1489, with no deviation. KOI8-U's extra letters at 0xA4, 0xA6, 0xA7, 0xAD, 0xB4, 0xB6, 0xB7 and 0xBD are not supported: they decode as KOI8-R box drawing, even though the name `koi8-u` maps to `Koi8R`.
- **CP866** is IBM code page 866, with no deviation.
- **ISO-8859-5** is ISO/IEC 8859-5, with no deviation.
- **Windows-1252** is Microsoft's table. Its five unassigned bytes 0x81, 0x8D, 0x8F, 0x90 and 0x9D decode to U+FFFD.

### 2.3 Russian letter scoring

```cpp
// Approximate frequencies (per mille) of Russian letters а..я, used to score candidate charsets.
const int kRuFreq[32] = {80, 16, 45, 17, 30, 85, 9,  16, 74, 12, 35, 44, 32, 67, 110, 28,
                         47, 55, 63, 26, 3,  10, 5,  14, 7,  4,  1,  19, 17, 3,  6,   20};
```

Index `k` is the letter U+0430 + k: а 80, б 16, в 45, г 17, д 30, е 85, ж 9, з 16, и 74, й 12, к 35, л 44, м 32, н 67, о 110, п 28, р 47, с 55, т 63, у 26, ф 3, х 10, ц 5, ч 14, ш 7, щ 4, ъ 1, ы 19, ь 17, э 3, ю 6, я 20.

`struct Score { double value = 0; size_t letters = 0; size_t high = 0; };`

**`scoreRussian(bytes, cs)`** looks at each byte `b` of `bytes`. It skips `b < 0x80`; otherwise it increments `high`, maps `c = singleByteToCp(b, cs)`, and applies the first matching rule:

| `c` | effect |
|---|---|
| U+0430–U+044F | `value += kRuFreq[c − 0x430]`, `++letters` |
| U+0451 (ё) | `value += 2`, `++letters` |
| U+0410–U+042F | `value += kRuFreq[c − 0x410] * 0.25`, `++letters` |
| U+0401 (Ё) | `value += 0.5`, `++letters` |
| any other U+0400–U+045F (non-Russian Cyrillic) | `value -= 20` |
| U+00A0, U+00AB, U+00BB, U+2014, U+2013, U+2026, U+201C, U+201D, U+201E, U+2116 | no change ("plausible punctuation") |
| anything else (box drawing, controls, symbols, U+FFFD, Ґ/ґ, ‘ ’ …) | `value -= 50` |

### 2.4 UTF-16 sniffing: `looksUtf16(b, littleEndian)`

```cpp
const size_t n = std::min<size_t>(b.size(), 8192) & ~size_t(1);
if (n < 16) return false;
// for i = 0, 2, ..., n - 2 with e = (unsigned char)b[i], o = (unsigned char)b[i + 1]:
//   evenZero += (e == 0); oddZero += (o == 0); evenCyr += (e == 0x04); oddCyr += (o == 0x04);
const size_t pairs = n / 2;
const size_t le = oddZero + oddCyr, be = evenZero + evenCyr;
if (le * 10 >= pairs * 4 && evenZero * 20 < pairs) { littleEndian = true;  return true; }
if (be * 10 >= pairs * 4 && oddZero * 20 < pairs)  { littleEndian = false; return true; }
return false;   // littleEndian untouched
```

In words: the function looks at the first 8192 bytes, rounded down to even. It says LE when at least 40 % of the pairs have a 0x00 or 0x04 high byte and fewer than 5 % have a zero low byte, and BE for the mirror case. LE is tested first.

### 2.5 Charset names

**`charsetName(cs)`**:

| `cs` | returned string |
|---|---|
| Utf8 | `"UTF-8"` |
| Utf16LE | `"UTF-16LE"` |
| Utf16BE | `"UTF-16BE"` |
| Cp1251 | `"windows-1251"` |
| Koi8R | `"KOI8-R"` |
| Cp866 | `"CP866"` |
| Iso8859_5 | `"ISO-8859-5"` |
| Cp1252 | `"windows-1252"` |
| default (Unknown) | `"unknown"` |

**`charsetFromName(name)`** first normalises the name into a new `std::string` of the same length: ASCII-lowercase each byte, then replace `'_'` and `' '` with `'-'`. Nothing is trimmed. It then compares the result exactly:

| normalised name | result |
|---|---|
| `utf-8`, `utf8` | Utf8 |
| `utf-16`, `utf-16le`, `unicode` | Utf16LE |
| `utf-16be` | Utf16BE |
| `windows-1251`, `cp1251`, `win-1251`, `cp-1251`, `x-cp1251`, `windows1251`, `1251` | Cp1251 |
| `koi8-r`, `koi8r`, `koi8`, `koi8-u`, `cskoi8r` | Koi8R |
| `cp866`, `ibm866`, `866`, `csibm866`, `dos-866` | Cp866 |
| `iso-8859-5`, `iso8859-5`, `cyrillic` | Iso8859_5 |
| `windows-1252`, `cp1252`, `iso-8859-1`, `latin1`, `latin-1`, `iso8859-1`, `us-ascii`, `ascii` | Cp1252 |
| anything else (including `""`, `"utf-32"`, `"windows-1250"`, names with surrounding spaces) | Unknown |

For example, `"UTF_8"`, `"Windows 1251"`, `"ISO_8859-1"` and `"KOI8_R"` are recognised, but `" utf-8"` becomes `"-utf-8"` and is Unknown.

### 2.6 `detectBom(b, bomLen)`

Sets `bomLen = 0`, then checks:
- `b` starts with EF BB BF → Utf8, `bomLen = 3`.
- Else `b` starts with FF FE → Utf16LE, `bomLen = 2`.
- Else `b` starts with FE FF → Utf16BE, `bomLen = 2`.
- Otherwise Unknown.

There is no UTF-32 detection: FF FE 00 00 is UTF-16LE.

### 2.7 `detectCharset(bytes)`

Steps in order; the first that returns wins:

1. `detectBom(bytes, …)`: if it returns something other than Unknown, return that.
2. If `looksUtf16(bytes, le)`, return Utf16LE or Utf16BE.
3. `sample = bytes[0 : min(size, 512 * 1024)]` (524288 bytes). Only if this is shorter than `bytes`: `sample = sample[0 : utf8AlignBack(sample, sample.size() − 1)]`. This drops the code point containing the last sample byte, so no UTF-8 sequence is cut; when the last byte is ASCII, only that byte is dropped.
4. `utf8Validate(sample, &multi, &errors)`. If `errors == 0 || multi > errors * 50`, return **Utf8**. Empty and pure-ASCII inputs therefore end here.
5. Western check over `sample`:
   - For every byte ≥ 0x80, increment `high`. If the byte before it (`i > 0`) or the byte after it (`i + 1 < size`) is an ASCII letter (`(c | 32)` in `'a'..'z'` on the unsigned byte), also increment `mixed`.
   - If `high > 0 && mixed * 10 > high * 4` (strictly more than 40 %), return **Cp1252**.
   - This works because Western accents sit inside ASCII words, while Russian words consist entirely of high bytes.
6. Score the candidates in the order `Cp1251, Koi8R, Cp866, Iso8859_5` with `scoreRussian(sample, cs)`.
   - Start with `best = Cp1251` and `bestScore.value = -1e300`.
   - A candidate replaces the best only if its `value` is **strictly greater**, so ties keep the earlier candidate.
7. If `bestScore.high > 0 && bestScore.letters * 2 < bestScore.high` (fewer than half of the high bytes are Russian letters under the best charset), return **Cp1252**.
8. Otherwise return `best`.

`detectCharset` never returns Unknown.

### 2.8 `decodeToUtf8(bytes, cs)`

The BOM must already be stripped; an unstripped BOM is decoded as U+FEFF.

- **Utf8 and Unknown**: if `utf8Validate(bytes)` is true, return a copy of `bytes` unchanged (NUL bytes included). Otherwise re-encode: for each `utf8Decode` result, call `utf8Append`, so each malformed byte becomes EF BF BD.
- **Utf16LE / Utf16BE**: `n = bytes.size() & ~1` (an odd trailing byte is ignored). For `i = 0; i < n; i += 2`:
  ```cpp
  char32_t u = le ? char32_t(a | (b << 8)) : char32_t((a << 8) | b);      // a = bytes[i], b = bytes[i + 1]
  if (u >= 0xD800 && u <= 0xDBFF && i + 3 < n) {
    const char32_t lo = /* next unit, same byte order */;
    if (lo >= 0xDC00 && lo <= 0xDFFF) { u = 0x10000 + ((u - 0xD800) << 10) + (lo - 0xDC00); i += 2; }
    else u = kReplacementChar;              // the following unit is NOT consumed: it is decoded on its own next
  } else if (u >= 0xD800 && u <= 0xDFFF) {
    u = kReplacementChar;                   // lone low surrogate, or high surrogate in the last unit
  }
  utf8Append(out, u);
  ```
  U+0000 units become 0x00 bytes, and U+FEFF is kept.
- **Every other value** (the single-byte charsets): bytes < 0x80 are copied as they are; others go through `utf8Append(out, singleByteToCp(b, cs))`.

### 2.9 `bytesToUtf8(bytes, hint, used)`

1. `cs = detectBom(bytes, bomLen)`. If `cs` is not Unknown, remove the `bomLen` BOM bytes from the view and **ignore the hint**.
2. Else, if `hint != Unknown`, set `cs = hint`. **Only a Utf8 hint is checked for plausibility**:
   - Run `utf8Validate` on `bytes[0 : min(size, 512 * 1024)]` **without** any `utf8AlignBack` (a sequence cut at the 512 KiB mark counts as error(s)).
   - If `errors > 0 && multi < errors * 50`, set `cs = detectCharset(bytes)`. When `multi == errors * 50`, the hint stays.
   - Any other hint (Cp1251, Koi8R, Utf16LE …) is used as given, even if it is wrong.
3. Else `cs = detectCharset(bytes)`.
4. If `used` is non-null, `*used = cs` (never Unknown).
5. Return `decodeToUtf8(bytes, cs)`.

### 2.10 Tests that constrain this file

- `testEncodings`:
  - `encodeSingleByte` builds an encoder by inverting `decodeToUtf8` byte by byte (0x80–0xFF). The tables must therefore map every Russian letter used from exactly one byte.
  - `detectCharset` must identify the Tolstoy sample encoded in Cp1251, KOI8-R and CP866 (scoring and candidate order).
  - `decodeToUtf8(enc, cs)` and `bytesToUtf8(enc)` must reproduce the sample.
  - The UTF-8 sample must be detected as Utf8.
  - `bytesToUtf8` of FF FE + UTF-16LE must strip the BOM.
  - `charsetFromName("Windows-1251")` must be Cp1251 and `charsetFromName("koi8-r")` must be Koi8R.
  - The Western sample `"Caf\xE9 cr\xE8me … \x93quoted\x94 …"` must be Cp1252 (the 40 % mixed-letter rule).
- `testFb2`: `fb2ToUtf8` in Fb2Parser passes the declared charset as the hint. A Cp1251 hint is trusted; `doc2.meta.encoding == "windows-1251"` comes from `charsetName`. The "declared windows-1251 but UTF-8" case is resolved in Fb2Parser before `bytesToUtf8` is called.
- `testTxt` (through `bytesToUtf8(raw, Unknown, &cs)` in TxtParser): lib.ru-style cp1251 text with indented lines must be detected as Cp1251, not Cp1252, so that `meta.encoding == "windows-1251"`. The ASCII Gutenberg text decodes as UTF-8.
- `testLibrarySearch`: a KOI8-R TXT (300 copies of the sample plus a unique phrase) must be detected as KOI8-R, otherwise the content search for "уникальная фраза для поиска" fails.

---

## 3. `src/core/XmlReader.cpp`

### 3.1 Purpose and layout

This is a forgiving pull parser over the UTF-8 bytes of a document. It never fails: anything it cannot interpret is either reported as text or skipped. `name_` is a view into the input. Attribute values and text are entity-decoded copies.

The file includes `<cstdlib>` (for `std::strtol`) and `"core/Unicode.h"` (for `utf8Append`). The anonymous namespace holds `isNameStart`, `isWs`, `localName`, `struct NamedEntity { const char* name; char32_t cp; }` and `kEntities`. After it come `xmlDecodeEntities`, `XmlReader::attr`, `XmlReader::hasAttr`, `XmlReader::next`, `XmlReader::parseTag` and `XmlReader::readText`.

### 3.2 Helpers

- **`isNameStart(char c)`**: an ASCII letter, `'_'`, `':'`, or any byte ≥ 0x80 (so `<` followed by Cyrillic opens a tag). Digits, `-` and `.` are not name starts.
- **`isWs(char c)`**: `' '`, `'\t'`, `'\r'`, `'\n'` only.
- **`localName(qname)`**: the part after the last `':'` (`rfind`). The whole string if there is no colon; `""` if the colon is the last character. Examples: `"l:href"` → `"href"`, `"a:b:c"` → `"c"`, `"xmlns:l"` → `"l"`.

### 3.3 Entities

The table is verbatim. Names are matched case-sensitively and exactly.

```cpp
const NamedEntity kEntities[] = {
    {"amp", '&'},        {"lt", '<'},          {"gt", '>'},         {"quot", '"'},       {"apos", '\''},
    {"nbsp", 0xA0},      {"mdash", 0x2014},    {"ndash", 0x2013},   {"laquo", 0xAB},     {"raquo", 0xBB},
    {"hellip", 0x2026},  {"copy", 0xA9},       {"reg", 0xAE},       {"trade", 0x2122},   {"lsquo", 0x2018},
    {"rsquo", 0x2019},   {"ldquo", 0x201C},    {"rdquo", 0x201D},   {"bdquo", 0x201E},   {"sbquo", 0x201A},
    {"shy", 0xAD},       {"deg", 0xB0},        {"plusmn", 0xB1},    {"times", 0xD7},     {"divide", 0xF7},
    {"middot", 0xB7},    {"bull", 0x2022},     {"euro", 0x20AC},    {"sect", 0xA7},      {"para", 0xB6},
    {"frac12", 0xBD},    {"frac14", 0xBC},     {"frac34", 0xBE},    {"iexcl", 0xA1},     {"iquest", 0xBF},
    {"thinsp", 0x2009},  {"ensp", 0x2002},     {"emsp", 0x2003},    {"minus", 0x2212},   {"prime", 0x2032},
    {"Prime", 0x2033},   {"cent", 0xA2},       {"pound", 0xA3},     {"yen", 0xA5},       {"acute", 0xB4},
    {"uml", 0xA8},       {"ordf", 0xAA},       {"ordm", 0xBA},      {"lsaquo", 0x2039},  {"rsaquo", 0x203A},
    {"eacute", 0xE9},    {"egrave", 0xE8},     {"agrave", 0xE0},    {"ouml", 0xF6},      {"uuml", 0xFC},
    {"auml", 0xE4},      {"szlig", 0xDF},      {"ccedil", 0xE7},    {"zwnj", 0x200C},    {"zwj", 0x200D},
    {"larr", 0x2190},    {"rarr", 0x2192},     {"hearts", 0x2665},  {"infin", 0x221E},   {"asymp", 0x2248},
};
```

**`xmlDecodeEntities(in, out)`** appends to `out` and never clears it:

```
i = 0
while i < in.size():
    amp = in.find('&', i)
    if amp == npos: out += in[i:]; return
    out += in[i:amp]
    semi = in.find(';', amp + 1)                 // the first ';' anywhere after the '&'
    if semi != npos and 2 <= semi - amp <= 12:   // entity body of 1..11 bytes
        ent = in[amp+1 : semi]
        ok = false
        if ent[0] == '#':
            if ent.size() >= 2:
                hex = (ent[1] == 'x' || ent[1] == 'X')
                num = std::string(ent.substr(hex ? 2 : 1))
                v = std::strtol(num.c_str(), &end, hex ? 16 : 10)
                if *end == '\0' and !num.empty() and v > 0 and v <= 0x10FFFF: cp = v; ok = true
        else:
            linear search of kEntities for an exact match → cp; ok = true
        if ok:
            if 0x80 <= cp <= 0x9F: cp = k1252[cp - 0x80]     // Windows-1252 smuggled in as numeric entities
            utf8Append(out, cp)
            i = semi + 1
            continue
    out += '&'                                     // not an entity: the '&' is literal text
    i = amp + 1                                    // scanning continues right after it
```

`k1252` is a function-local `static const char16_t k1252[32]` with exactly the values of `kCp1252Hi` (§2.2):

```cpp
static const char16_t k1252[32] = {0x20AC, 0xFFFD, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021,
                                   0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0xFFFD, 0x017D, 0xFFFD,
                                   0xFFFD, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
                                   0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0xFFFD, 0x017E, 0x0178};
```

Consequences:
- `&#151;` and `&#x97;` give "—". `&#129;` gives U+FFFD.
- `&#0;`, `&#-5;`, `&#;`, `&#x;`, `&#1114112;`, `&AMP;`, `&bogus;`, `& amp;` and `&amp x;` all stay literal.
- `&#xD800;` decodes to U+FFFD, because `utf8Append` replaces surrogates.
- Because `strtol` is used, leading white space and a sign are accepted (`&#+65;` gives `A`), and in base 16 a `0x` prefix is too (`&#x0x41;` gives `A`).
- Leading zeros are fine as long as the body is at most 11 bytes: `&#0000000065;` gives `A`, but `&#00000000065;` is literal.
- `"&&amp;"` gives `"&&"`.

### 3.4 `attr` / `hasAttr`

Both do a linear search over `attrs_` in document order, comparing the stored local name exactly with the argument:
- `attr` returns a view of the **first** match's value, or an empty view if there is none.
- `hasAttr` returns true if any entry matches, even one with an empty value.

The views stay valid until the next start or end tag is parsed.

### 3.5 `next()`

```
if pendingEnd_: pendingEnd_ = false; return EndTag          // nothing else changes (see below)
while pos_ < size:
    if s[pos_] != '<': readText(); return Text
    if pos_ + 1 >= size: readText(); return Text            // a '<' that is the last byte
    c = s[pos_ + 1]
    if c == '!':
        if s.compare(pos_, 4, "<!--") == 0:
            e = find("-->", pos_ + 4); pos_ = (e == npos) ? size : e + 3; continue
        if s.compare(pos_, 9, "<![CDATA[") == 0:
            e = find("]]>", pos_ + 9); end = (e == npos) ? size : e
            text_.assign(s[pos_ + 9 : end])                   // raw: no entity decoding, may be empty
            pos_ = (e == npos) ? size : e + 3
            return Text
        // anything else after "<!" (DOCTYPE with an internal subset, ELEMENT, junk):
        depth = 0
        for i = pos_ + 2; i < size; ++i:
            '[' → ++depth;  else ']' → --depth;  else '>' and depth <= 0 → break
        pos_ = (i < size) ? i + 1 : size; continue
    if c == '?':
        e = find("?>", pos_ + 2); pos_ = (e == npos) ? size : e + 2; continue
    if c == '/':
        i = pos_ + 2
        e = find('>', i); lt = find('<', i)
        end = (e == npos) ? size : e
        if lt != npos and lt < end: end = lt                  // "</p <p>": broken end tag
        raw = s[i:end] with isWs bytes trimmed at both ends
        name_ = localName(raw)
        pos_ = (end < size and s[end] == '>') ? end + 1 : end  // a '<' that ends it is not consumed
        attrs_.clear(); selfClosing_ = false
        return EndTag
    if isNameStart(c): parseTag(); return StartTag
    readText(); return Text                                    // '<' + space/digit/'='/...: a lone '<' is text
return End
```

Notes:
- Comments, processing instructions and `<!…>` declarations produce no token, so text on both sides of a comment comes out as two separate Text tokens.
- An unterminated comment, PI or declaration swallows the rest of the input.
- The search for `-->` starts after `<!--`, so `<!-->` does not close itself.
- The comparisons are case-sensitive (`<![cdata[` is a declaration and is skipped).
- An end tag's name is everything between `</` and its end, trimmed and passed through `localName`. Inner spaces are kept: `</p x='1'>` has the name `"p x='1'"`, while `</a b:c>` has the name `"c"`. `</>` gives an empty name. `</section` at the end of input gives EndTag `"section"` with `pos_ = size`.
- Text and End tokens do not touch `name_`, `attrs_` or `selfClosing_`.
- The pending EndTag of a self-closing tag reports the same `name()` with `selfClosing()` still true, and its attributes remain readable.
- Once the input is consumed, every call returns End.
- Whitespace-only text (for example the newline after `<?xml …?>`) is reported as an ordinary Text token.

### 3.6 `parseTag()`

`pos_` is at the `<`.

```
attrs_.clear(); selfClosing_ = false
i = pos_ + 1
while i < size and s[i] is not isWs, '>', '/', '<': ++i
name_ = localName(s[pos_ + 1 : i])            // '=' or quotes would be part of the name ("<p=x>" → "p=x")
for (;;):
    skip isWs
    if i >= size: break
    c = s[i]
    if c == '>': ++i; break
    if c == '<': break                        // malformed: the next tag starts here; '<' not consumed
    if c == '/':
        if i + 1 < size and s[i + 1] == '>': selfClosing_ = true; i += 2; break
        ++i; continue                         // stray '/' ignored
    an = i
    while i < size and s[i] is not isWs, '=', '>', '/', '<': ++i
    attrName = localName(s[an:i])
    skip isWs
    value = ""
    if i < size and s[i] == '=':
        ++i; skip isWs
        if i < size and (s[i] == '"' or s[i] == '\''):
            q = s[i++]
            e = find(q, i)                    // the closing quote is searched first, even past '>' and other tags
            gt = find('>', i)
            if e == npos: e = (gt == npos) ? size : gt
            xmlDecodeEntities(s[i:e], value)
            i = (e < size and s[e] == q) ? e + 1 : e
        else:
            vs = i
            while i < size and s[i] is not isWs, '>', '<': ++i       // '/' and quotes ARE allowed here
            xmlDecodeEntities(s[vs:i], value)
    if attrName is not empty: attrs_.emplace_back(attrName, std::move(value))
pos_ = i
if selfClosing_: pendingEnd_ = true
```

Consequences:
- An attribute without `=` has an empty value (`<td nowrap>`).
- A value with an empty name (`<p ="x">`) is parsed and discarded.
- Duplicates are all stored; `attr` returns the first.
- An unquoted value swallows a trailing slash, so `<img src=a.png/>` gives `src = "a.png/"` and is **not** self-closing.
- A quote that never closes ends the value at the next `>` (or the end of input), and then that `>` closes the tag.
- A tag cut off by the end of input still yields StartTag.

### 3.7 `readText()`

```
text_.clear()
i = chunkStart = pos_
if i < size and s[i] == '<': ++i              // a '<' that does not start markup is kept as literal text
for (;;):
    lt = find('<', i)
    if lt == npos: i = size; break
    if lt + 1 < size:
        c = s[lt + 1]
        if isNameStart(c) or c == '/' or c == '!' or c == '?': i = lt; break
    else:
        i = size; break                         // a final '<' belongs to the text
    i = lt + 1
xmlDecodeEntities(s[chunkStart:i], text_)
pos_ = i
```

So text runs up to the next `<` that is followed by a name-start byte, `/`, `!` or `?`. Every other `<` (`a < b`, `<3`, `<<`, a final `<`) is part of the text. The text is never empty.

### 3.8 Tests that constrain this file

- `testXml` checks the following sequence for `<?xml version='1.0'?><!-- c --><a x="1&amp;2" l:href='#n1'>T&lt;e&#x41;&mdash;<b/>x < y &bogus; </a>`:
  1. PI and comment skipped; StartTag `a`, with `attr("x") == "1&2"` and `attr("href") == "#n1"` (local name of `l:href`).
  2. Text `"T<eA—"`.
  3. StartTag `b` with `selfClosing()`, then EndTag.
  4. Text `"x < y &bogus; "`: a `<` followed by a space is text, and an unknown entity stays literal.
  5. EndTag, then End.
- `testFb2`:
  - The full FB2 sample: namespaced attributes, whitespace text, base64 text inside `<binary>`.
  - The broken document `<FictionBook><body><section><p>broken <emphasis>text</section` must tokenise without hanging: the final `</section` is an EndTag at the end of input.
- `testLibrarySearch` reads the same FB2 inside a zip.

---

## 4. `src/core/Document.cpp`

### 4.1 Purpose and layout

The functions behind the book model in `Document.h`: style-run lookup, TOC lookup, plain text, character offsets, and turning web addresses written in the text into links.

The file includes `<algorithm>`, `<cstring>`, `<string_view>` and `"core/Unicode.h"`. The anonymous namespace holds `startsWithNoCase`, `isAsciiAlnum`, `addressStop` and `addLinkSpan`. Then come `isWebLink`, `findWebAddresses`, `BookMeta::authorsJoined`, `Document::finalize`, `Document::tocIndexForBlock`, `Document::plainText` and `spanFlagsAt`.

### 4.2 File-local helpers

- **`startsWithNoCase(const std::string& s, size_t at, const char* prefix)`**: `n = strlen(prefix)`. Returns false if `at + n > s.size()`. Otherwise it compares `s[at + k]`, ASCII-lowercased, with `prefix[k]`; the prefixes passed are always lowercase literals.
- **`isAsciiAlnum(unsigned char c)`**: `0`–`9`, `a`–`z`, `A`–`Z`.
- **`addressStop(t, i)`**: the byte length of a character that ends an address at byte `i`, or 0. Only "zero or not" is ever used.
  - `c = t[i]`. If `c ≤ 0x20` (all control bytes and space) or `c` is one of `"` `<` `>` `` ` `` `{` `}` `|` `\` `^`, the result is 1.
  - If `c == 0xC2`, `i + 1 < size` and `t[i+1]` is 0xA0, 0xAB or 0xBB (U+00A0 NBSP, « and »), the result is 2.
  - If `c == 0xE2`, `i + 2 < size`, `t[i+1] == 0x80` and `t[i+2]` is in 0x93–0x9E or is 0xA6 or 0xAF, the result is 3. Those bytes are U+2013–U+201E (en dash, em dash, U+2015–U+2017, curly and low quotes) plus U+2026 (…) and U+202F (narrow no-break space).
  - Otherwise 0. `'`, `(`, `)`, `[`, `]`, `.`, `,`, `;`, `:`, `!`, `?`, `*`, `~`, `#`, `%`, `&`, `=`, `+`, `$`, `@`, 0x7F and all other non-ASCII bytes (Cyrillic paths) do not stop an address.

### 4.3 `spanFlagsAt(b, offset, link)`

1. If `link` is non-null, set `*link = -1`.
2. If `b.spans` is empty, return 0.
3. `it = std::upper_bound(spans, offset, by begin)`, the first span whose `begin > offset`. If that is the first span, return 0; `*link` stays −1.
4. Otherwise step back to the last span with `begin ≤ offset`, set `*link` to its `link` (whether or not its flags include `kSpanLink`), and return its `flags`.

### 4.4 `isWebLink(target)`

True if `target` starts, ASCII case-insensitively, with `"http://"`, `"https://"`, `"ftp://"` or `"mailto:"`. Nothing is trimmed: a leading space makes it false.

### 4.5 `findWebAddresses(t)`

```
out = {}
i = 0
while i < t.size():
    prefix = 8 if startsWithNoCase(t, i, "https://")
        else 7 if startsWithNoCase(t, i, "http://")
        else 6 if startsWithNoCase(t, i, "ftp://")
        else 4 if startsWithNoCase(t, i, "www.")
        else 0
    boundary = (i == 0) or not (isAsciiAlnum(t[i-1]) or t[i-1] in { '/', '.', '@', '-', '_' })
    if prefix == 0 or not boundary: ++i; continue
    e = i + prefix
    while e < t.size() and addressStop(t, e) == 0: ++e
    // Sentence punctuation after an address is not part of it; neither is a closing bracket without its pair.
    while e > i + prefix:
        c = t[e-1]
        if c in { '.', ',', ';', ':', '!', '?', '\'', '*' }: --e
        else if c == ')' or c == ']':
            open = (c == ')') ? '(' : '['
            opens  = std::count(t[i:e], open)
            closes = std::count(t[i:e], c)
            if closes > opens: --e else break
        else break
    body = t[i+prefix : e]
    hostEnd = min(body.find('/'), body.size())
    if body.size() >= 3 and body[0:hostEnd] contains '.' and isAsciiAlnum(body[0]):
        out.emplace_back(i, e)
    i = max(e, i + prefix)        // scanning resumes after the candidate, even when it was rejected
return out
```

Notes:
- Prefixes match in any case (`HTTP://`, `WWW.`).
- The boundary test is on the preceding **byte**. A UTF-8 continuation byte counts as a boundary, so `сайтwww.example.com` is found, but `me@www.x.com` and `x.www.y.com` are not.
- `mailto:` is never searched for.
- For `www.` the body starts after `www.`, so `www.example` (no dot after `www.`) is rejected while `www.a.b` is accepted.
- `http://localhost/x` is rejected because the host has no dot.
- `http://http://a.b` yields nothing: the host is `http:`, and the scan resumes at the end.

### 4.6 `addLinkSpan(Block& b, uint32_t begin, uint32_t end, int32_t link)`

This inserts a link over `[begin, end)` while keeping the other styles of the text (spans are style runs). Here it is verbatim:

```cpp
void addLinkSpan(Block& b, uint32_t begin, uint32_t end, int32_t link) {
  int32_t endLink = -1;
  const uint8_t endFlags = spanFlagsAt(b, end, &endLink);
  const uint8_t beginFlags = spanFlagsAt(b, begin);
  std::vector<Span> out;
  out.reserve(b.spans.size() + 2);
  for (const Span& s : b.spans) {
    if (s.begin < begin) out.push_back(s);
  }
  out.push_back(Span{begin, static_cast<uint8_t>(beginFlags | kSpanLink), link});
  for (const Span& s : b.spans) {
    if (s.begin > begin && s.begin < end) out.push_back(Span{s.begin, static_cast<uint8_t>(s.flags | kSpanLink), link});
  }
  const bool spanAtEnd = std::any_of(b.spans.begin(), b.spans.end(), [&](const Span& s) { return s.begin == end; });
  if (end < b.text.size() && !spanAtEnd) out.push_back(Span{end, endFlags, endLink});
  for (const Span& s : b.spans) {
    if (s.begin >= end) out.push_back(s);
  }
  b.spans = std::move(out);
}
```

The effect on existing spans:
- Spans before `begin` are kept.
- A span starting exactly at `begin` is replaced by the new span, which carries the flags in effect at `begin` plus `kSpanLink`.
- Spans inside `(begin, end)` keep their flags, gain `kSpanLink`, and have their link index replaced.
- A span that restores the old style (flags and link in effect at `end` before the change) is added at `end` only if `end` is before the end of the text and no span already starts at `end`.
- Spans from `end` on are kept unchanged.
- With no spans at all, the result is `[{begin, kSpanLink, link}]`, plus `{end, 0, -1}` if `end < text.size()`.

### 4.7 `Document::finalize()`

```
total = 0                                     // uint64_t
for b in blocks:
    b.charStart = total
    total += utf8Length(b.text)
    if b.type == BlockType::Image or b.type == BlockType::EmptyLine: total += 1
totalChars = total
std::stable_sort(toc, [](a, b) { return a.block < b.block; })     // FB2 notes bodies may come in any order
for b in blocks:
    if b.type == BlockType::Image or b.text.size() < 8: continue
    for (begin, end) in findWebAddresses(b.text):     // computed once per block, before its spans change
        int32_t existing = -1                         // out-parameter only, not used afterwards
        linked = (spanFlagsAt(b, begin, &existing) & kSpanLink) != 0
        for s in b.spans: linked = linked or (s.begin > begin and s.begin < end and (s.flags & kSpanLink))
        if linked: continue                           // already a link in the book (FB2 <a href>)
        target = b.text.substr(begin, end - begin)
        if startsWithNoCase(target, 0, "www."): target = "https://" + target    // case of the text kept
        links.push_back(std::move(target))
        addLinkSpan(b, begin, end, int32_t(links.size()) - 1)
```

The 8-byte minimum is checked on the block, not on the address. A block whose whole text is the 7-byte valid address `www.a.b` is therefore not linked, while `" www.a.b"` is. Calling `finalize` twice gives the same result: addresses that are already links are skipped.

### 4.8 `tocIndexForBlock`, `plainText`, `authorsJoined`

- **`Document::tocIndexForBlock(block)`**: a binary search with `lo = 0` and `hi = int(toc.size()) − 1`. It returns the **last** index whose `toc[idx].block ≤ block`, or −1 when there is none (including an empty TOC). Among equal `block` values, the last one wins.
- **`Document::plainText(first, last)`**: clamps `first = max(0, first)` and `last = min(last, int(blocks.size()))`. For `i` in `[first, last)` it skips blocks with empty `text` and joins the rest with `'\n'`. No trailing newline is added, and it returns `""` when `first >= last`.
- **`BookMeta::authorsJoined()`**: joins the non-empty `authors` with `", "`.

### 4.9 Tests that constrain this file

- `testWebAddresses`:
  - In the test string it must find exactly 4 addresses:
    - `https://www.gutenberg.org/ebooks/1342`: the sentence full stop is trimmed.
    - `www.example.com`: the comma is trimmed.
    - `http://a.b/c_(d)`: the address's own brackets are kept and the outer `)` is dropped by the balance rule.
    - `http://x.ru/путь`: a Cyrillic path, stopped by `»`.
  - It must find none in `"version 1.2, file.txt, e.g. me@www.x.com, www."`.
  - `isWebLink` must accept `https://`, upper-case `HTTP://` and `mailto:`, and reject `#note1`.
  - `finalize` on `"Visit https://example.com/page now"` with spans `{0, italic}` must give spans `{0, I, -1}`, `{6, I|L, 0}`, `{30, I, -1}`. At offset 6 the result is link and italic with link 0; at 29 it is a link; at 30 it is italic, not a link, with link −1; at 2 it is not a link.
  - `finalize` on `"go http://x.org and www.gutenberg.org"` with an existing link span `{3, L, 0}, {15, 0, -1}` must leave the first address alone and add `links[1] == "https://www.gutenberg.org"`, with offset 22 linked to 1.
- `checkSampleDoc` (FB2 and zipped FB2): `spanFlagsAt` (italic, note reference with link), `plainText` of the note's anchor range, `totalChars > 100`, and TOC order (the notes body comes last).
- `testTxtTypography`: `spanFlagsAt`.
- Only with `LL_TESTS_WITH_TEXT`, `testTextLayout`: the narrow-column document must get exactly one link from `finalize`.

---

## 5. `src/core/FileUtil.cpp`

### 5.1 Layout

The file includes `<cstdint>`, `<filesystem>`, `<fstream>` and `"core/BookLoader.h"`. All paths are converted with `pathFromUtf8` (declared in `BookLoader.h`; UTF-8 → `std::filesystem::path` through `std::u8string`). Definition order: `writeFileAtomic`, `fileExists`, `isDirectory`, `fileSize`. Every filesystem call uses the `std::error_code` overloads.

### 5.2 `writeFileAtomic(path, data)`

```cpp
const std::filesystem::path target = pathFromUtf8(path);
std::filesystem::path tmp = target;
tmp += ".tmp";                                         // "<path>.tmp", same directory
{
  std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
  if (!f) return false;                                // cannot create: nothing is written
  f.write(data.data(), static_cast<std::streamsize>(data.size()));
  if (!f) return false;                                // write error: the .tmp file is left behind
}                                                      // stream closed here (close result not checked)
std::error_code ec;
std::filesystem::rename(tmp, target, ec);
if (ec) {
  std::filesystem::remove(target, ec);                 // resets ec
  std::filesystem::rename(tmp, target, ec);
}
return !ec;
```

There is no fsync and no directory creation. If the second rename fails, the function returns false: the target may already have been removed and the `.tmp` file remains.

### 5.3 Queries

- **`fileExists(path)`**: `std::filesystem::is_regular_file(pathFromUtf8(path), ec)`. False for directories and on errors.
- **`isDirectory(path)`**: `std::filesystem::is_directory(…, ec)`.
- **`fileSize(path)`**: `std::filesystem::file_size(…, ec)`, or 0 when `ec` is set (missing file, directory).

### 5.4 Tests

`testLibrarySearch` calls `cache.save(cacheFile)`, which is `MetaCache::save` → `writeFileAtomic`. It must return true, and `MetaCache::load` must read the file back. Settings saving also uses `writeFileAtomic`.

---

## 6. `src/core/ImageCodec.cpp`

### 6.1 stb configuration

The file includes `<cstdio>`, `<cstring>`, `<filesystem>`, `<fstream>` and `<string>`, then the following block verbatim. This is the only translation unit in the project that compiles the stb implementations:

```cpp
#define STB_IMAGE_IMPLEMENTATION
#define STBI_NO_STDIO
#define STBI_NO_HDR
#define STBI_NO_LINEAR
#define STBI_NO_PSD
#define STBI_NO_PIC
#define STBI_NO_PNM
#include <stb_image.h>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBI_WRITE_NO_STDIO
#include <stb_image_write.h>
```

The headers come from the vcpkg `stb` port (`${Stb_INCLUDE_DIR}`, pinned baseline: stb_image v2.30, stb_image_write v1.16), unmodified, and no other `STBI_*` option is set. As a result:
- The decoders compiled in are JPEG (baseline and progressive), PNG, BMP, GIF and TGA. PSD, PIC, PNM and HDR are excluded, and so are the FILE-based and float (`stbi_loadf`) APIs.
- Images are never flipped: `stbi_set_flip_vertically_on_load` and `stbi_flip_vertically_on_write` are never called, so row 0 is the top row.
- GIFs decode to their first frame, and 16-bit PNGs are reduced to 8 bits by stb.
- The PNG writer uses stb's defaults: compression level 8 and automatic filter selection.

### 6.2 `probeImageSize(data, size, width, height)`

1. Sets `width = height = 0`.
2. Returns false if `!data || size == 0 || size > 0x7fffffff`.
3. Otherwise, with a local `int comp`, returns `stbi_info_from_memory(data, int(size), &width, &height, &comp) != 0 && width > 0 && height > 0`.

Only the header is read; the sizes are written by stb.

### 6.3 `decodeImageRgba(data, size, rgba, width, height)`

1. Sets `width = height = 0`, with the same guard as above (return false).
2. Calls `px = stbi_load_from_memory(data, int(size), &width, &height, &comp, 4)` (4 channels requested). If `px` is null, returns false and leaves `rgba` untouched.
3. Otherwise does `rgba.assign(px, px + size_t(width) * height * 4)`, calls `stbi_image_free(px)` and returns true. The output is tightly packed RGBA8, top row first.

### 6.4 `writePngRgba(utf8Path, rgba, width, height)`

- The anonymous namespace, placed between `decodeImageRgba` and `writePngRgba`, defines `void writeToVector(void* context, void* data, int size)`. It appends `size` bytes to the `std::string*` passed as `context`.
- The PNG is encoded entirely in memory with `stbi_write_png_to_func(writeToVector, &png, width, height, 4, rgba, width * 4)`. If that returns 0, the function returns false.
- The path is `std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(utf8Path)))`, built here directly rather than through `pathFromUtf8`.
- The bytes are written with `std::ofstream f(p, std::ios::binary)` (truncating, not atomic). It returns false if the stream fails to open, otherwise `static_cast<bool>(f)` after the write.

### 6.5 Tests

`testFb2`: the FB2 sample embeds a 1×1 PNG cover, which `Fb2Parser::finishBinary` probes with `probeImageSize`. On failure it would clear the image bytes. `decodeImageRgba` is used by the app for textures and `writePngRgba` by the screenshot/self-test mode; neither has a direct unit test.

---

## Checklist

Bytes are written in C escape notation, `→` means "returns/produces", and `U+XXXX` stands for the UTF-8 encoding of that code point.

**Unicode**
1. Decoding `"a\xC3(b\xE2\x82"` with repeated `utf8Decode` takes 6 steps: `a`, U+FFFD, `(`, `b`, U+FFFD, U+FFFD.
2. `utf8Validate("a\xC3(b\xE2\x82", &m, &e)` → false, `m == 0`, `e == 3`.
3. `utf8Validate("Ёж", &m, &e)` → true, `m == 2`, `e == 0`. `utf8Validate("\xEF\xBF\xBD", &m, &e)` → true, `m == 1`.
4. `utf8Decode` on `"\xC0\x80"`, `"\xE0\x80\x80"`, `"\xED\xA0\x80"` and `"\xF4\x90\x80\x80"` gives one U+FFFD per byte (2, 3, 3 and 4 steps). `"\xF0\x9F\x98\x80"` → U+1F600 in one step of 4 bytes.
5. `utf8Append`:

   | input | bytes |
   |---|---|
   | 0x7F | `7F` |
   | 0x80 | `C2 80` |
   | 0x7FF | `DF BF` |
   | 0x800 | `E0 A0 80` |
   | 0xD800 | `EF BF BD` |
   | 0xFFFF | `EF BF BF` |
   | 0x10000 | `F0 90 80 80` |
   | 0x10FFFF | `F4 8F BF BF` |
   | 0x110000 | `EF BF BD` |
6. `utf8Length("Ёж «ёлка» — Straße")` → 18, and `u32ToUtf8(utf8ToU32(s)) == s`.
7. `utf8AlignBack`: `("Ж", 1)` → 0; `(s, s.size())` → `s.size()`; `("\x80\x80\x80\x80\x80", 4)` → 1 (at most 3 steps).
8. `utf8NextPos`: `("Жx", 0)` → 2; `("Жx", 1)` → 2; `("Жx", 3)` → 3.
9. `utf8PrevPos`: `("Жx", 3)` → 2; `("Жx", 2)` → 0; `("Жx", 0)` → 0; `("Жx", 99)` → 2.
10. `toLowerCp`:

    | input | result |
    |---|---|
    | U+00C9 | U+00E9 |
    | U+00D7 | U+00D7 |
    | U+00DF | U+00DF |
    | U+0130 | `i` |
    | U+0178 | U+00FF |
    | U+0139 | U+013A |
    | U+0141 | U+0142 |
    | U+0152 | U+0153 |
    | U+017D | U+017E |
    | U+0386 | U+03AC |
    | U+0388 | U+03AD |
    | U+038C | U+03CC |
    | U+038F | U+03CE |
    | U+03A3 | U+03C3 |
    | U+03AA | U+03AA |
    | U+0401 | U+0451 |
    | U+0407 Ї | U+0457 ї |
    | U+042F | U+044F |
    | U+0462 | U+0463 |
    | U+0490 | U+0491 |
    | U+04C0 | U+04CF |
    | U+04C1 | U+04C2 |
    | U+04D0 | U+04D1 |
    | U+0181 | U+0181 |
    | U+1E9E | U+1E9E |
11. `toUpperCp`:

    | input | result |
    |---|---|
    | U+00FF | U+0178 |
    | U+00B5 | U+00B5 |
    | U+00F7 | U+00F7 |
    | U+0131 | `I` |
    | U+0130 | U+0130 |
    | U+013A | U+0139 |
    | U+0153 | U+0152 |
    | U+017E | U+017D |
    | U+03C2 | U+03A3 |
    | U+03C3 | U+03A3 |
    | U+03AC | U+0386 |
    | U+03AF | U+038A |
    | U+03CC | U+038C |
    | U+03CE | U+038F |
    | U+03CA | U+03CA |
    | U+044F я | U+042F Я |
    | U+0451 | U+0401 |
    | U+0491 | U+0490 |
    | U+04CF | U+04C0 |
    | U+04C2 | U+04C1 |
    | U+04D1 | U+04D0 |
12. `isSpaceCp` is true for U+000B, U+000C, U+1680, U+2006, U+2008, U+205F and U+3000, and false for U+00A0, U+2007, U+202F, U+200B, U+0085 and U+FEFF.
13. `isLetterCp` is true for U+00AA, U+00B5, U+0386, U+05D0, U+0627, U+4E2D and U+AC00, and false for U+00D7, U+0370, U+0387, U+0482, U+0660 and `'5'`.
14. `isCyrillicCp(U+0481)` → true; `(U+0482)` → false; `(U+048A)` → true; `(U+1C88)` → true; `(U+1C89)` → false; `(U+A69F)` → true.
15. `isDashCp`: U+2010 and U+2212 → true; U+2011 and U+00AD → false. `isOpeningPunctCp`: `«`, `“`, `‘`, `‚`, `‹` and `(` → true; `»`, `”`, `’` and `<` → false.
16. `foldForSearchCp`:

    | input | result |
    |---|---|
    | `Ё` | U+0435 |
    | `É` | `e` |
    | `Æ` | U+00E6 |
    | `ß` | U+00DF |
    | `Ø` | `o` |
    | `Ÿ` | `y` |
    | `Ł` | `l` |
    | `ı` | `i` |
    | `İ` | `i` |
    | `Œ` | U+0153 |
    | `’` | `'` |
    | `` ` `` | `'` |
    | `´` | `'` |
    | `″` (U+2033) | `"` |
    | U+2011 | `-` |
    | U+00A0 | ` ` |
    | U+202F | ` ` |
    | `\t` | ` ` |
    | U+3000 | ` ` |
    | `Σ` | `σ` |
    | U+00AD | U+00AD |
17. `foldForSearch`:

    | input | result |
    |---|---|
    | `"ЁЛКА  «Ёжик»\tCafé"` | `"елка \"ежик\" cafe"` |
    | `"  a"` | `" a"` |
    | `"e\xCC\x81"` | `"e"` |
    | `"a\xC2\xAD\xC2\xADb"` | `"ab"` |
    | `"x \xE2\x80\x8B y"` | `"x y"` |
18. `toLowerUtf8("ПРИВЕТ Мир ЁЖ")` → `"привет мир ёж"`; `toLowerUtf8("\xFF")` → `"\xEF\xBF\xBD"`.
19. `trimView`: `(" \t\xC2\xA0abc\xC2\xA0\n")` → `"abc"`; `("\fabc")` → `"\fabc"`.
20. `collapseSpaces`: `("  a \t b\n\nc  ")` → `"a b c"`; `("a\xC2\xA0 b")` → `"a\xC2\xA0 b"`; `("\xFF  x")` → `"\xFF x"` (the raw byte is kept).
21. `iequalsAscii("ABC", "abc")` → true; `iequalsAscii("Ж", "ж")` → false; `endsWithNoCase("Book.FB2", ".fb2")` → true; `startsWith("abc", "AB")` → false.

**Encoding**

22. `charsetName` gives `"UTF-8"`, `"UTF-16LE"`, `"UTF-16BE"`, `"windows-1251"`, `"KOI8-R"`, `"CP866"`, `"ISO-8859-5"`, `"windows-1252"`, and `"unknown"` for Unknown.
23. `charsetFromName`:

    | name | result |
    |---|---|
    | `"Windows-1251"` | Cp1251 |
    | `"Windows 1251"` | Cp1251 |
    | `"koi8-r"` | Koi8R |
    | `"KOI8-U"` | Koi8R |
    | `"IBM866"` | Cp866 |
    | `"ISO_8859-5"` | Iso8859_5 |
    | `"Latin1"` | Cp1252 |
    | `"US-ASCII"` | Cp1252 |
    | `"UTF_8"` | Utf8 |
    | `"unicode"` | Utf16LE |
    | `"UTF-16"` | Utf16LE |
    | `""` | Unknown |
    | `" utf-8"` | Unknown |
    | `"utf-32"` | Unknown |
24. `detectBom`: `"\xEF\xBB\xBFx"` → Utf8, len 3; `"\xFF\xFE"` → Utf16LE, len 2; `"\xFE\xFF"` → Utf16BE, len 2; `"\xEF\xBB"` → Unknown, len 0.
25. `decodeToUtf8(…, Cp1251)`: `"\xC0\xFF"` → `"Ая"`; `"\xA8\xB8"` → `"Ёё"`; `"\xB9"` → `"№"`; `"\x98"` → U+FFFD; `"\x88"` → `"€"`.
26. `decodeToUtf8(…, Koi8R)`: `"\xC1"` → `"а"`; `"\xE1"` → `"А"`; `"\xA3"` → `"ё"`; `"\xB3"` → `"Ё"`; `"\xDF"` → `"ъ"`; `"\xFF"` → `"Ъ"`; `"\x9A"` → U+00A0; `"\xBF"` → `"©"`.
27. `decodeToUtf8(…, Cp866)`: `"\x80"` → `"А"`; `"\xAF"` → `"п"`; `"\xE0"` → `"р"`; `"\xEF"` → `"я"`; `"\xF0\xF1"` → `"Ёё"`; `"\xFC"` → `"№"`; `"\xC4"` → U+2500; `"\xFF"` → U+00A0.
28. `decodeToUtf8(…, Iso8859_5)`: `"\x85"` → U+0085; `"\xA1"` → `"Ё"`; `"\xAD"` → U+00AD; `"\xB0"` → `"А"`; `"\xF0"` → `"№"`; `"\xF1"` → `"ё"`; `"\xFD"` → `"§"`; `"\xFF"` → `"џ"`.
29. `decodeToUtf8(…, Cp1252)`: `"\x80"` → `"€"`; `"\x81"` → U+FFFD; `"\x93\x94"` → `"“”"`; `"\x9F"` → `"Ÿ"`; `"\xE9"` → `"é"`.
30. `decodeToUtf8("a\xFFb", Utf8)` → `"a\xEF\xBF\xBDb"`. Valid UTF-8 (also with Unknown) is returned byte-identical.
31. UTF-16:
    - `decodeToUtf8("\x3D\xD8\x00\xDE", Utf16LE)` → U+1F600.
    - `("\x3D\xD8\x41\x00", Utf16LE)` → U+FFFD then `"A"`.
    - `("\x00\xDC", Utf16LE)` → U+FFFD.
    - `("\x3D\xD8", Utf16LE)` → U+FFFD.
    - `("\x41\x00\x42", Utf16LE)` → `"A"` (the odd byte is dropped).
    - `("\x00\x41", Utf16BE)` → `"A"`.
32. `detectCharset`:
    - `""` → Utf8; `"hello"` → Utf8; `"Caf\xE9"` → Cp1252.
    - 16 ASCII characters as UTF-16LE without a BOM (32 bytes) → Utf16LE; the same as BE → Utf16BE.
    - `"A\0B\0C\0"` (6 bytes, below the 16-byte minimum) → Utf8.
33. `detectCharset` of the core_tests Tolstoy sample encoded in Cp1251, KOI8-R and CP866 → that charset. The UTF-8 original → Utf8. The core_tests Western sample → Cp1252.
34. `bytesToUtf8("\xEF\xBB\xBF" "abc", Cp1251, &u)` → `"abc"`, `u == Utf8` (the BOM beats the hint).
35. `bytesToUtf8("\xD0\x96", Cp1251)` → `"Р–"` (U+0420 U+2013: a non-UTF-8 hint is trusted).
36. `bytesToUtf8(cp1251Sample, Utf8, &u)` → the Russian text, `u == Cp1251`. `bytesToUtf8("abc", Unknown, &u)` → `"abc"`, `u == Utf8`.

**XmlReader**

37. The `testXml` sequence (§3.8) is reproduced exactly.
38. `<p>a<!--x-->b</p>` → StartTag p, Text `"a"`, Text `"b"`, EndTag p, End.
39. `<![CDATA[a &amp; <b>]]>` → Text `"a &amp; <b>"`, End. `<![CDATA[]]>` → Text `""`.
40. `<!DOCTYPE x [<!ENTITY a 'b'>]><r/>` → StartTag r (selfClosing), EndTag r, End.
41. `</p <p>` → EndTag `"p"`, then StartTag `"p"`, then End.
42. `<a href=x/y/>t` → StartTag a, `attr("href") == "x/y/"`, `selfClosing() == false`, then Text `"t"`.
43. `<image l:href="#c"/>` → StartTag with `attr("href") == "#c"`; the next EndTag still has `name() == "image"`, `selfClosing()` and `attr("href") == "#c"`.
44. `<td nowrap>` → `hasAttr("nowrap")` → true, `attr("nowrap")` → `""`. `<p a="1" a="2">` → `attr("a") == "1"`.
45. `<a href="x>text` (no closing quote) → StartTag a with `href == "x"`, then Text `"text"`.
46. `<p class='x'<b>` → StartTag p (class `"x"`), then StartTag b.
47. `a < b` → Text `"a < b"`; `x<` → Text `"x<"`; `<3` → Text `"<3"`; `<<p>` → Text `"<"`, then StartTag p.
48. `<p>broken <emphasis>text</section` → StartTag p, Text `"broken "`, StartTag emphasis, Text `"text"`, EndTag `"section"`, End.
49. `</ l:p >` → EndTag `"p"`; `</>` → EndTag `""`.
50. `xmlDecodeEntities`:

    | input | output |
    |---|---|
    | `"&#151;"` | `"—"` |
    | `"&#x97;"` | `"—"` |
    | `"&#129;"` | U+FFFD |
    | `"&#0;"` | `"&#0;"` |
    | `"&#xD800;"` | U+FFFD |
    | `"&#1114112;"` | `"&#1114112;"` |
    | `"&AMP;"` | `"&AMP;"` |
    | `"&Prime;&prime;"` | `"″′"` |
    | `"&#65;&#X42;"` | `"AB"` |
    | `"&#x0x41;"` | `"A"` |
    | `"&#+65;"` | `"A"` |
    | `"&#0000000065;"` | `"A"` |
    | `"&#00000000065;"` | unchanged |
    | `"&;"` | unchanged |
    | `"& amp;"` | unchanged |
    | `"AT&T;"` | unchanged |
    | `"&&amp;"` | `"&&"` |
    | `"&nbsp;"` | U+00A0 |

**Document**

51. `findWebAddresses` of the core_tests text → the 4 addresses listed in §4.9. `findWebAddresses("version 1.2, file.txt, e.g. me@www.x.com, www.")` → empty.
52. `findWebAddresses`:

    | input | result |
    |---|---|
    | `"http://localhost/x"` | empty |
    | `"www.abc"` | empty |
    | `"www.a.b"` | `[(0,7)]` |
    | `"WWW.X.ORG"` | `[(0,9)]` |
    | `"x.www.y.com"` | empty |
    | `"mailto:a@b.c"` | empty |
    | `"http://http://a.b"` | empty |
53. `findWebAddresses`:

    | input | address found |
    |---|---|
    | `"(see http://a.b/c)."` | `"http://a.b/c"` |
    | `"http://a.b/c[1]"` | the whole string |
    | `"http://x.org…"` | `"http://x.org"` |
    | `"\"http://x.org\""` | `"http://x.org"` |
    | `"сайтwww.example.com"` | `"www.example.com"` |
    | `"http://a.b/c'*"` | `"http://a.b/c"` |
54. `isWebLink`: `"HTTP://X.ORG"` → true; `"mailto:a@b.c"` → true; `"ftp://x"` → true; `"#note1"` → false; `" http://x"` → false.
55. `finalize` gives the span results listed in §4.9 for both test blocks. `links` gets `"https://"` prepended only for `www.` addresses, and the case of the text is kept (`"WWW.X.ORG"` → `"https://WWW.X.ORG"`).
56. `finalize` on blocks `["ab", Image "", EmptyLine "", "cd"]` → `charStart` 0, 2, 3, 4 and `totalChars == 6`.
57. `finalize` on a block with text `"www.a.b"` (7 bytes) → no link; on `" www.a.b"` → `links == {"https://www.a.b"}` and spans `[{1, kSpanLink, 0}]`.
58. `addLinkSpan` behaviour through `finalize`: for text `"see http://a.b/x now"` with spans `[{0,0,-1},{10,Bold,-1}]`, the result is `[{0,0,-1},{4,Link,0},{10,Bold|Link,0},{16,Bold,-1}]`.
59. `tocIndexForBlock` with TOC blocks `[0,5,5,10]`:

    | block | result |
    |---|---|
    | −1 | −1 |
    | 0 | 0 |
    | 4 | 0 |
    | 5 | 2 |
    | 9 | 2 |
    | 10 | 3 |
    | 100 | 3 |

    With an empty TOC the result is −1.
60. `plainText` with block texts `["a", "", "b"]`: `(0,3)` → `"a\nb"`; `(-5,100)` → `"a\nb"`; `(2,1)` → `""`.
61. `spanFlagsAt` with spans `[{2,Italic,-1},{5,Bold|Link,3}]`:

    | offset | flags | link |
    |---|---|---|
    | 0 | 0 | −1 |
    | 2 | Italic | −1 (the span's own `link`) |
    | 4 | Italic | −1 |
    | 5 | Bold\|Link | 3 |
    | 1000 | Bold\|Link | 3 |

    With no spans the result is 0.
62. `authorsJoined` of `{"A", "", "B"}` → `"A, B"`.

**FileUtil**

63. `writeFileAtomic("<dir>/a.json", "x")` → true. The file contains `"x"` and no `"<dir>/a.json.tmp"` remains. An existing file is replaced.
64. `writeFileAtomic` into a non-existent directory → false, and nothing is created.
65. `fileExists(<dir>)` → false; `isDirectory(<dir>)` → true; `fileSize("<missing>")` → 0; `fileSize(<5-byte file>)` → 5.

**ImageCodec**

66. `probeImageSize` of the core_tests 1×1 PNG (decoded from base64) → true, 1×1. `probeImageSize(nullptr, 10, w, h)` and `probeImageSize(p, 0, w, h)` → false with `w == h == 0`.
67. PSD (`"8BPS…"`), PNM (`"P6\n…"`), Radiance HDR and Softimage PIC data → `probeImageSize` and `decodeImageRgba` return false (those decoders are compiled out). JPEG, PNG, BMP, GIF and TGA work.
68. `decodeImageRgba` of the 1×1 PNG → true, `w == h == 1`, `rgba.size() == 4`. A multi-row image has its top row at `rgba[0]`.
69. `writePngRgba(path, px, w, h)` → true and writes a PNG file (starting `89 50 4E 47 0D 0A 1A 0A`). Decoding it gives back the same RGBA bytes, with row 0 at the top.
