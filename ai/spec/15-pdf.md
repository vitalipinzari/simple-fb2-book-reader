# 15 — PDF: file reader, decryption, page content and reflowed books

This file specifies the four translation units that read PDF books (new in 0.7.0). `src/core/PdfReader.cpp` is the object layer: the tokenizer and object parser, cross-reference tables and streams, object streams, the repair scan of damaged files, the stream filters, PDF text strings and the "LLPDFIM1" container in which pictures are kept still compressed. `src/core/PdfCrypt.cpp` holds MD5, SHA-256/384/512, RC4 and AES and the standard security handler for files that open with the empty user password. `src/core/PdfContent.cpp` turns pages into positioned characters and placed pictures: the page tree, fonts (encodings, glyph names, CMaps, embedded TrueType `cmap` tables, Type 1 built-in encodings, widths) and the content stream interpreter. `src/core/PdfParser.cpp` rebuilds a reflowable book from that: lines, columns, tables, footnotes, running heads, paragraphs, headings, pictures, the cover, the table of contents and the metadata, behind the three public functions of `PdfParser.h`. The verbatim headers `PdfReader.h`, `PdfCrypt.h`, `PdfContent.h` and `PdfParser.h` hold every declaration, member, default value and the constant `kMaxStreamBytes` (256 MiB); this file refers to them by name and does not restate them. The files rely on `Unicode.h` (spec 03 § 1), `Document.h` and `Document::finalize()` (03 § 4), `probeImageSize` from `ImageCodec.h` (03 § 6), `guessMetaFromFileStem` from `TxtParser.h` (04 B.12), miniz (inflate) and stb_image (JPEG pictures). `PdfReader.cpp`, `PdfCrypt.cpp` and `PdfContent.cpp` are in namespace `ll::pdf`; the public functions of `PdfParser.cpp` are in namespace `ll`. A helper called "file-local" sits in an unnamed namespace in its `.cpp`. None of the files uses SDL, OpenGL, locales or mutable global state other than the function-local static tables named below. Nothing throws on purpose; the only `try`/`catch` blocks are the guards of `decodeImageContainer` (A.12) and of the three public functions of `PdfParser.h` (D.19), which turn a `std::exception` (in practice `std::bad_alloc` for a file or a picture that does not fit in memory) into a plain failure. As everywhere in this folder, the quirks described here are part of the copy: do not "fix" them.

---

## 0. Notation, shared behaviour and the entry points

**Notation.**
- Bytes are written `0xNN`, code points `U+XXXX`; ranges are inclusive. `s[a:b]` is the byte range `a ≤ k < b`.
- For a PDF `Object` (header `PdfReader.h`): `num(def)` is the value of an `Int` or `Real` (otherwise `def`, default 0); `integer(def)` is an `Int`, a `Real` truncated toward zero, otherwise `def`; `isDict()` is true for dictionaries **and** streams; `size()` is the element count of an array and 0 for anything else; `at(k)` is a null object when out of range; `o[key]` is the direct (unresolved) entry or a null object. "Direct" below means the value as written, without following an indirect reference; "resolved" means passed through `File::resolve`.
- *User space* is PDF's own coordinate system (points, y up). *Page space* (header `PdfContent.h`) is points with the origin at the top left of the visible page and y going down; every coordinate in Parts C and D is in page space unless stated otherwise.
- In Part D, `em` is a font size in page units and every layout value is a `float`, as the members of `Glyph`, `PageContent` and the structures of D.3 are. Constants written `0.3` are `float` literals (`0.3f`) there unless the text says `double`. Matrices in Part C use `double`.

**Shared helpers** (spec 03 § 1) that results depend on: `utf8Decode` never stalls and returns U+FFFD for a bad byte; `utf8Append` writes U+FFFD for surrogates and values above U+10FFFF; `utf8Validate(s, &multi, &errors)`; `isLetterCp` (Latin, Cyrillic, Greek and the other ranges of 03 § 1.6), `isLatinLetterCp`, `isCyrillicCp`, `isDigitCp` (ASCII digits only), `toLowerCp`/`toUpperCp`, `toLowerUtf8`, `trimView`/`trimCopy` (ASCII space, tab, CR, LF and NBSP at both ends), `collapseSpaces` (runs of `isSpaceCp` become one space, ends trimmed; NBSP is kept).

**Entry points wired in elsewhere** (specified in 03 and 04, listed here only so that the callers are known):
- `BookLoader.cpp` reads the first 1024 bytes of a file; when `looksLikePdf(head)` is true (and the file is not a zip) the content format is `BookFormat::Pdf` whatever the name. `loadBook` calls `parsePdf(raw, doc, fileStemOf(path), err)` with default options; `loadBookText` calls `pdfExtractText(raw, text, meta, fileStemOf(path))`; `loadBookMeta` passes the first 256 KiB and the last 512 KiB (or the head itself when it is the whole file) to `parsePdfMeta`, then on failure the whole file (`parsePdfMeta(full, full, full.size(), meta)`), and then calls `guessMetaFromFileStem`.
- `ImageCodec.cpp`: `probeImageSize` and `decodeImageRgba` first ask `pdf::isImageContainer(data, size)`; for a container they return `pdf::imageContainerSize(...)` and `pdf::decodeImageContainer(...)` instead of calling stb_image.
- Pictures reach the book model as `ImageData` with `mime` `"image/jpeg"` (a JPEG passed through) or `"application/x-lanternleaf-pdf-image"` (a container), see D.16.

---

## Part A — `src/core/PdfReader.cpp`

### A.1 Includes and layout

Includes, in this order: `core/PdfReader.h`, `<miniz.h>`, `<algorithm>`, `<cmath>`, `<cstring>`, `<exception>`, `<unordered_set>`, `core/PdfCrypt.h`, `core/Unicode.h`, then

```cpp
#define STBI_NO_STDIO
#include <stb_image.h>
```

for the declarations of `stbi_load_from_memory` and `stbi_image_free` only (the implementation is compiled once, in `ImageCodec.cpp`). `std::atoi` and `INT64_MAX` are reached through these headers.

Definition order: an unnamed namespace with the constants, the byte helpers, the five decoders and `unpredict`, and the two PDFDocEncoding tables; then `nullObject` and the `Object` members; `isPdfSpace`, `isPdfDelimiter` and the `Lexer` members; `pdfDocEncodingToUnicode` and `textToUtf8`; `canonicalFilterName`, `isImageCodecFilter`, `filterParams`, `applyFilter`; `struct File::Crypt { CryptHandler handler; };` and the `File` members; a second unnamed namespace with `kImageMagic`, `struct Reader` and `sampleAt`; `encodeImageContainer`, `isImageContainer` and `imageContainerSize`; a third unnamed namespace with `decodeContainer`; finally `decodeImageContainer`.

### A.2 Constants and byte helpers (file-local)

```cpp
constexpr int kMaxDepth = 64;              // nesting of arrays and dictionaries
constexpr int kMaxObjectNumber = 8000000;  // larger numbers are treated as damage
constexpr size_t kMaxArrayItems = 4000000;
```

- `bool isDigit(unsigned char c)`: `'0'..'9'`.
- `int hexValue(unsigned char c)`: `0-9`, `a-f`, `A-F` → 0..15; anything else → −1.
- `uint32_t readU32(const unsigned char* p)`: four bytes, little-endian.
- `void putU32(std::string& out, uint32_t v)`: appends four bytes, little-endian.

### A.3 Objects

- `nullObject()` returns a function-local `static const Object` (type `Null`).
- `Object::at(k)`: the element when `isArray() && k < a->size()`, else `nullObject()`.
- `Object::find(key)`: `nullptr` unless `isDict()`; otherwise a linear search of the `Dict` vector, the **first** entry with that key wins.
- `Object::operator[](key)`: `*find(key)` or `nullObject()`.

### A.4 The lexer

- `isPdfSpace(c)`: space, `\n`, `\r`, `\t`, `\f` and NUL.
- `isPdfDelimiter(c)`: `( ) < > [ ] { } / %`.
- `Lexer::skipSpace()`: skips white space and comments. A comment runs from `%` up to (not including) the next CR or LF; the line end is then skipped as white space.

**`token(t)`** calls `skipSpace`, then resets `t.type = Null`, `t.flag = false`, clears `t.s` and resets `t.a` and `t.d`. The other fields (`i`, `r`, `gen`, `streamOffset`, `objNum`, `objGen`) keep whatever they held. At the end of the data it returns false. Otherwise, by the byte `c` at the position:

| `c` | result |
|---|---|
| `/` | `readName` |
| `(` | `readLiteralString` |
| `<` followed by `<` | keyword `<<` (2 bytes) |
| `<` otherwise | `readHexString` |
| `>` | keyword `>>`; consumes 2 bytes when the next byte is `>`, else 1 (a lone `>` also comes back as `>>`) |
| `[` `]` `{` `}` `)` | keyword of that one character (a stray `)` is a keyword) |
| anything else | `readNumberOrKeyword` |

The function returns true in every case except the end of the data.

**`readName`**: type `Name`; skips the `/` and takes every byte up to the next white-space or delimiter byte (a lone `/` gives the empty name). When the raw name contains `#`, it is rewritten: a `#` followed by two hex digits (both present, `k + 2 < size`) becomes that byte; any other `#` is kept literally.

**`readLiteralString`**: type `String`; starts after `(` with depth 1 and reads to the end of the data at most:
- `\` followed by `n r t b f` → LF, CR, TAB, BS, FF; by CR → nothing (a following LF is skipped too); by LF → nothing; by 1–3 octal digits → that value `& 0xFF`; by any other byte → that byte (`\(`, `\)`, `\\` and unknown escapes). A `\` as the last byte of the data ends the string.
- An unescaped `(` increments the depth and is kept; `)` decrements it and is kept unless the depth reaches 0, which ends the string.
- An unescaped CR is stored as LF (a CR LF pair as one LF); every other byte is kept.

**`readHexString`**: type `String`, `flag = true`; reads after `<` up to the first `>` or the end of the data, ignores every byte that is not a hex digit (white space and garbage alike), packs pairs; an odd final digit `d` adds the byte `d << 4`.

**`readNumberOrKeyword`**: takes the bytes up to the next white-space or delimiter byte (at least one byte, so it never stalls) as the word `w`.
1. Leading `+` and `-` signs are skipped, any number of them; the value is negative when at least one of them is `-` (`--5` and `+-5` are −5).
2. `numeric` starts as "at least one byte after the signs". The rest is scanned: digits are counted; before a dot each digit is accumulated as `ip = ip * 10 + d` only while `ip < (INT64_MAX - 9) / 10` (further integer digits are dropped, so `99999999999999999999` reads as 999999999999999999); after the dot they add `d * scale` with `scale /= 10` first; the first `.` is accepted; any other byte (including a second `.`) makes the word non-numeric.
3. Numeric with at least one digit: no dot → `Int` (`t.i = ±ip`); with a dot → `Real` (`t.r = ±(ip + frac)`). So `.5`, `4.` and `-.5` are reals; `1.2.3`, `+`, `.` and `5e3` are keywords.
4. Otherwise `true`/`false` → `Bool` (`flag`), `null` → `Null`, anything else → `Keyword` with `s = w`.

**`object(o, refs, depth)`** reads one complete object:
- If `token(o)` fails → return false (only at the end of the data).
- Keyword `[` with `depth < kMaxDepth` → an array. Loop: `skipSpace`, remember the position, read a token `e`; stop at the end of the data or at `]` (consumed); stop *without consuming* at `>>`, `endobj`, `stream` or `obj`. A `[` or `<<` token: rewind and read it with `object(e, refs, depth + 1)` (stop the array if that fails). An `Int` with `refs`: if the next two tokens are an `Int` and the keyword `R`, `e` becomes a `Ref` (`i` = object number, `gen` = the second integer); otherwise rewind to just after the first integer. The element is appended only while the array has fewer than `kMaxArrayItems` elements (later ones are read and discarded). Every other token (strings, names, keywords such as `R` or `)`) is an element as it is. Result: `type = Array`, `s` cleared.
- Keyword `<<` with `depth < kMaxDepth` → a dictionary. Loop: `skipSpace`, remember the position, read a token `k`; stop at the end of the data or at `>>`; stop without consuming at `endobj`, `stream`, `obj` or `]`; skip `k` silently when it is not a `Name` (garbage in key position: `<< 1 /A 2 >>` has only `A`). Then `skipSpace`, remember the value position and read a token `v`:
  - end of data → add `(key, null)` and stop;
  - `>>` → add `(key, null)` and stop (consumed);
  - `endobj` or `stream` → rewind to the value position, add `(key, null)` and stop;
  - `[` or `<<` → rewind and read it with `object(v, refs, depth + 1)`; if that fails, stop **without** adding the key;
  - an `Int` with `refs` → the same `n g R` test as in arrays;
  - anything else, including keywords such as `]` or `R`, is the value as it is.
  Each pair is appended (`emplace_back`), so duplicate keys are all kept and `find` sees the first. Result: `type = Dict`, `s` cleared.
- Any other keyword (also `[`/`<<` at `depth >= kMaxDepth`, which are then *not* parsed) → returned as the keyword, true.
- An `Int` with `refs` → the `n g R` test; otherwise the token as it is.

### A.5 Text strings

`pdfDocEncodingToUnicode(c)`: 0x18–0x1F → `kPdfDoc18[c - 0x18]`; 0x80–0xA0 → `kPdfDoc80[c - 0x80]`; 0x7F → U+FFFD; every other byte → the same value (Latin-1). The tables, verbatim:

```cpp
const char32_t kPdfDoc18[8] = {0x02D8, 0x02C7, 0x02C6, 0x02D9, 0x02DD, 0x02DB, 0x02DA, 0x02DC};
const char32_t kPdfDoc80[33] = {0x2022, 0x2020, 0x2021, 0x2026, 0x2014, 0x2013, 0x0192, 0x2044, 0x2039, 0x203A, 0x2212,
                                0x2030, 0x201E, 0x201C, 0x201D, 0x2018, 0x2019, 0x201A, 0x2122, 0xFB01, 0xFB02, 0x0141,
                                0x0152, 0x0160, 0x0178, 0x017D, 0x0131, 0x0142, 0x0153, 0x0161, 0x017E, 0xFFFD, 0x20AC};
```

(0x9F is undefined in PDFDocEncoding and maps to U+FFFD; 0xA0 is the euro sign.)

**`textToUtf8(raw, collapse)`**:
1. **UTF-16**, when `raw` starts with `FE FF` (big-endian) or `FF FE` (little-endian, accepted although PDF only defines the first): walk 2-byte units from offset 2 while `k + 1 < size` (an odd last byte is dropped). A unit U+001B toggles a *language escape* (`ESC lang ESC`): the escape units and every unit between them are dropped. A high surrogate followed (`k + 3 < size`) by a low surrogate is combined; any surrogate left alone becomes U+FFFD. Each value is appended with `utf8Append`.
2. Else **UTF-8 with BOM** (`EF BB BF`): the rest is taken as it is; if it is not valid UTF-8 it is re-encoded with `u32ToUtf8(utf8ToU32(...))`, which turns each bad byte into U+FFFD.
3. Else: `utf8Validate(raw, &multi, &errors)`; with `multi > 0 && errors == 0` the bytes are taken as UTF-8 without a BOM (not allowed, but common); otherwise every byte goes through `pdfDocEncodingToUnicode` (pure ASCII therefore takes this path and only changes 0x18–0x1F and 0x7F).
4. Cleaning, on the UTF-8 bytes:
   - `collapse == false`: keep bytes `>= 0x20` other than 0x7F, plus TAB and LF; drop all other control bytes; return.
   - `collapse == true` (the default): bytes `< 0x20` and 0x7F become spaces, then `collapseSpaces`.

Callers: the document information strings and `/Lang` (D.18) and the outline titles (D.17) use the default `collapse = true`; ActualText (C.11) uses `collapse = false`.

### A.6 Filters

**`canonicalFilterName(name)`**: `Fl` → `FlateDecode`, `LZW` → `LZWDecode`, `AHx` → `ASCIIHexDecode`, `A85` → `ASCII85Decode`, `RL` → `RunLengthDecode`, `DCT` → `DCTDecode`, `CCF` → `CCITTFaxDecode`; any other name is returned unchanged.

**`isImageCodecFilter(name)`**: the canonical name is `DCTDecode`, `JPXDecode`, `CCITTFaxDecode` or `JBIG2Decode`.

**`filterParams(dp)`**: defaults `{predictor 1, colors 1, bpc 8, columns 1, earlyChange 1}`; when `dp.isDict()`, each field is the direct value's `integer(default)` of `Predictor`, `Colors`, `BitsPerComponent`, `Columns`, `EarlyChange` (cast to `int`; nothing is resolved or clamped here).

**`applyFilter(name, p, in, out, maxOut)`** on the canonical name:

| filter | action | result |
|---|---|---|
| `FlateDecode` | `inflateData(in, out, maxOut)`, then `unpredict(out, p)` | false only when `mz_inflateInit2` fails |
| `LZWDecode` | `lzwDecode(in, out, p.earlyChange, maxOut)`, then `unpredict(out, p)` | true |
| `ASCIIHexDecode` | `asciiHexDecode(in, out)` | true |
| `ASCII85Decode` | `ascii85Decode(in, out)` | true |
| `RunLengthDecode` | `runLengthDecode(in, out, maxOut)` | true |
| `Crypt` | `out = in` (`rawStream` already decrypted the stream, or left it as it is for the Identity crypt filter, A.11) | true |
| anything else (`DCTDecode`, `JPXDecode`, `CCITTFaxDecode`, `JBIG2Decode`, unknown names) | — | false |

The decoders never fail on damaged data: they keep what they decoded.

#### `bool inflateData(std::string_view in, std::string& out, size_t maxOut)`

```
out.clear(); if in is empty: return true
raw = true
if in.size() >= 2:
  cmf = in[0], flg = in[1]
  if (cmf & 0x0F) == 8 && (cmf >> 4) <= 7 && ((cmf << 8) | flg) % 31 == 0: raw = false   // a zlib header
for attempt in 0, 1:
  zero an mz_stream; if mz_inflateInit2(&s, raw ? -MZ_DEFAULT_WINDOW_BITS : MZ_DEFAULT_WINDOW_BITS) != MZ_OK: return false
  next_in = in; avail_in = min(in.size(), 0xFFFFFFFF)
  out.resize(min(maxOut, max(in.size() * 4, 4096))); total = 0
  loop:
    if total == out.size():
      if out.size() >= maxOut: break
      out.resize(min(maxOut, out.size() * 2))
    next_out = out + total; avail_out = min(out.size() - total, 0x40000000)
    outBefore = total; inBefore = avail_in
    st = mz_inflate(&s, MZ_SYNC_FLUSH)
    total += bytes produced
    if st == MZ_STREAM_END: break
    if st != MZ_OK && st != MZ_BUF_ERROR: break          // damaged data: keep what was decoded
    if total == outBefore && avail_in == inBefore: break  // no progress: a truncated stream
  mz_inflateEnd; out.resize(total)
  if total > 0 || raw: return true
  raw = true; in.remove_prefix(2)                         // a broken zlib header in front of valid deflate data
return true
```

- Data without a valid zlib header is inflated as raw deflate from its first byte. Data with a valid header that yields nothing is tried again as raw deflate after the two header bytes.
- The loop must go on calling `mz_inflate` while it makes progress, even after all input is consumed: miniz can hold up to a 32 KiB window of decoded output that it only hands over in later calls. Stopping when `avail_in` reaches 0 loses the end of large streams (the unit test inflates 100 000 bytes through a 1 MiB limit).
- A missing or wrong Adler-32 is not an error; truncated or damaged streams return the bytes decoded so far; the output never exceeds `maxOut` (it is cut at `maxOut`).

#### `bool lzwDecode(std::string_view in, std::string& out, int earlyChange, size_t maxOut)`

The LZW decoder of ISO 32000-1 § 7.4.4 (MSB-first codes of 9 to 12 bits, clear code 256, end-of-data 257, first free code 258), with these exact rules:
- A table of 4096 entries `{prefix, last byte, length}`; entries 0–255 are the single bytes.
- Codes are read MSB first from a bit buffer; decoding stops when fewer than `codeLen` bits are left.
- 256 resets `codeLen = 9`, `next = 258`, `prev = −1`. 257 stops.
- The first code after a reset (or at the start) must be < 256, else decoding stops; it is emitted.
- A code `< next` is emitted, and when `next < 4096` the entry `{prev, first byte of the emitted string, len(prev) + 1}` is added at `next++`. A code `== next` (with `next < 4096`) first adds `{prev, first byte of prev's string, len(prev) + 1}` and then emits it. Any larger code stops decoding.
- After each code: `if (next + earlyChange >= (1 << codeLen) && codeLen < 12) ++codeLen`. A full table is not reset; codes stay 12 bits.
- The loop runs while `out.size() < maxOut`; the output is then cut to `maxOut`. Returns true.

#### `void asciiHexDecode(std::string_view in, std::string& out)`

Stops at the first `>`; ignores every non-hex byte; packs pairs of digits; an odd final digit `d` adds `d << 4`.

#### `void ascii85Decode(std::string_view in, std::string& out)`

- A leading `<~` is skipped; decoding stops at the first `~`; PDF white space is skipped.
- `z` when no group is in progress → four zero bytes; a `z` inside a group, and every byte outside `'!'..'u'`, is skipped.
- Five characters make a group: `group = group * 85 + (c - '!')` (in `uint32_t`, wrapping on invalid input), output as four big-endian bytes.
- A final partial group of `n >= 2` characters is padded with `u` (84) and gives `n - 1` bytes; a single leftover character is dropped.

#### `void runLengthDecode(std::string_view in, std::string& out, size_t maxOut)`

While input remains and `out.size() < maxOut`: a length byte 128 ends the data; a length `< 128` copies the next `length + 1` bytes (fewer if the input ends); a length `> 128` repeats the next byte `257 - length` times (nothing when no byte follows). A run is never cut, so the output can exceed `maxOut` by up to 127 bytes.

#### `void unpredict(std::string& data, const FilterParams& p)`

Applied after Flate and LZW only.
1. `predictor <= 1` → nothing.
2. `colors = clamp(p.colors, 1, 32)`, `bpc = clamp(p.bpc, 1, 16)`, `columns = clamp(p.columns, 1, 1 << 24)`; `bpp = max(1, (colors * bpc + 7) / 8)`; `rowBytes = (colors * bpc * columns + 7) / 8`.
3. `predictor == 2` (TIFF): only for `bpc` 8 or 16, otherwise the data stay as they are. For every *complete* row (`row + rowBytes <= size`; a partial last row is left alone): with 8 bits, `r[x] += r[x - colors]` for `x` from `colors` to `rowBytes - 1`; with 16 bits, big-endian 16-bit sums with a step of `colors * 2` bytes (`x` from that step while `x + 1 < rowBytes`). Return.
4. Any other predictor (the PNG predictors 10–15, but also 3–9 and anything larger) is treated as PNG: every row is one filter-type byte plus `rowBytes` bytes. A row longer than the whole stream comes from damaged parameters: `rowLen = min(rowBytes, data.size())` is the length of the two row buffers (`prev`, `row`, zeros at first) and of every output row. Rows are still taken at `pos = 0, rowBytes + 1, ...` while `pos < size`; each takes `n = min(rowLen, size − pos − 1)` bytes after its type byte, and a short row is padded with zeros to `rowLen`. Type 1 Sub, 2 Up, 3 Average (`(a + b) / 2`), 4 Paeth (`pa = |b − c|`, `pb = |a − c|`, `pc = |a + b − 2c|`; `a` if `pa <= pb && pa <= pc`, else `b` if `pb <= pc`, else `c`), with `a` = the byte `bpp` to the left, `b` = the byte above, `c` = above-left, 0 outside the row; type 0 and unknown types copy the bytes. The first row's "above" is zeros. The output, `rowLen` bytes per row (the type bytes removed), replaces `data`. With sane parameters `rowLen == rowBytes` and the output is a whole number of rows; with a row longer than the data there is one row of `data.size()` bytes, so the output is never larger than the input in that case.

### A.7 Opening a file

`File::open(data, err)`: `data_ = data`, `tail_ = {}`, `tailOffset_ = 0`, `fileSize_ = data.size()`, `partial_ = false`, then `finishOpen(err)`.

`File::openPartial(head, tail, fileSize, err)`: when `head.size() >= fileSize` it is `open(head, err)`. Otherwise `data_ = head`, `tail_ = tail`, `fileSize_ = fileSize`, `tailOffset_ = fileSize - tail.size()`, `partial_ = true`, then `finishOpen(err)`.

`File::view(offset)` (every read of an object goes through it): `data_[offset:]` when `offset < data_.size()`; in partial mode, `tail_[offset - tailOffset_:]` when the offset lies inside the tail; otherwise empty. The view ends at the end of the range that holds the offset, so an object that straddles the end of the head is cut there.

**`finishOpen(err)`**, in order (error strings are written to `*err` only when `err` is non-null):
0. Nothing of an earlier file survives, so one `File` can open several files in turn: `headerShift_ = 0`; `repaired_ = encrypted_ = readingXref_ = false`; `version_` cleared; `trailer_ = Object{}`; `xref_`, `cache_`, `objStreams_` and `loading_` cleared; `crypt_` reset. (`data_`, `tail_`, `tailOffset_`, `fileSize_` and `partial_` were just set by `open`/`openPartial`.)
1. `head = data_[0 : min(size, 1024)]`; `h = head.find("%PDF-")`; not found → `"This is not a PDF file."`, false.
2. `headerShift_ = h` (bytes before the header; some writers count offsets from it).
3. `version_`: for `k` from `h + 5` while `k < head.size()` and `k < h + 9`: stop at the first byte that is neither a digit nor `.`, else append it (at most 4 bytes, `"1.7"`).
4. The last `startxref`: `end = partial_ ? tail_ : data_`; `sx = end.rfind("startxref")`; it is used only when found within the last 4096 bytes of `end` (`sx >= end.size() - 4096`, or anywhere when `end` is shorter). A lexer at `sx + 9` reads one token; when it is an `Int > 0`, `ok = readXrefChain(that offset)`.
5. Partial mode: `!ok` → `"The cross-reference table is outside the part that was read."`, false. (The catalog is not checked in partial mode.)
6. Full mode, when `!ok || !rootUsable()`: `rebuildXref()` (A.10). If the root is still unusable, look for any object `k` in `1 .. objectCount() - 1` whose `get(k)` is a dictionary with direct `/Type /Page`; if there is none → `"The PDF file is damaged: its document catalog was not found."`, false. (A truncated download may have lost a catalog written at the end; its pages are still found in file order, C.10.)
7. If the trailer has an `Encrypt` key (direct presence): `encrypted_ = true`; `setupDecryption(err)` (A.11); return false when it fails.
8. Return true.

`rootUsable()`: `resolve(trailer_["Root"])` is a dictionary that has a `Pages` key.

### A.8 Cross-reference sections

`setEntry(num, e)`: ignores `num <= 0 || num > kMaxObjectNumber`; grows `xref_` to `num + 1`; writes the entry **only if the slot is still type 0** — the newest section is read first, so the first writer wins.

`mergeTrailer(t)` (only for dictionaries): creates `trailer_` as an empty dictionary the first time, then appends every key of `t` that `trailer_` does not have yet, except `Prev`, `XRefStm`, `W`, `Index`, `Filter`, `DecodeParms`, `Length` and `Type`. Newer sections are merged first, so their values win.

**`readXrefChain(offset)`**:
```
todo = [offset]; seen = {}; any = false
while todo is not empty and seen.size() < 200:
  off = todo.front(); remove it
  if off was seen: continue; add it to seen
  prevs = []
  if readXrefAt(off, prevs) || (headerShift_ > 0 && readXrefAt(off + headerShift_, prevs)):
    any = true; append prevs to todo
  else if !any: return false          // the startxref section itself is unreadable
return any                              // later broken /Prev sections are ignored
```

**`readXrefAt(offset, prevs)`**: `v = view(offset)`; empty → false. A lexer over `v` skips white space; if the next 4 bytes are `xref` they are skipped and `readXrefTable(lx, prevs)` decides; otherwise `readXrefStream(lx, offset, prevs)` decides.

**`readXrefTable(lx, prevs)`**:
```
entries = []                                   // applied only when the table was read
loop:
  save = position
  if !token(a): return false                   // the data end inside the table
  if a is the keyword "trailer": break
  if a is not an Int, or !token(b), or b is not an Int: rewind to save; break
  start = a.i; count = min(b.i, kMaxObjectNumber)
  for k in 0 .. count - 1:
    entryPos = position
    if !token(off) || !token(gen) || !token(kind): return false
    if off or gen is not an Int, or kind is not a keyword: rewind to entryPos; break   // shorter than announced
    if k == 0 && start == 1 && kind.s == "f" && gen.i == 65535: start = 0   // writer bug: the free head of object 0
    if kind.s == "n" && off.i > 0 && start + k > 0: entries += (start + k, {type 1, gen.i, offset off.i})
setEntry for every entry, in table order
skipSpace; if the next 7 bytes are "trailer", skip them
if !object(t, refs = true) || !t.isDict(): return !entries.empty()
if t has XRefStm (direct Int > 0): readXrefAt(XRefStm, ignored)    // hybrid files; its Prev is not followed
mergeTrailer(t)
if t has Prev (direct number, integer() > 0): prevs += Prev
return true
```
`f` entries are skipped, not recorded as free, so an older section can still define such an object. Entry keywords other than `n` and `f` are skipped as well.

**`readXrefStream(lx, base, prevs)`**:
1. Tokens `n` (Int), `g` (Int), keyword `obj`; then `object(dict, refs = true)` must be a dictionary; then the keyword `stream`. Any failure → false.
2. Data start: after the keyword, skip one CR, then one LF. `dict` becomes a `Stream` with `streamOffset = base + that position`, `objNum = n.i` (`objGen` stays 0).
3. `decodeStream(dict, data)` with `encrypted_` set to false (cross-reference streams are never encrypted) and `readingXref_` set to true for the call, both restored after; failure → false. A cross-reference stream's `/Length` must be direct: an indirect one cannot be looked up before the table exists, so while `readingXref_` is set `rawStream` does not resolve it and the data end at `endstream` (A.11). Reading such a file needs no repair.
4. `W` (direct) must have at least 3 elements; `ws[k] = clamp(W[k].integer(), 0, 8)`; `rec = ws[0] + ws[1] + ws[2]`; 0 → false.
5. `Index` (direct array): every element's `integer()`; without it `{0, Size.integer()}` (direct `Size`). An odd last element is ignored.
6. One cursor `p` runs through `data` for all subsections. `field(k, def)` is `def` when `ws[k] == 0`, else the next `ws[k]` bytes big-endian.
   ```
   for each pair (start, count) of Index, count = min(count, kMaxObjectNumber):
     for k in 0 .. count - 1 while p + rec <= data.size():
       type = field(0, 1); f1 = field(1, 0); f2 = field(2, 0)
       type 1 and f1 > 0 → setEntry(start + k, {type 1, gen f2, offset f1})
       type 2           → setEntry(start + k, {type 2, offset = object stream number f1, index f2})
       anything else (type 0, type 1 at offset 0, types 3+) → nothing
   ```
7. `mergeTrailer(dict)`; `Prev` (direct number > 0) → `prevs`; return true.

### A.9 Loading objects and the cache

**`get(num)`**:
```
if num <= 0: return nullObject()
if cache_ has num: return it
if num is in loading_ (a reference cycle) or loading_.size() > 32: return nullObject()
loading_.push(num)
ok = false
for attempt in 0, 1 while !ok:
  if num < xref_.size():
    e = xref_[num]
    type 1: ok = loadAt(e.offset, num, o) || (headerShift_ > 0 && loadAt(e.offset + headerShift_, num, o))
    type 2 and e.offset != num: ok = loadFromObjStream(e.offset, e.index, num, o)
  if !ok && attempt == 0:
    if repaired_ || partial_: break
    rebuildXref()                      // the table was wrong: scan once, then try again
loading_.pop()
if !ok: return nullObject()            // failed loads are not cached: a later repair may find the object
return cache_.emplace(num, o)
```
Cache rules: failed loads are never cached; successful loads are never evicted (the only resets are the start of `finishOpen` and `setupDecryption`, A.11), and `rebuildXref` does not clear the cache — objects in it were verified at their offset and callers may hold references to them. References returned by `get` stay valid because `std::unordered_map` does not move its elements. The repair runs at most once per file (`repaired_`), never in partial mode.

**`loadAt(offset, num, out)`**:
1. `v = view(offset)`; empty → false.
2. Tokens: an `Int` equal to `num`, an `Int` (the generation, not compared with the table), the keyword `obj`; otherwise false.
3. `object(out, refs = true)`; if it fails (nothing after `obj`) → `out` = null, return **true** (an empty object is a successful load).
4. A keyword `endobj` in place of the object → null.
5. A dictionary followed by the keyword `stream` becomes a `Stream`: after the keyword skip one CR and then one LF; `streamOffset = offset + that position`. Otherwise the lexer is rewound.
6. `out.objNum = num`, `out.objGen = gen`; when `encrypted_ && crypt_`, `decryptObject(out, num, gen)` (A.11). Return true.

**`loadFromObjStream(streamNum, index, num, out)`**:
- `objStreams_` caches one `ObjStream` per stream number, **including failures**: on first use, `s = get(streamNum)`; if it is a stream and `decodeStream(s, data)` succeeds, `n = clamp(direct N.integer(), 0, kMaxObjectNumber)`, `first = direct First.integer()`, and up to `n` pairs of integer tokens `(objnum, offset)` are read from the start of the data (stopping at the first pair that is not two `Int`s); each offset is stored as `max(0, first + offset)`. Whatever was read (possibly nothing) is cached and never retried (until `setupDecryption` clears the map).
- The object's offset: the pair at `index` when its number is `num`; otherwise the first pair with number `num`; none, or an offset at or past the end of the data → false.
- `object(out, refs = true)` at that offset; failure → null; a keyword → null. `out.objNum = num` (generation 0). No decryption: the object stream was decrypted as a whole. Return true.

`resolve(o)`: `o` itself unless it is a `Ref`; otherwise `get(o.i)`, followed through at most 16 further references; a result that is still a reference becomes a null object. It returns a copy (the shared `a`/`d` pointers make copies cheap).

`get(dict, key)`: the resolved entry, or a null object when the key is missing.

### A.10 Repair: `rebuildXref()`

1. `repaired_ = true`.
2. **Scan for `n g obj`** in `data_` (the head only in partial mode, which never calls this): for every occurrence `p` of `obj` (searching again from `p + 3`):
   - the byte after it must be white space or a delimiter, or the data must end there (`object`, `objx` are skipped);
   - going backwards: skip white space; take up to 6 digits as the generation (none → skip); require at least one white-space byte; skip the white space; take up to 8 digits as the object number (none → skip); the byte before the number must be white space or a delimiter, or the number must start the data;
   - `num = atoi(number)`, `gen = atoi(generation)`; skip `num <= 0 || num > kMaxObjectNumber`;
   - `fresh[num] = {type 1, gen, offset = start of the number}`; a later occurrence overwrites an earlier one (incremental updates win). `endobj` never qualifies because no digits precede its `obj`.
3. Entries of type 2 in the old table are kept where the scan found nothing (the scan cannot see inside object streams). `xref_ = fresh`; `headerShift_ = 0` (offsets are now absolute).
4. **Object streams**: for every type-1 entry `k` (from 1 to the table size taken before this step): if `/ObjStm` occurs within the first 300 bytes at its offset, `s = get(k)`; if it is a stream with direct `/Type /ObjStm` and decodes, read up to `clamp(N, 0, kMaxObjectNumber)` pairs of tokens (stop at the first pair whose first token is not an `Int` in `1 .. kMaxObjectNumber`; the second token is not checked) and register each object `a` as `{type 2, offset k, index j}` where its slot is still type 0.
5. **Trailer**: a dictionary `merged` takes only `Root`, `Info`, `Encrypt` and `ID`, later values replacing earlier ones: first from every `trailer` keyword in the data (a lexer at `p + 7` reads one object), in file order; then from every type-1 object whose first 300 bytes contain `/XRef` and that is a stream with direct `/Type /XRef`, in object-number order.
6. The old trailer is kept aside and `trailer_ = merged`. If the root is not usable, the first object `k >= 1` (in number order, type ≠ 0) whose `get(k)` is a dictionary with direct `/Type /Catalog` and a `Pages` key becomes `Root` (a `Ref` to `k`, generation 0; replacing an existing `Root` entry or appended).
7. If `trailer_` still has no `Root` and the old trailer was a dictionary, the old trailer is restored as a whole.

### A.11 Streams and decryption

**`rawStream(s, out)`**:
1. `out` cleared; not a stream → false; `v = view(s.streamOffset)`; empty → false.
2. `len` = the `/Length` value: for a reference, `resolve(...).integer(-1)` — but not while `readingXref_` is set (A.8), when `len` stays −1; otherwise `integer(-1)`; −1 when missing.
3. The length is trusted when `0 <= len <= v.size()` and, after skipping at most 8 PDF white-space bytes from `len`, the data continue with `endstream` or `endobj` or end there. Otherwise the data run up to the first `endstream` (or the end of the view), minus one LF and then one CR directly before it.
4. When `encrypted_ && crypt_`:
   - `plain` = direct `/Type /XRef`, or (`!encryptMetadata()` and direct `/Type /Metadata`);
   - a stream stored unencrypted in an encrypted file is marked by a first filter `/Crypt` with the Identity crypt filter: `filter = resolve(s["Filter"])`, `first` = `resolve(filter.at(0))` for an array, else `filter`; when `first` is the name `Crypt`: `parms = resolve(s["DecodeParms"])`, `p` = `resolve(parms.at(0))` for an array, else `parms`; `name` = `resolve(p["Name"])` when `p` is a dictionary, else null; a `name` that is not a name, or is `Identity`, sets `plain = true` (without a `/Name` the crypt filter is Identity by default). Only the key names `Filter` and `DecodeParms` are looked at here, and a `/Crypt` naming any other crypt filter is decrypted with the stream method like every other stream;
   - `crypt_->handler.decryptStream(out, s.objNum, s.objGen, plain)`.
5. True.

**`decodeStream(s, out, imageFilter, maxOut)`**:
1. `out` and `*imageFilter` cleared; `rawStream` into `a`, false if it fails.
2. `filter = get(s, "Filter")`, or `get(s, "F")` when that is null; `parms = get(s, "DecodeParms")`, or `get(s, "DP")` when null (the inline-image abbreviations are accepted on every stream).
3. The chain: a name → one filter with `filterParams(parms is an array ? resolve(parms.at(0)) : parms)`; an array → each element resolved, non-names skipped, filter `k` takes `parms.at(k)` (by its index in the filter array) or the single dictionary.
4. For each filter in order: an image codec filter (`isImageCodecFilter`) → without `imageFilter` return false; with it, `*imageFilter` = its canonical name, `out` = the data decoded so far (still in that codec), return true — later filters are dropped. Otherwise `applyFilter(name, params, a, b, maxOut)`; false → return false; `a = b`.
5. `out = a`; true. A stream without filters returns its raw (decrypted) bytes.

`decryptString(s, num, gen)`: when `encrypted_ && crypt_`, `crypt_->handler.decryptString(s, num, gen)`.

`decryptObject(o, num, gen)`: strings are decrypted; arrays, dictionaries and stream dictionaries recursively, every element and value; other types are left alone. Objects from object streams are never passed through it.

**`setupDecryption(err)`**:
1. `enc = resolve(trailer_["Encrypt"])` (loaded before `crypt_` exists, so it is not decrypted — the encryption dictionary never is).
2. `id0` = the bytes of `resolve(ids.at(0))` where `ids = resolve(trailer_["ID"])` is an array; otherwise empty.
3. `CryptHandler::init(enc, id0, resolve-callback, &why)`; on failure `*err = why` and return false (`encrypted_` stays true, `crypt_` null).
4. `crypt_` is set. Every cached object except the one the trailer's `Encrypt` reference names (when it is a reference) is erased — they were loaded with encrypted strings — and `objStreams_` is cleared. True.

### A.12 The image container ("LLPDFIM1")

A picture whose samples still need PDF filters or colour conversion is stored in `ImageData::bytes` as this container (all integers unsigned 32-bit little-endian):

| offset | size | content |
|---|---|---|
| 0 | 8 | magic `LLPDFIM1`: `constexpr char kImageMagic[8] = {'L', 'L', 'P', 'D', 'F', 'I', 'M', '1'};` (no terminator) |
| 8 | 4 | width |
| 12 | 4 | height |
| 16 | 1 | bpc (low 8 bits of `ImageSpec::bpc`) |
| 17 | 1 | comps |
| 18 | 1 | space: 0 Gray, 1 Rgb, 2 Cmyk, 3 Indexed (`ImageSpec::Space`) |
| 19 | 1 | flags: 1 invert, 2 stencil, 4 jpeg |
| 20 | 4 | number of filters F |
| … | F × | 4 name length L, L name bytes, then 5 × 4: predictor, colors, bpc, columns, earlyChange (each `int` stored as `uint32_t`) |
| … | 4 + P | palette length P, then the palette (RGB triplets) |
| … | 4 + D | data length D, then the encoded samples |
| … | 4 + M | mask length M, then the mask (another container, or nothing) |

**`encodeImageContainer(spec)`** writes exactly that, in that order.

**`isImageContainer(data, size)`**: `data` non-null, `size >= 16`, and the first 8 bytes are the magic.

**`imageContainerSize(data, size, w, h)`**: false when not a container; otherwise `w`, `h` = the two `uint32_t` at 8 and 12 cast to `int`; returns `w > 0 && h > 0` (no other limit).

File-local helpers: `struct Reader { const unsigned char* p; size_t n, k = 0; bool ok = true; }` with `u32()`, `u8()` and `bytes(len)`; each returns 0 / empty and sets `ok = false` when fewer bytes than needed remain, and does not advance then. `unsigned sampleAt(const unsigned char* row, size_t i, int bpc)` returns sample `i` of a row: bpc 8 → the byte; 16 → the high byte `row[2i]`; 1, 2, 4 → MSB-first bit fields; any other depth → 0.

**`decodeImageContainer(data, size, rgba, w, h)`** runs while a page is drawn, so a picture that does not fit in memory must not end the app: it returns `decodeContainer(data, size, rgba, w, h)` inside `try`; on a `std::exception` it clears `rgba`, sets `w = h = 0` and returns false.

**`bool decodeContainer(const unsigned char* data, size_t size, std::vector<unsigned char>& rgba, int& width, int& height)`** (file-local, the third unnamed namespace):
1. `w = h = 0`; not a container → false. A `Reader` at offset 8 reads width, height, bpc, comps, space and flags.
2. False when the reader failed, `width <= 0`, `height <= 0`, either above 20 000, or `width * height > kMaxImagePixels` (50 000 000, `PdfReader.h`; 64-bit product).
3. The filter count is read and limited to 16; for each filter its name and the five parameters. Then palette, samples and mask. Any short read → false.
4. The filters are applied in order to the samples with `applyFilter(..., kMaxStreamBytes)`; one that fails → false.
5. `rgba` = `width × height × 4` bytes of 255.
6. **JPEG** (flag 4): `stbi_load_from_memory` on the data after step 4 (length `min(size, 0x7FFFFFFF)`, 4 channels requested); null → false. If `jw × jh` differs from the container's size, the JPEG is returned with its own size (`rgba` replaced, `w = jw`, `h = jh`) and **no mask is applied**; return true. Otherwise its pixels are copied into `rgba`. Neither the invert flag nor the colour space affects a JPEG.
7. **Samples**: `nc` = 1 for Indexed or stencil images, else `clamp(comps, 1, 4)`; `rowBytes = (width × nc × bpc + 7) / 8` (0 → false); short data are padded with zero bytes to `rowBytes × height`. `maxv = bpc >= 16 ? 255 : (1 << bpc) − 1`; `scale(v)`: with invert `v = maxv − min(v, maxv)`; then `bpc >= 8 ? v : v × 255 / maxv`. Per pixel, with `base = x × nc` (sample index in the row):
   - stencil: `v = sampleAt(base)`, flipped (`^ 1`) when inverted; RGB 0, alpha `v ? 0 : 255` (0 paints black, 1 leaves the background);
   - Indexed: `idx = sampleAt(base)`; RGB from `palette[3 idx .. 3 idx + 2]` when `3 idx + 2 < palette size`, else black; alpha 255; invert is not applied;
   - `nc == 1` or `nc == 2`: gray `scale(first sample)` in R, G and B (two components never come from `makeImage`; the second is ignored);
   - `nc == 3`: R, G, B = `scale` of the three samples;
   - otherwise (`nc == 4`): `c, m, y, k` = `scale` of samples `base .. base + 3`; R = `(255 − c)(255 − k) / 255`, G = `(255 − m)(255 − k) / 255`, B = `(255 − y)(255 − k) / 255` (integer arithmetic).
   - Bit depths other than 1, 2, 4, 8, 16 give 0 samples (the encoder rejects them).
8. **Mask**: when the mask bytes are non-empty and decode with `decodeContainer` (recursively, the same limits) to `mw × mh > 0`, every pixel's alpha becomes the mask's red channel at `(x × mw / w, y × mh / h)` (nearest sample, 64-bit products). A mask that does not decode is ignored.
9. `w`, `h` = the container's size; true.

---

## Part B — `src/core/PdfCrypt.cpp`

### B.1 Includes and layout

Includes: `core/PdfCrypt.h`, `<algorithm>`, `<array>`, `<cstdint>`, `<cstring>`.

Definition order: an unnamed namespace with `rotl32`, `rotr32`, `rotr64`, `padMessage`, `struct AesTables` and `aesTables()`, `xtime`, `gmul`, `class Aes`, `kPad` and `hashR6`; then `md5`, `sha256`; a second unnamed namespace with `sha512Core`; then `sha512`, `sha384`, `rc4`, `aesCbcDecrypt`, `aesCbcEncrypt` and the `CryptHandler` members.

### B.2 Hashes and ciphers

All primitives are the standard algorithms, written out in full in the file (no library); their results must be bit-identical to the standards. The unit test vectors of Part E pin them.

- `std::string padMessage(std::string_view data, size_t block, size_t lenBytes, bool bigEndian)`: the Merkle–Damgård padding shared by the hashes: append `0x80`, then zero bytes until `size % block == block - lenBytes`, then the message length in **bits** in `lenBytes` bytes (big- or little-endian; bytes beyond the 64-bit value are 0). MD5 and SHA-256 use `(64, 8)`, SHA-384/512 `(128, 16)`.
- `inline uint32_t rotl32(uint32_t x, int n)`, `rotr32`, `inline uint64_t rotr64(uint64_t x, int n)`: rotations.
- **`md5(data)`**: RFC 1321 (the standard K table and shift amounts, little-endian words), 16-byte digest.
- **`sha256(data)`**: FIPS 180-4, 32-byte digest.
- `std::string sha512Core(std::string_view data, const uint64_t iv[8], size_t outBytes)` (file-local): the SHA-512 compression of FIPS 180-4 with the given initial value; the 64-byte result is cut to `outBytes`. **`sha512`** uses the SHA-512 initial value and 64 bytes, **`sha384`** the SHA-384 initial value and 48 bytes.
- **`rc4(key, data)`**: the standard key schedule and keystream; with an empty key the key schedule is skipped (the identity permutation is used). The output has the length of `data`.
- **AES** (FIPS 197): `struct AesTables { uint8_t sbox[256], inv[256]; }` is computed once, on first use, in the function-local `static const AesTables t` of `aesTables()`: the S-box is generated rather than stored, by the usual walk over the multiplicative group:
  ```cpp
  uint8_t p = 1, q = 1;
  do {
    p = static_cast<uint8_t>(p ^ static_cast<uint8_t>(p << 1) ^ ((p & 0x80) ? 0x1B : 0));  // p * 3
    q = static_cast<uint8_t>(q ^ (q << 1));                                                // q / 3
    q = static_cast<uint8_t>(q ^ (q << 2));
    q = static_cast<uint8_t>(q ^ (q << 4));
    if (q & 0x80) q ^= 0x09;
    auto rot = [](uint8_t x, int n) { return static_cast<uint8_t>((x << n) | (x >> (8 - n))); };
    const uint8_t x = static_cast<uint8_t>(q ^ rot(q, 1) ^ rot(q, 2) ^ rot(q, 3) ^ rot(q, 4));
    sbox[p] = static_cast<uint8_t>(x ^ 0x63);
  } while (p != 1);
  sbox[0] = 0x63;
  for (int k = 0; k < 256; ++k) inv[sbox[k]] = static_cast<uint8_t>(k);
  ```
  `xtime(x)` multiplies by 2 in GF(2⁸) (`(x << 1) ^ (x & 0x80 ? 0x1B : 0)`), `gmul(a, b)` by any byte (shift-and-add). `class Aes` holds the expanded key `uint8_t w_[240]` and `rounds_`: the constructor takes `nk = key.size() / 4` words (16-byte keys → 10 rounds, 32-byte keys → 14; other lengths are not rejected: `rounds_ = nk + 6`) and runs the FIPS 197 key expansion (`RotWord`+`SubWord`+`Rcon` every `nk` words, the extra `SubWord` at `i % nk == 4` for `nk > 6`). `encrypt(s)` and `decrypt(s)` process one 16-byte block in place (column-major state: byte `4c + r` is row `r` of column `c`); `MixColumns` uses the `xtime` form, `InvMixColumns` multiplies by 14, 11, 13 and 9 with `gmul`.
- **`aesCbcDecrypt(key, iv, data)`** / **`aesCbcEncrypt(key, iv, data)`**: CBC over the whole 16-byte blocks of `data` only — a trailing partial block is ignored, no padding is added or removed. The first 16 bytes of `iv` are used (the caller always passes 16).

### B.3 Constants and Algorithm 2.B

The padding string of the standard security handler (ISO 32000-1, 7.6.3.3), verbatim:

```cpp
const unsigned char kPad[32] = {0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00, 0x4E,
                                0x56, 0xFF, 0xFA, 0x01, 0x08, 0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68,
                                0x3E, 0x80, 0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A};
```

`std::string hashR6(std::string_view password, std::string_view salt, std::string_view udata)` — ISO 32000-2 Algorithm 2.B (revision 6), only ever called with an empty password and empty `udata`:
```
k = sha256(password + salt + udata)
for round = 0, 1, 2, ...:
  unit = password + k + udata
  k1 = unit repeated 64 times
  e = aesCbcEncrypt(key = k[0:16], iv = k[16:32], k1)
  sum = the sum of the first 16 bytes of e (as unsigned)        // equals the 128-bit number mod 3
  k = sum % 3 == 0 ? sha256(e) : sum % 3 == 1 ? sha384(e) : sha512(e)
  if round >= 63 && e.back() <= round + 1 - 32: break           // at least 64 rounds, then the last-byte test
  if round > 1000: break                                         // safety limit
return k[0:32]
```

### B.4 `CryptHandler::init(encrypt, id0, resolve, err)`

Every value is passed through the `resolve` callback before use. Messages are written to `*err` only when `err` is non-null.

1. `encrypt` not a dictionary → `"The PDF file is encrypted, but its encryption dictionary is damaged."`, false.
2. `/Filter` not the name `Standard` → `"The PDF file is protected by a security handler that Lanternleaf does not support."`, false.
3. `v = V.integer(0)`, `r = R.integer(2)`, `o = O` bytes, `u = U` bytes (the `s` of whatever object it is), `p = (int32_t) P.integer(0)`; `encryptMetadata_` = `/EncryptMetadata` when it is a `Bool` (default true).
4. The methods:
   - `v` 1 or 2 → strings and streams `Rc4`;
   - `v` 4 or 5 → `streams_ = methodOf(StmF)`, `strings_ = methodOf(StrF)`, where a missing or non-name value counts as `Identity`;
   - any other `v` → `"The PDF file uses an encryption method that Lanternleaf does not support."`, false.

   `methodOf(name)`: `Identity` → `None`; otherwise `CFM` of `CF[name]` (each resolved): `V2` → `Rc4`, `AESV2` → `Aes128`, `AESV3` → `Aes256`, `None` → `None`; anything else (a missing crypt filter included) → `Aes256` when `v >= 5`, else `Rc4`.
5. **`r <= 4`** (every revision up to 4, also the invalid 0 and 1) — Algorithm 2 with the empty user password, then Algorithm 6:
   ```
   n = (r == 2) ? 5 : Length.integer(40) / 8
   if v == 4: n = 16
   n = clamp(n, 5, 16)
   in = kPad (32 bytes) + o[0:32] + p as 4 bytes little-endian + id0
   if r >= 4 && !encryptMetadata_: in += FF FF FF FF
   h = md5(in)
   if r >= 3: 50 times h = md5(h[0:n])
   key_ = h[0:n]
   if r == 2: ok = rc4(key_, kPad) == u[0:32]
   else:      x = rc4(key_, md5(kPad + id0)); for k in 1..19: x = rc4(key_ with every byte XOR k, x)
              ok = u.size() >= 16 && x[0:16] == u[0:16]
   ```
   `!ok` → `"The PDF file is protected with a password."`, false; else true. The owner password is never tried.
6. **`r == 5` or `r == 6`**:
   - `u.size() < 48` → the "damaged" message of step 1, false.
   - `validationSalt = u[32:40]`, `keySalt = u[40:48]`, `ue` = `/UE` bytes.
   - `check = (r == 5) ? sha256(validationSalt) : hashR6("", validationSalt, "")`; `check != u[0:32]` → `"The PDF file is protected with a password."`, false.
   - `ik = (r == 5) ? sha256(keySalt) : hashR6("", keySalt, "")`; `ue.size() < 32` → the "damaged" message, false.
   - `key_ = aesCbcDecrypt(ik, 16 zero bytes, ue[0:32])` (32 bytes); true. `/Perms` is not checked.
7. Any other `r` → the "encryption method" message of step 4, false.

### B.5 Decrypting

`decrypt(s, num, gen, m)` (private):
1. `m == None` or `s` empty → unchanged.
2. The key: for `Aes256`, `key_` itself. Otherwise `md5(key_ + num as 3 bytes little-endian + gen as 2 bytes little-endian + ("sAlT" for Aes128))`, cut to `min(key_.size() + 5, 16)` bytes (Algorithm 1).
3. `Rc4` → `s = rc4(key, s)`.
4. AES (both): fewer than 32 bytes (an IV and at least one block) → `s` is cleared. Otherwise `body = (size − 16) / 16 × 16`; `out = aesCbcDecrypt(key, s[0:16], s[16:16 + body])` (a partial last block is ignored); if the last byte `pad` of `out` is 1–16 and `pad <= out.size()`, `pad` bytes are removed (the pad bytes themselves are not checked); `s = out`.

`decryptString(s, num, gen)` → `decrypt(..., strings_)`. `decryptStream(s, num, gen, unencryptedKind)` → nothing when `unencryptedKind`, else `decrypt(..., streams_)`. `encryptMetadata()` is the inline getter of the header.

---

## Part C — `src/core/PdfContent.cpp`

### C.1 Includes and layout

Includes: `core/PdfContent.h`, `<algorithm>`, `<array>`, `<cctype>`, `<cmath>`, `<cstring>`, `<unordered_map>`, `<unordered_set>`, `core/Unicode.h`.

Definition order: an unnamed namespace with the encoding tables (C.2), the glyph names (C.3), the standard-14 widths (C.4), the matrix helpers (C.5), CMaps (C.6), the TrueType `cmap` reader (C.7), the Type 1 encoding reader (C.8), `struct Font`, `baseFontName` and `styleFromName` (C.9); then the public `glyphNameToUtf8`; `struct ContentReader::Impl` and its members (C.10); a second unnamed namespace with `class Interpreter` and `numArg` (C.11); the `ContentReader` constructor, destructor, `pageCount`, `pageIndexOf`, `pageBox`; a third unnamed namespace with `pageMatrix`; `userToPage`, `readPage` and `fonts` (C.12).

### C.2 Encoding tables

`using EncodingTable = std::array<char32_t, 256>;` — code → Unicode, 0 meaning "no character". `struct CodePair { uint8_t code; char32_t cp; };`. Each table is built once in a function-local static. Verbatim:

```cpp
struct CodePair {
  uint8_t code;
  char32_t cp;
};

using EncodingTable = std::array<char32_t, 256>;

EncodingTable makeAscii() {
  EncodingTable t{};
  for (int c = 0x20; c < 0x7F; ++c) t[static_cast<size_t>(c)] = static_cast<char32_t>(c);
  return t;
}

const EncodingTable& standardEncoding() {
  static const EncodingTable t = [] {
    EncodingTable e = makeAscii();
    e[0x27] = 0x2019;
    e[0x60] = 0x2018;
    static const CodePair kHigh[] = {
        {0xA1, 0x00A1}, {0xA2, 0x00A2}, {0xA3, 0x00A3}, {0xA4, 0x2044}, {0xA5, 0x00A5}, {0xA6, 0x0192}, {0xA7, 0x00A7},
        {0xA8, 0x00A4}, {0xA9, 0x0027}, {0xAA, 0x201C}, {0xAB, 0x00AB}, {0xAC, 0x2039}, {0xAD, 0x203A}, {0xAE, 0xFB01},
        {0xAF, 0xFB02}, {0xB1, 0x2013}, {0xB2, 0x2020}, {0xB3, 0x2021}, {0xB4, 0x00B7}, {0xB6, 0x00B6}, {0xB7, 0x2022},
        {0xB8, 0x201A}, {0xB9, 0x201E}, {0xBA, 0x201D}, {0xBB, 0x00BB}, {0xBC, 0x2026}, {0xBD, 0x2030}, {0xBF, 0x00BF},
        {0xC1, 0x0060}, {0xC2, 0x00B4}, {0xC3, 0x02C6}, {0xC4, 0x02DC}, {0xC5, 0x00AF}, {0xC6, 0x02D8}, {0xC7, 0x02D9},
        {0xC8, 0x00A8}, {0xCA, 0x02DA}, {0xCB, 0x00B8}, {0xCD, 0x02DD}, {0xCE, 0x02DB}, {0xCF, 0x02C7}, {0xD0, 0x2014},
        {0xE1, 0x00C6}, {0xE3, 0x00AA}, {0xE8, 0x0141}, {0xE9, 0x00D8}, {0xEA, 0x0152}, {0xEB, 0x00BA}, {0xF1, 0x00E6},
        {0xF5, 0x0131}, {0xF8, 0x0142}, {0xF9, 0x00F8}, {0xFA, 0x0153}, {0xFB, 0x00DF}};
    for (const CodePair& p : kHigh) e[p.code] = p.cp;
    return e;
  }();
  return t;
}

const EncodingTable& winAnsiEncoding() {
  static const EncodingTable t = [] {
    EncodingTable e = makeAscii();
    for (int c = 0xA0; c < 0x100; ++c) e[static_cast<size_t>(c)] = static_cast<char32_t>(c);
    e[0xAD] = 0x002D;  // drawn hyphen
    static const CodePair k80[] = {{0x80, 0x20AC}, {0x82, 0x201A}, {0x83, 0x0192}, {0x84, 0x201E}, {0x85, 0x2026},
                                   {0x86, 0x2020}, {0x87, 0x2021}, {0x88, 0x02C6}, {0x89, 0x2030}, {0x8A, 0x0160},
                                   {0x8B, 0x2039}, {0x8C, 0x0152}, {0x8E, 0x017D}, {0x91, 0x2018}, {0x92, 0x2019},
                                   {0x93, 0x201C}, {0x94, 0x201D}, {0x95, 0x2022}, {0x96, 0x2013}, {0x97, 0x2014},
                                   {0x98, 0x02DC}, {0x99, 0x2122}, {0x9A, 0x0161}, {0x9B, 0x203A}, {0x9C, 0x0153},
                                   {0x9E, 0x017E}, {0x9F, 0x0178}};
    for (const CodePair& p : k80) e[p.code] = p.cp;
    return e;
  }();
  return t;
}

const EncodingTable& macRomanEncoding() {
  static const EncodingTable t = [] {
    EncodingTable e = makeAscii();
    static const char32_t kHigh[128] = {
        0x00C4, 0x00C5, 0x00C7, 0x00C9, 0x00D1, 0x00D6, 0x00DC, 0x00E1, 0x00E0, 0x00E2, 0x00E4, 0x00E3, 0x00E5,
        0x00E7, 0x00E9, 0x00E8, 0x00EA, 0x00EB, 0x00ED, 0x00EC, 0x00EE, 0x00EF, 0x00F1, 0x00F3, 0x00F2, 0x00F4,
        0x00F6, 0x00F5, 0x00FA, 0x00F9, 0x00FB, 0x00FC, 0x2020, 0x00B0, 0x00A2, 0x00A3, 0x00A7, 0x2022, 0x00B6,
        0x00DF, 0x00AE, 0x00A9, 0x2122, 0x00B4, 0x00A8, 0x2260, 0x00C6, 0x00D8, 0x221E, 0x00B1, 0x2264, 0x2265,
        0x00A5, 0x00B5, 0x2202, 0x2211, 0x220F, 0x03C0, 0x222B, 0x00AA, 0x00BA, 0x03A9, 0x00E6, 0x00F8, 0x00BF,
        0x00A1, 0x00AC, 0x221A, 0x0192, 0x2248, 0x2206, 0x00AB, 0x00BB, 0x2026, 0x00A0, 0x00C0, 0x00C3, 0x00D5,
        0x0152, 0x0153, 0x2013, 0x2014, 0x201C, 0x201D, 0x2018, 0x2019, 0x00F7, 0x25CA, 0x00FF, 0x0178, 0x2044,
        0x00A4, 0x2039, 0x203A, 0xFB01, 0xFB02, 0x2021, 0x00B7, 0x201A, 0x201E, 0x2030, 0x00C2, 0x00CA, 0x00C1,
        0x00CB, 0x00C8, 0x00CD, 0x00CE, 0x00CF, 0x00CC, 0x00D3, 0x00D4, 0xF8FF, 0x00D2, 0x00DA, 0x00DB, 0x00D9,
        0x0131, 0x02C6, 0x02DC, 0x00AF, 0x02D8, 0x02D9, 0x02DA, 0x00B8, 0x02DD, 0x02DB, 0x02C7};
    for (int c = 0; c < 128; ++c) e[static_cast<size_t>(0x80 + c)] = kHigh[c];
    return e;
  }();
  return t;
}

const EncodingTable& symbolEncoding() {
  static const EncodingTable t = [] {
    EncodingTable e = makeAscii();
    static const CodePair kSym[] = {
        {0x22, 0x2200}, {0x24, 0x2203}, {0x27, 0x220B}, {0x2A, 0x2217}, {0x2D, 0x2212}, {0x40, 0x2245}, {0x41, 0x0391},
        {0x42, 0x0392}, {0x43, 0x03A7}, {0x44, 0x0394}, {0x45, 0x0395}, {0x46, 0x03A6}, {0x47, 0x0393}, {0x48, 0x0397},
        {0x49, 0x0399}, {0x4A, 0x03D1}, {0x4B, 0x039A}, {0x4C, 0x039B}, {0x4D, 0x039C}, {0x4E, 0x039D}, {0x4F, 0x039F},
        {0x50, 0x03A0}, {0x51, 0x0398}, {0x52, 0x03A1}, {0x53, 0x03A3}, {0x54, 0x03A4}, {0x55, 0x03A5}, {0x56, 0x03C2},
        {0x57, 0x03A9}, {0x58, 0x039E}, {0x59, 0x03A8}, {0x5A, 0x0396}, {0x5C, 0x2234}, {0x5E, 0x22A5}, {0x60, 0},
        {0x61, 0x03B1}, {0x62, 0x03B2}, {0x63, 0x03C7}, {0x64, 0x03B4}, {0x65, 0x03B5}, {0x66, 0x03C6}, {0x67, 0x03B3},
        {0x68, 0x03B7}, {0x69, 0x03B9}, {0x6A, 0x03D5}, {0x6B, 0x03BA}, {0x6C, 0x03BB}, {0x6D, 0x03BC}, {0x6E, 0x03BD},
        {0x6F, 0x03BF}, {0x70, 0x03C0}, {0x71, 0x03B8}, {0x72, 0x03C1}, {0x73, 0x03C3}, {0x74, 0x03C4}, {0x75, 0x03C5},
        {0x76, 0x03D6}, {0x77, 0x03C9}, {0x78, 0x03BE}, {0x79, 0x03C8}, {0x7A, 0x03B6}, {0x7E, 0x223C}, {0xA0, 0x20AC},
        {0xA1, 0x03D2}, {0xA2, 0x2032}, {0xA3, 0x2264}, {0xA4, 0x2044}, {0xA5, 0x221E}, {0xA6, 0x0192}, {0xA7, 0x2663},
        {0xA8, 0x2666}, {0xA9, 0x2665}, {0xAA, 0x2660}, {0xAB, 0x2194}, {0xAC, 0x2190}, {0xAD, 0x2191}, {0xAE, 0x2192},
        {0xAF, 0x2193}, {0xB0, 0x00B0}, {0xB1, 0x00B1}, {0xB2, 0x2033}, {0xB3, 0x2265}, {0xB4, 0x00D7}, {0xB5, 0x221D},
        {0xB6, 0x2202}, {0xB7, 0x2022}, {0xB8, 0x00F7}, {0xB9, 0x2260}, {0xBA, 0x2261}, {0xBB, 0x2248}, {0xBC, 0x2026},
        {0xBF, 0x21B5}, {0xC0, 0x2135}, {0xC1, 0x2111}, {0xC2, 0x211C}, {0xC3, 0x2118}, {0xC4, 0x2297}, {0xC5, 0x2295},
        {0xC6, 0x2205}, {0xC7, 0x2229}, {0xC8, 0x222A}, {0xC9, 0x2283}, {0xCA, 0x2287}, {0xCB, 0x2284}, {0xCC, 0x2282},
        {0xCD, 0x2286}, {0xCE, 0x2208}, {0xCF, 0x2209}, {0xD0, 0x2220}, {0xD1, 0x2207}, {0xD2, 0x00AE}, {0xD3, 0x00A9},
        {0xD4, 0x2122}, {0xD5, 0x220F}, {0xD6, 0x221A}, {0xD7, 0x22C5}, {0xD8, 0x00AC}, {0xD9, 0x2227}, {0xDA, 0x2228},
        {0xDB, 0x21D4}, {0xDC, 0x21D0}, {0xDD, 0x21D1}, {0xDE, 0x21D2}, {0xDF, 0x21D3}, {0xE0, 0x25CA}, {0xE1, 0x2329},
        {0xE2, 0x00AE}, {0xE3, 0x00A9}, {0xE4, 0x2122}, {0xE5, 0x2211}, {0xF1, 0x232A}, {0xF2, 0x222B}};
    for (const CodePair& p : kSym) e[p.code] = p.cp;
    return e;
  }();
  return t;
}
```

Notes: StandardEncoding has `'` → U+2019 and `` ` `` → U+2018; WinAnsiEncoding maps 0xAD to U+002D (the hyphen is drawn), 0xA0–0xFF otherwise to Latin-1, and leaves 0x7F, 0x81, 0x8D, 0x8F, 0x90 and 0x9D at 0; in the Symbol table code 0x60 (radical extender) is 0 and every code not listed keeps the ASCII value of `makeAscii` (digits, punctuation).

### C.3 Glyph names

The glyph-name list (a subset of the Adobe Glyph List, 460 pairs, no duplicates) and its map, verbatim:

```cpp
struct NamePair {
  const char* name;
  char32_t cp;
};

const NamePair kGlyphNames[] = {
    {"space", 0x20}, {"exclam", 0x21}, {"quotedbl", 0x22}, {"numbersign", 0x23}, {"dollar", 0x24}, {"percent", 0x25},
    {"ampersand", 0x26}, {"quotesingle", 0x27}, {"parenleft", 0x28}, {"parenright", 0x29}, {"asterisk", 0x2A},
    {"plus", 0x2B}, {"comma", 0x2C}, {"hyphen", 0x2D}, {"period", 0x2E}, {"slash", 0x2F}, {"zero", 0x30},
    {"one", 0x31}, {"two", 0x32}, {"three", 0x33}, {"four", 0x34}, {"five", 0x35}, {"six", 0x36}, {"seven", 0x37},
    {"eight", 0x38}, {"nine", 0x39}, {"colon", 0x3A}, {"semicolon", 0x3B}, {"less", 0x3C}, {"equal", 0x3D},
    {"greater", 0x3E}, {"question", 0x3F}, {"at", 0x40}, {"bracketleft", 0x5B}, {"backslash", 0x5C},
    {"bracketright", 0x5D}, {"asciicircum", 0x5E}, {"underscore", 0x5F}, {"grave", 0x60}, {"braceleft", 0x7B},
    {"bar", 0x7C}, {"braceright", 0x7D}, {"asciitilde", 0x7E}, {"quoteleft", 0x2018}, {"quoteright", 0x2019},
    {"nbspace", 0xA0}, {"nonbreakingspace", 0xA0}, {"exclamdown", 0xA1}, {"cent", 0xA2}, {"sterling", 0xA3},
    {"currency", 0xA4}, {"yen", 0xA5}, {"brokenbar", 0xA6}, {"section", 0xA7}, {"dieresis", 0xA8},
    {"copyright", 0xA9}, {"ordfeminine", 0xAA}, {"guillemotleft", 0xAB}, {"guillemetleft", 0xAB},
    {"logicalnot", 0xAC}, {"sfthyphen", 0xAD}, {"softhyphen", 0xAD}, {"registered", 0xAE}, {"macron", 0xAF},
    {"overscore", 0xAF}, {"degree", 0xB0}, {"plusminus", 0xB1}, {"twosuperior", 0xB2}, {"threesuperior", 0xB3},
    {"acute", 0xB4}, {"mu", 0xB5}, {"paragraph", 0xB6}, {"periodcentered", 0xB7}, {"middot", 0xB7},
    {"cedilla", 0xB8}, {"onesuperior", 0xB9}, {"ordmasculine", 0xBA}, {"guillemotright", 0xBB},
    {"guillemetright", 0xBB}, {"onequarter", 0xBC}, {"onehalf", 0xBD}, {"threequarters", 0xBE},
    {"questiondown", 0xBF}, {"Agrave", 0xC0}, {"Aacute", 0xC1}, {"Acircumflex", 0xC2}, {"Atilde", 0xC3},
    {"Adieresis", 0xC4}, {"Aring", 0xC5}, {"AE", 0xC6}, {"Ccedilla", 0xC7}, {"Egrave", 0xC8}, {"Eacute", 0xC9},
    {"Ecircumflex", 0xCA}, {"Edieresis", 0xCB}, {"Igrave", 0xCC}, {"Iacute", 0xCD}, {"Icircumflex", 0xCE},
    {"Idieresis", 0xCF}, {"Eth", 0xD0}, {"Ntilde", 0xD1}, {"Ograve", 0xD2}, {"Oacute", 0xD3},
    {"Ocircumflex", 0xD4}, {"Otilde", 0xD5}, {"Odieresis", 0xD6}, {"multiply", 0xD7}, {"Oslash", 0xD8},
    {"Ugrave", 0xD9}, {"Uacute", 0xDA}, {"Ucircumflex", 0xDB}, {"Udieresis", 0xDC}, {"Yacute", 0xDD},
    {"Thorn", 0xDE}, {"germandbls", 0xDF}, {"agrave", 0xE0}, {"aacute", 0xE1}, {"acircumflex", 0xE2},
    {"atilde", 0xE3}, {"adieresis", 0xE4}, {"aring", 0xE5}, {"ae", 0xE6}, {"ccedilla", 0xE7}, {"egrave", 0xE8},
    {"eacute", 0xE9}, {"ecircumflex", 0xEA}, {"edieresis", 0xEB}, {"igrave", 0xEC}, {"iacute", 0xED},
    {"icircumflex", 0xEE}, {"idieresis", 0xEF}, {"eth", 0xF0}, {"ntilde", 0xF1}, {"ograve", 0xF2},
    {"oacute", 0xF3}, {"ocircumflex", 0xF4}, {"otilde", 0xF5}, {"odieresis", 0xF6}, {"divide", 0xF7},
    {"oslash", 0xF8}, {"ugrave", 0xF9}, {"uacute", 0xFA}, {"ucircumflex", 0xFB}, {"udieresis", 0xFC},
    {"yacute", 0xFD}, {"thorn", 0xFE}, {"ydieresis", 0xFF}, {"Amacron", 0x100}, {"amacron", 0x101},
    {"Abreve", 0x102}, {"abreve", 0x103}, {"Aogonek", 0x104}, {"aogonek", 0x105}, {"Cacute", 0x106},
    {"cacute", 0x107}, {"Ccaron", 0x10C}, {"ccaron", 0x10D}, {"Dcaron", 0x10E}, {"dcaron", 0x10F},
    {"Dcroat", 0x110}, {"dcroat", 0x111}, {"Emacron", 0x112}, {"emacron", 0x113}, {"Edotaccent", 0x116},
    {"edotaccent", 0x117}, {"Eogonek", 0x118}, {"eogonek", 0x119}, {"Ecaron", 0x11A}, {"ecaron", 0x11B},
    {"Gbreve", 0x11E}, {"gbreve", 0x11F}, {"Gcommaaccent", 0x122}, {"gcommaaccent", 0x123}, {"Imacron", 0x12A},
    {"imacron", 0x12B}, {"Iogonek", 0x12E}, {"iogonek", 0x12F}, {"Idotaccent", 0x130}, {"dotlessi", 0x131},
    {"Kcommaaccent", 0x136}, {"kcommaaccent", 0x137}, {"Lacute", 0x139}, {"lacute", 0x13A},
    {"Lcommaaccent", 0x13B}, {"lcommaaccent", 0x13C}, {"Lcaron", 0x13D}, {"lcaron", 0x13E}, {"Lslash", 0x141},
    {"lslash", 0x142}, {"Nacute", 0x143}, {"nacute", 0x144}, {"Ncommaaccent", 0x145}, {"ncommaaccent", 0x146},
    {"Ncaron", 0x147}, {"ncaron", 0x148}, {"Omacron", 0x14C}, {"omacron", 0x14D}, {"Ohungarumlaut", 0x150},
    {"ohungarumlaut", 0x151}, {"OE", 0x152}, {"oe", 0x153}, {"Racute", 0x154}, {"racute", 0x155},
    {"Rcommaaccent", 0x156}, {"rcommaaccent", 0x157}, {"Rcaron", 0x158}, {"rcaron", 0x159}, {"Sacute", 0x15A},
    {"sacute", 0x15B}, {"Scedilla", 0x15E}, {"scedilla", 0x15F}, {"Scaron", 0x160}, {"scaron", 0x161},
    {"Tcommaaccent", 0x162}, {"tcommaaccent", 0x163}, {"Tcaron", 0x164}, {"tcaron", 0x165}, {"Umacron", 0x16A},
    {"umacron", 0x16B}, {"Uring", 0x16E}, {"uring", 0x16F}, {"Uhungarumlaut", 0x170}, {"uhungarumlaut", 0x171},
    {"Uogonek", 0x172}, {"uogonek", 0x173}, {"Ydieresis", 0x178}, {"Zacute", 0x179}, {"zacute", 0x17A},
    {"Zdotaccent", 0x17B}, {"zdotaccent", 0x17C}, {"Zcaron", 0x17D}, {"zcaron", 0x17E}, {"longs", 0x17F},
    {"florin", 0x192}, {"Scommaaccent", 0x218}, {"scommaaccent", 0x219}, {"dotlessj", 0x237},
    {"circumflex", 0x2C6}, {"caron", 0x2C7}, {"breve", 0x2D8}, {"dotaccent", 0x2D9}, {"ring", 0x2DA},
    {"ogonek", 0x2DB}, {"tilde", 0x2DC}, {"hungarumlaut", 0x2DD}, {"Alpha", 0x391}, {"Beta", 0x392},
    {"Gamma", 0x393}, {"Delta", 0x394}, {"Epsilon", 0x395}, {"Zeta", 0x396}, {"Eta", 0x397}, {"Theta", 0x398},
    {"Iota", 0x399}, {"Kappa", 0x39A}, {"Lambda", 0x39B}, {"Mu", 0x39C}, {"Nu", 0x39D}, {"Xi", 0x39E},
    {"Omicron", 0x39F}, {"Pi", 0x3A0}, {"Rho", 0x3A1}, {"Sigma", 0x3A3}, {"Tau", 0x3A4}, {"Upsilon", 0x3A5},
    {"Phi", 0x3A6}, {"Chi", 0x3A7}, {"Psi", 0x3A8}, {"Omega", 0x3A9}, {"alpha", 0x3B1}, {"beta", 0x3B2},
    {"gamma", 0x3B3}, {"delta", 0x3B4}, {"epsilon", 0x3B5}, {"zeta", 0x3B6}, {"eta", 0x3B7}, {"theta", 0x3B8},
    {"iota", 0x3B9}, {"kappa", 0x3BA}, {"lambda", 0x3BB}, {"nu", 0x3BD}, {"xi", 0x3BE}, {"omicron", 0x3BF},
    {"pi", 0x3C0}, {"rho", 0x3C1}, {"sigma1", 0x3C2}, {"sigma", 0x3C3}, {"tau", 0x3C4}, {"upsilon", 0x3C5},
    {"phi", 0x3C6}, {"chi", 0x3C7}, {"psi", 0x3C8}, {"omega", 0x3C9}, {"theta1", 0x3D1}, {"Upsilon1", 0x3D2},
    {"phi1", 0x3D5}, {"omega1", 0x3D6}, {"afii10023", 0x401}, {"afii10051", 0x402}, {"afii10052", 0x403},
    {"afii10053", 0x404}, {"afii10054", 0x405}, {"afii10055", 0x406}, {"afii10056", 0x407}, {"afii10057", 0x408},
    {"afii10058", 0x409}, {"afii10059", 0x40A}, {"afii10060", 0x40B}, {"afii10061", 0x40C}, {"afii10062", 0x40E},
    {"afii10145", 0x40F}, {"afii10071", 0x451}, {"afii10099", 0x452}, {"afii10100", 0x453}, {"afii10101", 0x454},
    {"afii10102", 0x455}, {"afii10103", 0x456}, {"afii10104", 0x457}, {"afii10105", 0x458}, {"afii10106", 0x459},
    {"afii10107", 0x45A}, {"afii10108", 0x45B}, {"afii10109", 0x45C}, {"afii10110", 0x45E}, {"afii10193", 0x45F},
    {"afii10050", 0x490}, {"afii10098", 0x491}, {"afii61352", 0x2116}, {"enspace", 0x2002}, {"emspace", 0x2003},
    {"thinspace", 0x2009}, {"hairspace", 0x200A}, {"zerowidthspace", 0x200B}, {"hyphentwo", 0x2010},
    {"figuredash", 0x2012}, {"endash", 0x2013}, {"emdash", 0x2014}, {"horizontalbar", 0x2015},
    {"dblverticalbar", 0x2016}, {"underscoredbl", 0x2017}, {"quotesinglbase", 0x201A}, {"quotereversed", 0x201B},
    {"quotedblleft", 0x201C}, {"quotedblright", 0x201D}, {"quotedblbase", 0x201E}, {"dagger", 0x2020},
    {"daggerdbl", 0x2021}, {"bullet", 0x2022}, {"onedotenleader", 0x2024}, {"twodotenleader", 0x2025},
    {"ellipsis", 0x2026}, {"perthousand", 0x2030}, {"minute", 0x2032}, {"second", 0x2033},
    {"guilsinglleft", 0x2039}, {"guilsinglright", 0x203A}, {"exclamdbl", 0x203C}, {"fraction", 0x2044},
    {"Euro", 0x20AC}, {"trademark", 0x2122}, {"Ifraktur", 0x2111}, {"weierstrass", 0x2118}, {"Rfraktur", 0x211C},
    {"Ohm", 0x2126}, {"estimated", 0x212E}, {"aleph", 0x2135}, {"onethird", 0x2153}, {"twothirds", 0x2154},
    {"oneeighth", 0x215B}, {"threeeighths", 0x215C}, {"fiveeighths", 0x215D}, {"seveneighths", 0x215E},
    {"arrowleft", 0x2190}, {"arrowup", 0x2191}, {"arrowright", 0x2192}, {"arrowdown", 0x2193},
    {"arrowboth", 0x2194}, {"arrowupdn", 0x2195}, {"carriagereturn", 0x21B5}, {"arrowdblleft", 0x21D0},
    {"arrowdblup", 0x21D1}, {"arrowdblright", 0x21D2}, {"arrowdbldown", 0x21D3}, {"arrowdblboth", 0x21D4},
    {"universal", 0x2200}, {"partialdiff", 0x2202}, {"existential", 0x2203}, {"emptyset", 0x2205},
    {"increment", 0x2206}, {"gradient", 0x2207}, {"nabla", 0x2207}, {"element", 0x2208}, {"notelement", 0x2209},
    {"suchthat", 0x220B}, {"product", 0x220F}, {"summation", 0x2211}, {"minus", 0x2212}, {"asteriskmath", 0x2217},
    {"radical", 0x221A}, {"proportional", 0x221D}, {"infinity", 0x221E}, {"orthogonal", 0x221F}, {"angle", 0x2220},
    {"logicaland", 0x2227}, {"logicalor", 0x2228}, {"intersection", 0x2229}, {"union", 0x222A},
    {"integral", 0x222B}, {"therefore", 0x2234}, {"similar", 0x223C}, {"congruent", 0x2245},
    {"approxequal", 0x2248}, {"notequal", 0x2260}, {"equivalence", 0x2261}, {"lessequal", 0x2264},
    {"greaterequal", 0x2265}, {"propersubset", 0x2282}, {"propersuperset", 0x2283}, {"notsubset", 0x2284},
    {"reflexsubset", 0x2286}, {"reflexsuperset", 0x2287}, {"circleplus", 0x2295}, {"circlemultiply", 0x2297},
    {"perpendicular", 0x22A5}, {"dotmath", 0x22C5}, {"angleleft", 0x2329}, {"angleright", 0x232A},
    {"filledbox", 0x25A0}, {"H22073", 0x25A1}, {"filledrect", 0x25AC}, {"triagup", 0x25B2}, {"triagrt", 0x25BA},
    {"triagdn", 0x25BC}, {"triaglf", 0x25C4}, {"lozenge", 0x25CA}, {"circle", 0x25CB}, {"H18533", 0x25CF},
    {"openbullet", 0x25E6}, {"spade", 0x2660}, {"club", 0x2663}, {"heart", 0x2665}, {"diamond", 0x2666},
    {"checkmark", 0x2713}, {"check", 0x2713}, {"ff", 0xFB00}, {"fi", 0xFB01}, {"fl", 0xFB02}, {"ffi", 0xFB03},
    {"ffl", 0xFB04}, {"dotaccentcmb", 0x307}, {"gravecomb", 0x300}, {"acutecomb", 0x301}, {"tildecomb", 0x303},
    {"apple", 0xF8FF}, {"registersans", 0xAE}, {"copyrightsans", 0xA9}, {"trademarksans", 0x2122},
    {"registerserif", 0xAE}, {"copyrightserif", 0xA9}, {"trademarkserif", 0x2122}};

std::string cpToUtf8(char32_t cp) {
  std::string s;
  if (cp) utf8Append(s, cp);
  return s;
}

const std::unordered_map<std::string_view, char32_t>& glyphNameMap() {
  static const std::unordered_map<std::string_view, char32_t> m = [] {
    std::unordered_map<std::string_view, char32_t> t;
    t.reserve(sizeof(kGlyphNames) / sizeof(kGlyphNames[0]) + 128);
    for (const NamePair& p : kGlyphNames) t.emplace(p.name, p.cp);
    // Cyrillic: afii10017..afii10049 = А..Я (with Ё at 10023, listed above), afii10065..afii10097 = а..я.
    static std::string names[66];
    static const char32_t upper[33] = {0x410, 0x411, 0x412, 0x413, 0x414, 0x415, 0x401, 0x416, 0x417, 0x418, 0x419,
                                       0x41A, 0x41B, 0x41C, 0x41D, 0x41E, 0x41F, 0x420, 0x421, 0x422, 0x423, 0x424,
                                       0x425, 0x426, 0x427, 0x428, 0x429, 0x42A, 0x42B, 0x42C, 0x42D, 0x42E, 0x42F};
    for (int k = 0; k < 33; ++k) {
      names[k] = "afii" + std::to_string(10017 + k);
      names[33 + k] = "afii" + std::to_string(10065 + k);
      t[names[k]] = upper[k];
      t[names[33 + k]] = upper[k] == 0x401 ? 0x451 : upper[k] + 0x20;
    }
    return t;
  }();
  return m;
}
```

- The map is filled with `emplace` from the list (the first entry of a name would win; there are no duplicates), then the generated Cyrillic names are **assigned**: `afii10017`…`afii10049` → А…Я with Ё at `afii10023`, `afii10065`…`afii10097` → а…я with ё at `afii10071` (the same values the list already has for those two). The 66 generated names live in a function-local static array so that the `string_view` keys stay valid.
- `cpToUtf8(cp)`: `utf8Append` of `cp`, or the empty string for 0.

`uint32_t parseHex(std::string_view s, bool& ok)`: `ok` = `s` non-empty and at most 8 characters; every character must be a hex digit (upper or lower case), else `ok = false` and the result is 0; otherwise the value.

`std::string glyphComponent(std::string_view n)` — the text of one name component, first rule that applies:
1. Empty → empty.
2. In the map → `cpToUtf8(value)`.
3. A single ASCII letter → that letter (`a`, `Z`).
4. `uni` + groups of 4 hex digits (size ≥ 7 and `(size − 3) % 4 == 0`): each group → that code point; a non-hex group or a surrogate value → empty for the whole name; otherwise the concatenation (`uni00410042` → `AB`).
5. Size 5–7 and starting with `u`: `parseHex(n[1:])`; when valid, ≤ U+10FFFF and not a surrogate → that code point (`u1F600`; `u0041` → `A`).
6. Size 6 ending in `small` with an upper-case ASCII first letter (`Asmall`) → that letter in lower case.
7. Otherwise empty (`g123`, `.notdef`, `Cyrillic_ghe`).

`std::string glyphNameText(std::string_view name)`: cut the name at its first `.` when that is not the first character (`a.sc` → `a`; `.notdef` is kept whole); without `_` → `glyphComponent(name)`; with `_` → the components between underscores concatenated, empty as soon as one component is empty (`f_f_i` → `ffi` as three letters, not the ligature U+FB03).

`glyphNameToUtf8(name)` (public) = `glyphNameText(name)`.

### C.4 Widths of the standard 14 fonts

Codes 32–126, in thousandths of an em, verbatim:

```cpp
const uint16_t kHelvetica[95] = {278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278,
                                 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
                                 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
                                 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
                                 222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
                                 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584};
const uint16_t kTimes[95] = {250, 333, 408, 500, 500, 833, 778, 333, 333, 333, 500, 564, 250, 333, 250, 278,
                             500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 278, 278, 564, 564, 564, 444,
                             921, 722, 667, 667, 722, 611, 556, 722, 722, 333, 389, 722, 611, 889, 722, 722,
                             556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611, 333, 278, 333, 469, 500,
                             333, 444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778, 500, 500,
                             500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541};
```

### C.5 Matrices

`struct Matrix { double a = 1, b = 0, c = 0, d = 1, e = 0, f = 0; };` — a point `(x, y)` maps to `(a x + c y + e, b x + d y + f)`.
- `Matrix mul(const Matrix& m, const Matrix& n)`: the transformation `m` followed by `n` (`r.a = m.a n.a + m.b n.c`, `r.b = m.a n.b + m.b n.d`, `r.c = m.c n.a + m.d n.c`, `r.d = m.c n.b + m.d n.d`, `r.e = m.e n.a + m.f n.c + n.e`, `r.f = m.e n.b + m.f n.d + n.f`).
- `Matrix matrixFrom(const Object& arr)`: identity unless the array has at least 6 elements; then `a = at(0).num(1)`, `b = at(1).num()`, `c = at(2).num()`, `d = at(3).num(1)`, `e = at(4).num()`, `f = at(5).num()` (direct elements).
- `bool finite(double v)`: `std::isfinite(v) && |v| < 1e7`.

### C.6 CMaps

```cpp
struct CMapData {
  struct Range { uint32_t lo, hi; uint8_t bytes; };
  std::vector<Range> codespace;
  std::unordered_map<uint32_t, std::string> bf;      // code -> UTF-8
  std::unordered_map<uint32_t, uint32_t> cidChars;   // code -> CID
  struct CidRange { uint32_t lo, hi, cid; };
  std::vector<CidRange> cidRanges;
};
```

- `uint32_t bytesToCode(std::string_view s)`: the first up to 4 bytes, big-endian.
- `std::string utf16ToUtf8(std::string_view s)`: a 1-byte string is not UTF-16 (seen in broken files) and gives that byte as a code point. Otherwise 2-byte big-endian units (an odd last byte is dropped); surrogate pairs are combined; U+0000 and lone surrogates are dropped.

**`void parseCMap(std::string_view data, CMapData& out)`** — a token loop over a `Lexer`, with a list `ops` of pending operands, `mode` ∈ {None, CodeSpace, BfChar, BfRange, CidChar, CidRange} and a guard: the loop stops after 4 000 000 tokens.
1. A keyword `[` or `<<`: rewind over it and read the whole object with `object(o, refs = false)` (stop the loop if that fails); that array or dictionary becomes the token and is handled by rule 2 like any other operand (a bfrange can map to an array of strings).
2. A non-keyword token: in mode None, drop the oldest operand when `ops` already holds more than 8, then push; in the other modes push, then complete an entry when `ops` has reached its size:
   - CodeSpace, 2 operands: when both are strings and the first has 1–4 bytes → `{code(first), code(second), length of first}`; `ops` cleared either way.
   - BfChar, 2: when the first is a string: a string destination → `bf[code] = utf16ToUtf8(dst)`; a name destination → `bf[code] = glyphNameText(name)`; cleared.
   - BfRange, 3: when the first two are strings, `lo ≤ hi` and `hi − lo < 65536`: `count = hi − lo + 1` (the loops count, so a range ending at 0xFFFFFFFF ends too). A non-empty string destination → for `k` in `0 .. count − 1`: `bf[lo + k] = utf16ToUtf8(dst)`, then increment the last 16-bit unit of `dst` (big-endian, carrying into the high byte but not beyond), or the last byte when `dst` has 1 byte. An array destination → for `k < count` and `k <` the array size: a string element `k` gives `bf[lo + k] = utf16ToUtf8(element)` (other elements are skipped). Cleared.
   - CidChar, 2: a string and an `Int` → `cidChars[code] = value`; cleared.
   - CidRange, 3: two strings and an `Int` → `{code(lo), code(hi), cid}` appended; cleared.
3. A keyword: `begincodespacerange`, `beginbfchar`, `beginbfrange`, `begincidchar`, `begincidrange` set their mode; any keyword starting with `end` sets None; every other keyword (`usecmap`, `def`, `begincmap`, …) changes nothing. Then `ops` is cleared (for every keyword).

`usecmap` and `/WMode` are not read: a base CMap is never loaded, and vertical writing is laid out horizontally.

### C.7 TrueType `cmap`: glyph id → Unicode

`uint32_t be16(std::string_view s, size_t k)`: 0 when `k + 2 > s.size()`, else `(s[k] << 8) | s[k + 1]` (unsigned bytes). `uint32_t be32(s, k) = be16(k) << 16 | be16(k + 2)`.

**`std::unordered_map<uint32_t, char32_t> trueTypeGlyphUnicode(std::string_view font)`**:
1. Fewer than 12 bytes → empty. `numTables = be16(4)`; the table records at `12 + 16k` (while the 16-byte record fits) are searched for tag `cmap`; the **last** such record gives `cmap` offset and length. Offset 0 or `cmap + 4 > size` → empty. `t = font[cmap : cmap + min(length, size − cmap)]`.
2. Subtables: `n = be16(t, 2)`; for each record at `4 + 8k` that fits: `pid`, `eid`, `off`, `fmt = be16(t, off)`; score 4 for (3, 10, format 12), 3 for (0, any, 12), 2 for (3, 1, 4), 1 for (0, any, 4), otherwise none; the first subtable with the highest score wins. None → empty.
3. A real font maps every code point at most once; a damaged table may describe far more. One step counter covers both formats: `constexpr size_t kMaxSteps = size_t(1) << 21;` (2 097 152), and every code visited increments it first; past the limit the map built so far is returned.
4. Format 4: `segX2 = be16(best + 6)`; `ends = best + 14`, `starts = ends + segX2 + 2`, `deltas = starts + segX2`, `ranges = deltas + segX2`. For each segment `s < segX2 / 2`: skip when `start > end` (or `end − start > 65535`, which 16-bit values never are); for `c` from `start` to `end`, stopping before 0xFFFF: count the step; `gid = (c + delta) & 0xFFFF` when the range offset is 0, else `gid = be16(ranges + 2s + rangeOffset + 2(c − start))` and, when non-zero, `(gid + delta) & 0xFFFF`. A non-zero `gid` → `emplace(gid, c)`: the first code point mapped to a glyph wins.
5. Format 12: `groups = be32(best + 12)`; for each group at `best + 16 + 12g` that fits: `start = be32(at)`, `gid0 = be32(at + 8)`, `end = min(be32(at + 4), 0x10FFFF)` (Unicode ends there, so nothing wraps); skip when `end < start`; for `c` from `start` to `end`: count the step; `emplace(gid0 + (c − start), c)`.

### C.8 Type 1 built-in encoding

`bool type1BuiltinEncoding(std::string_view prog, std::array<std::string, 256>& names, bool& standard)`:
1. `standard = false`; find `/Encoding` (none → false); the part after it up to the next `eexec` (or the end).
2. A lexer over that part: if the first token is the keyword `StandardEncoding` → `standard = true`, return true.
3. Otherwise read tokens until `def` or `readonly`: after each keyword `dup`, an `Int` code and a name give `names[code] = name` for codes 0–255 (other `dup`s are skipped). Return whether any name was set.

### C.9 Fonts

```cpp
struct Font {
  bool composite = false;
  bool type3 = false;
  bool ucs2 = false;          // predefined Uni*-UCS2/UTF16 CMaps: the code is the Unicode value
  bool identity = true;       // composite: CID = code
  CMapData enc;               // composite: code space and code -> CID
  std::unordered_map<uint32_t, std::string> toUnicode;
  std::array<std::string, 256> simple;  // simple fonts: text of each code
  std::unordered_map<uint32_t, std::string> cidText;
  std::array<float, 256> widths{};      // simple fonts, text space units per unit of font size
  std::unordered_map<uint32_t, float> cidWidths;
  float defaultWidth = 1.0f;
  Matrix fontMatrix{0.001, 0, 0, 0.001, 0, 0};
  float sizeScale = 1.0f;  // Type 3: em of the glyph space in text space
  uint16_t style = 0;
};
```

- `cidOf(code)`: `code` when `identity`; else `enc.cidChars[code]`, else the first `cidRanges` entry containing it (`cid + code − lo`), else 0.
- `width(code)`: simple → `widths[code & 0xFF]`; composite → `cidWidths[cidOf(code)]`, else `defaultWidth`.
- `text(code, scratch)`: a non-empty `toUnicode[code]` wins; then simple → `simple[code & 0xFF]`; `ucs2` → `code` as a code point (empty for 0 and surrogates); else `cidText[cidOf(code)]`, else empty.
- `forEachCode(s, f)`: simple → every byte is a code of length 1. Composite: at each position the shortest length 1–4 for which the bytes form a code inside a `codespace` range of exactly that byte length; when none matches (or there is no code space), 2 bytes (1 at the very end). `f(code, nbytes)`.

`std::string baseFontName(std::string_view n)`: removes a subset prefix — six upper-case ASCII letters and `+` — when the name is longer than 7 bytes.

`void styleFromName(std::string_view name, FontStyle& st)` only ever sets flags to true. `lower` = the name with `std::tolower` on each byte (ASCII only: no locale is ever set); `sep` = the first `-` or `,`; `styleRaw` / `styleLower` = the part after `sep` (empty without one).
- bold: `lower` contains `bold`, `black`, `heavy`, `demi` or `ultra`, or `styleRaw` contains `Bd`, `Hv`, `Sb` or `Blk`;
- italic: `lower` contains `italic`, `oblique`, `slanted` or `kursiv`, or `styleLower` contains `ital`, or `styleRaw` contains `It` or `Obl`;
- mono: `lower` contains `mono`, `courier`, `consol`, `menlo`, `monaco`, `typewriter`, `code`, `fixed` or `inconsolata`.

### C.10 Document state: pages and fonts

```cpp
struct ContentReader::Impl {
  struct PageRef {
    Object dict;
    Object resources;
    double box[4] = {0, 0, 612, 792};  // crop box, user space
    int rotate = 0;
    int obj = 0;
  };
  File& file;
  bool pagesLoaded = false;
  std::vector<PageRef> pages;
  std::unordered_map<int, int> pageIndex;                       // page object number -> index
  std::unordered_map<uintptr_t, std::unique_ptr<Font>> fonts;  // by object number (or dictionary address)
  std::vector<FontStyle> styles;
  std::unique_ptr<Font> fallback;
};
```

Members: `explicit Impl(File& f) : file(f) {}`, `void loadPages();`, `void walkPages(const Object& node, Object resources, const Object& media, const Object& crop, const Object& rotate, int depth, std::unordered_set<int>& seen);`, `Font* font(const Object& ref);`, `std::unique_ptr<Font> buildFont(const Object& fd);`, `uint16_t styleIndex(const FontStyle& s);`.

`styleIndex(s)`: the index of an equal entry in `styles` (same name and all three flags); otherwise append it, unless 65 535 styles exist already (then 0).

**`walkPages(nodeRef, resources, media, crop, rotate, depth, seen)`**:
1. Stop when `depth > 64` or 100 000 pages exist; a reference already in `seen` is skipped (cycles), otherwise added.
2. `node = resolve(nodeRef)`, a dictionary or nothing happens. Its own `Resources`, `MediaBox`, `CropBox` and `Rotate` (resolved) replace the inherited values.
3. `kids = get(node, "Kids")`: an array, while the direct `/Type` is not `Page` → walk every kid with `depth + 1` and return. Every other dictionary is a page (also a `Pages` node without kids).
4. The page: `dict = node`, the resources, `obj` = the reference's number (0 for a direct node). Box: start from 0 0 612 792; with a MediaBox of at least 4 elements each corner is its resolved `num(previous value)`; normalised to min/max; narrower or lower than 1 point → 0 0 612 792. A CropBox of at least 4 elements (resolved `num()`, default 0) is intersected with the media box and used only when the intersection is at least 1 point wide and high.
5. `r = (int) Rotate.integer(0) % 360`, plus 360 when negative, rounded down to a multiple of 90.
6. `pageIndex[obj] = index` when `obj` is non-zero; append.

**`loadPages()`** (once): walk from the catalog's `Pages` (`resolve(trailer["Root"])`) with empty inherited values. When that yields no page (a broken page tree or a lost catalog): every object `k` from 1 to `objectCount() − 1` whose `get(k)` is a dictionary with direct `/Type /Page`, in number order, is walked as a reference with the `Resources`, `MediaBox`, `CropBox` and `Rotate` it inherits — for each key the nearest value found going up the resolved `Parent` chain (at most 32 levels) — with the same `seen` set.

**`buildFont(fd)`** (`fd` is the font dictionary):
1. `subtype = get(fd, "Subtype")`; `st.name = baseFontName(get(fd, "BaseFont").s)`.
2. **`Type0`** (composite):
   - `Encoding` a name containing `UCS2` or `UTF16` → `ucs2 = true`; any name → code space `{0, 0xFFFF, 2}` (Identity-H/V, and approximately every other predefined CMap). A stream → `parseCMap` of its decoded data into `enc` (a failed decode parses nothing); an empty code space becomes `{0, 0xFFFF, 2}`; `identity` = no `cidChars` and no `cidRanges`.
   - The CIDFont: `DescendantFonts` resolved; its first element (resolved) when it is an array. If it is a dictionary:
     - `defaultWidth = DW.num(1000) / 1000`;
     - `W`: walk the array: `first` (resolved `integer()`), then either an array of widths (`cidWidths[first + j] = w / 1000` for at most 65 536 elements; advance 2) or, when 3 elements remain, `last` and one width for `first ..= last` (at most 65 536 codes; advance 3); otherwise stop;
     - `desc = FontDescriptor`; an empty `st.name` takes the CIDFont's `BaseFont`;
     - a `FontFile2` stream in `desc` is a TrueType program. When there is one and `fd` has **no** `ToUnicode` key (direct presence): decode it (nothing more on failure), `gidUni = trueTypeGlyphUnicode(program)`; `gidMap` = the decoded `CIDToGIDMap` when that is a stream. A non-empty `gidMap`: for each CID `c` with `2c + 1 < gidMap.size()`, `gid = be16(gidMap, 2c)` and `cidText[c]` = `cpToUtf8` of that glyph's code point when known. An empty one (the name `Identity`, no map, a failed decode): `cidText[gid] = cpToUtf8(code point)` for every glyph of `gidUni` (CID = GID).
3. **Simple fonts** (Type1, MMType1, TrueType, Type3 and anything else):
   - `type3` = subtype `Type3`; `desc = FontDescriptor`. For Type 3: a `FontMatrix` of at least 6 elements replaces `fontMatrix`; `sizeScale = |fontMatrix.d| × 1000`, reset to 1 unless `0.01 < sizeScale < 100`.
   - `symbolFont` = the name starts with `Symbol`; `dingbats` = it contains `Dingbats`.
   - Widths: `scale = type3 ? fontMatrix.a : 0.001`; `missing = desc ? MissingWidth.num() × 0.001 : 0`. With a `Widths` array: all 256 widths = `missing`, then `widths[FirstChar + k] = width × scale` for codes 0–255 (`FirstChar.integer(0)`). Without one (the standard 14 fonts): `courier` (name contains `Courier`) → 0.6 everywhere; otherwise codes 32–126 from `kTimes` (name contains `Times`) or `kHelvetica`, ÷ 1000, and every other code 0.5 (Times) or 0.556.
   - Base encoding: StandardEncoding; TrueType → WinAnsi; a `Symbol…` name → Symbol. `baseByName(n)`: `WinAnsiEncoding` → WinAnsi, `MacRomanEncoding` → MacRoman, `StandardEncoding` → Standard, `MacExpertEncoding` → Standard, any other name → unchanged.
   - `enc = get(fd, "Encoding")`: a name → `baseByName`. Otherwise, when `desc` is a dictionary, the font is not Type 3 and `enc` is not a dictionary with a `BaseEncoding` key: a `FontFile` stream (Type 1 program) is decoded and `builtin = type1BuiltinEncoding(program, names, builtinStandard)`; a built-in `StandardEncoding` sets the base to Standard and `builtin = false`.
   - `enc` a dictionary: its `BaseEncoding` name → `baseByName`; `Differences`: `code` starts at 0; a number sets `code = integer()`; a name sets `names[code]` (codes 0–255) and increments `code`.
   - For each code `c`: `s = glyphNameText(names[c])` when a name is set; when `s` is empty and (no name is set, or `!builtin`), `s = cpToUtf8(base[c])` — so with a built-in encoding an unknown glyph name gives no text rather than the base character. In a `Dingbats` font every code above 32 gives `•` (U+2022: Dingbats are mostly list marks). `simple[c] = s`.
4. `ToUnicode`: a stream → its decoded data through `parseCMap`; `toUnicode` = the `bf` map. A name `Identity-H` or `Identity-V` on a composite font → `ucs2 = true`.
5. Style, when `desc` is a dictionary: `Flags & 1` → mono, `Flags & (1 << 6)` → italic, `Flags & (1 << 18)` → bold; `FontWeight >= 600` → bold; `|ItalicAngle| >= 5` → italic. Then `styleFromName(st.name, st)`; `style = styleIndex(st)`.

**`font(ref)`**: the cache key is `object number << 1` for a reference, `address of the dictionary | 1` for a direct dictionary, 0 otherwise; a cached font is returned. Otherwise `fd = resolve(ref)`; when it is not a dictionary, or more than 20 000 fonts are cached, the shared `fallback` font — built once by `buildFont` of an empty dictionary (StandardEncoding text, Helvetica widths, style `""` with no flags) — is returned. Otherwise the new font is built and cached under its key (`fonts.emplace(key, std::move(f))`). The key is never 0 there: a reference to object 0 always reads as null (`File::get(0)`), and an argument that is neither a reference nor a dictionary resolves to itself, which is no dictionary; both take the fallback above.

### C.11 The content stream interpreter

`class Interpreter` (file-local), constructed with the document state, the output page, `withImages` and the base matrix (the page matrix of C.12) as the initial CTM. State:

```cpp
struct GState {
  Matrix ctm;
  double tc = 0, tw = 0, th = 1, tl = 0, rise = 0;
  int tr = 0;
  Font* font = nullptr;
  double fs = 0;
};
struct Marked { bool artifact = false; bool hasActual = false; std::string actual; size_t start = 0; };
GState gs_; std::vector<GState> stack_; Matrix tm_, tlm_;   // text matrix and line matrix, identity at first
std::vector<Marked> marked_;
size_t stackFloor_ = 0, markedFloor_ = 0;  // Q and EMC of the running form stop here (the page's entries)
int artifactDepth_ = 0;
std::vector<int> forms_;   // form XObjects being run (recursion guard)
std::string scratch_; size_t ops_ = 0;
```

Members: `Interpreter(ContentReader::Impl& doc, PageContent& out, bool withImages, const Matrix& base)`, `void run(std::string_view data, const Object& res, int depth);` (public), and privately `void op(std::string_view name, std::vector<Object>& a, const Object& res, int depth, Lexer& lx);`, `void show(std::string_view bytes);`, `void showArray(const Object& arr);`, `void nextLine(double tx, double ty);`, `void doXObject(const std::string& name, const Object& res, int depth);`, `void skipInlineImage(Lexer& lx);`, `void beginMarked(const std::string& tag, const Object& props, const Object& res);`, `void endMarked();`, `Font* currentFont();`. After the class, `double numArg(const std::vector<Object>& a, size_t k)`.

`currentFont()` is `gs_.font`, or `font(null)` (the fallback) when none is set. `numArg(a, k)` is `a[k].num()` (0 when missing), replaced by 0 when not `finite`. `nextLine(tx, ty)`: `tlm_ = translate(tx, ty) × tlm_` (`mul(t, tlm_)`), `tm_ = tlm_`.

**`run(data, res, depth)`**:
```
lexer over data; args = [] (capacity 16)
while token(t):
  if ++ops_ > 20 000 000: return              // pathological content; counted over the whole page, forms included
                                              // (at depth 0 this return also skips the closing step below)
  if t is a keyword:
    "[" or "<<": rewind, object(o, refs = false) (stop the loop if it fails); push o to args if fewer than 64
    "]" ">>" "{" "}" ")": ignored (args are kept)
    otherwise: op(t.s, args, res, depth, lexer); args cleared
  else: push t to args if fewer than 64
if depth == 0: endMarked() until marked_ is empty   // marked content left open ends with the page
                                                    // (a form's ends with the form, see doXObject)
```

**Operators** (by name; everything not listed is ignored, including `ET`, every path, colour and clipping operator, `MP`/`DP`, `d0`/`d1`; Type 3 glyph procedures are never run):

| operator | action |
|---|---|
| `q` | push `gs_` when fewer than 256 states are saved (the page's and the running forms' together) |
| `Q` | pop into `gs_` only when `stack_.size() > stackFloor_`: inside a form, a `Q` never pops a state the page or an outer form saved |
| `'` | `nextLine(0, −tl)`; show the last operand when it is a string |
| `"` | with at least 3 operands `tw = numArg(0)`, `tc = numArg(1)`; `nextLine(0, −tl)`; show the last operand when it is a string |
| `cm` | with at least 6 operands: `ctm = m × ctm` (`m` from `numArg(0..5)`, `mul(m, ctm)`) |
| `BT` | `tm_ = tlm_ = identity` |
| `Tf` | with at least 2 operands and a name first: `gs_.font = font(the direct entry of that name in get(res, "Font"), or null)`, `gs_.fs = numArg(1)` |
| `Tj` | show the last operand when it is a string |
| `TJ` | `showArray(last operand)` |
| `Td` | `nextLine(numArg(0), numArg(1))` |
| `TD` | `tl = −numArg(1)`, then `nextLine(numArg(0), numArg(1))` |
| `Tm` | with at least 6 operands: `tm_ = tlm_ = m` (from `numArg(0..5)`) |
| `T*` | `nextLine(0, −tl)` |
| `Tc` `Tw` `TL` `Ts` | `tc`, `tw`, `tl`, `rise` = `numArg(0)` |
| `Tz` | `th = numArg(0) / 100` |
| `Tr` | `tr = (int) numArg(0)` |
| `Do` | the first operand a name → `doXObject(name)` |
| `BI` | `skipInlineImage` (inline images are skipped, never recorded) |
| `gs` | the first operand a name: `ext = get(get(res, "ExtGState"), name)`; when its `Font` entry (resolved) has at least 2 elements: `gs_.font = font(element 0)`, `gs_.fs = numArg(the array, 1)` (element 1, direct, checked with `finite` like `Tf`) |
| `BMC` | `beginMarked(name or "", null)` |
| `BDC` | `beginMarked(name or "", second operand or null)` |
| `EMC` | `endMarked()` |

The text matrix and the marked-content stack are not part of the saved graphics state.

**`show(bytes)`**: `f = currentFont()`; `m = tm_ × ctm` (`mul(tm_, ctm)`); `size = |fs| × hypot(m.c, m.d) × f.sizeScale`; `flags` = `kGlyphArtifact` when `artifactDepth_ > 0`, plus `kGlyphInvisible` for rendering modes 3 and 7. For each code `(code, n)` of `f.forEachCode(bytes)`:
```
w0 = f.width(code)
gw = w0 × fs × th                                       // the glyph's own advance
adv = (w0 × fs + tc + (n == 1 && code == 32 ? tw : 0)) × th
origin = (rise × m.c + m.e, rise × m.d + m.f)            // (0, rise) in text space
if both coordinates are finite and fewer than 4 000 000 glyphs exist:
  Glyph{text = f.text(code), x, y = origin, ex = x + gw × m.a, ey = y + gw × m.b, size, font = f.style, flags}
m.e += adv × m.a; m.f += adv × m.b; tm_.e += adv × tm_.a; tm_.f += adv × tm_.b
```
Word spacing applies to the single-byte code 32 only (also in composite fonts with a 1-byte code space). A glyph without a Unicode mapping is still recorded, with empty text.

**`showArray(arr)`**: strings are shown; a number `v` moves the text matrix by `adv = −v / 1000 × fs × th` along its x axis (`tm_.e += adv × tm_.a`, `tm_.f += adv × tm_.b`) unless `adv` is not finite.

**`doXObject(name, res, depth)`**:
1. `x = resolve(get(res, "XObject").find(name))`; missing or not a stream → nothing.
2. `Subtype /Image`: when `withImages`, record a `PageImage` with `image = x`, the bounding box of the unit square under the CTM (the corners `(e, f)`, `(a + e, b + f)`, `(c + e, d + f)`, `(a + c + e, b + d + f)`) and `artifact = artifactDepth_ > 0`; at most 10 000 images per page. Return.
3. Only `Subtype /Form`, and only while `depth < 12`; a form whose object number is already in `forms_` is skipped. Decode it (nothing on failure). `fres = get(x, "Resources")`.
4. The form's `q`/`Q` and `BMC`/`EMC` cannot reach the page's: an unbalanced form neither pops states the page saved nor leaves its own behind, and marked content it leaves open ends with it. In order:
   ```
   savedGs = gs_; savedTm = tm_; savedTlm = tlm_
   savedStackFloor = stackFloor_; savedMarkedFloor = markedFloor_
   stackFloor_ = stack_.size(); markedFloor_ = marked_.size()
   if the form's Matrix has at least 6 elements: gs_.ctm = mul(matrixFrom(Matrix), gs_.ctm)   // form matrix first
   forms_.push(number)
   run(data, fres is a dictionary ? fres : res, depth + 1)
   forms_.pop()
   while marked_.size() > markedFloor_: endMarked()      // its open marked content ends here (ActualText applies)
   stack_.resize(stackFloor_)                            // states it saved and never restored are dropped
   stackFloor_ = savedStackFloor; markedFloor_ = savedMarkedFloor
   tm_ = savedTm; tlm_ = savedTlm; gs_ = savedGs
   ```
   Nothing is pushed onto `stack_` for the form itself.

**`skipInlineImage(lx)`**: read at most 200 tokens up to the keyword `ID` (arrays and dictionaries are read as whole objects with `refs = false`; stop at the end of the data); then skip one byte and search the data for `EI` preceded by a white-space byte and followed by a white-space byte or the end of the data; continue after it, or at the end of the data when there is none.

**`beginMarked(tag, props, res)`**: `start` = the glyph count; `artifact = tag == "Artifact"`; a name `props` is looked up in `get(res, "Properties")`; a dictionary with an `ActualText` string (resolved) sets `hasActual` and `actual = textToUtf8(ActualText, false)`. An artifact increments `artifactDepth_`. Pushed on `marked_`.

**`endMarked()`** (nothing when `marked_.size() <= markedFloor_`: an `EMC` inside a form never closes the page's marked content, and with no form running the floor is 0): pop `m`; an artifact decrements `artifactDepth_` (not below 0). Nothing more unless `m.hasActual` and no artifact is still open. Then:
- Glyphs were shown since `m.start`: `letters(s)` counts the code points of `s` that are `isLetterCp`. When `shown` (the letters of all those glyphs' texts) is at least 3 and `letters(actual) × 2 < shown`, the replacement is ignored — a producer's mistake such as `" "` over a whole heading. Otherwise the first of those glyphs gets `text = actual` and every later one gets empty text and `kGlyphReplaced`.
- Nothing was shown and `actual` is not empty: a glyph is added at the current text position `t = tm_ × ctm`: `x = ex = t.e`, `y = ey = t.f`, `size = |fs| × hypot(t.c, t.d)` (no Type 3 scale), `text = actual`, `font` = the current font's style or 0, flags 0 — when both coordinates are finite.

### C.12 `ContentReader`

- The constructor creates the `Impl` for the file; the destructor is defaulted. Every public function first calls `loadPages()`.
- `pageCount()`: the number of pages.
- `pageIndexOf(objNum)`: the index recorded for that page object, or −1.
- `pageBox(index, w, h)`: false outside `0 .. count − 1`; `w`, `h` = the box size, swapped for rotations 90 and 270.
- `Matrix pageMatrix(const double box[4], int rotate)` (file-local), from user space to page space, with `(x0, y0, x1, y1)` the box:

  | rotate | matrix `{a, b, c, d, e, f}` |
  |---|---|
  | 90 | `{0, 1, 1, 0, −y0, −x0}` |
  | 180 | `{−1, 0, 0, 1, x1, −y0}` |
  | 270 | `{0, −1, −1, 0, y1, x1}` |
  | otherwise (0) | `{1, 0, 0, −1, −x0, y1}` |
- `userToPage(index, x, y, px, py)`: false outside the range; otherwise `(px, py)` = the point under `pageMatrix`.
- `readPage(index, out, withImages)`: `out = PageContent{}`; false outside the range; `out.width/height` from `pageBox`. `Contents` (resolved): a stream is decoded (a failure leaves the data empty); an array → each element resolved, every stream that decodes is appended followed by `'\n'`. An `Interpreter` with `pageMatrix(box, rotate)` as the CTM runs the data with the page's resources at depth 0. Returns true (also for an empty page).
- `fonts()`: the `styles` vector; `Glyph::font` indexes it.

---

## Part D — `src/core/PdfParser.cpp`

### D.1 Includes and layout

Includes: `core/PdfParser.h`, `<algorithm>`, `<array>`, `<cmath>`, `<cstring>`, `<exception>`, `<map>`, `<unordered_map>`, `<unordered_set>`, `core/ImageCodec.h`, `core/PdfContent.h`, `core/PdfReader.h`, `core/TxtParser.h`, `core/Unicode.h`.

Everything except the four public functions of D.19 is in an unnamed namespace inside `ll`, which starts with `using pdf::Glyph; using pdf::Object; using pdf::PageContent;`. Definition order: the text helpers (D.2); the layout structures (D.3), `startsListItem`, `class LineBuilder` (D.4), `buildTables` (D.6), `usableImageFilter` (D.7), `sortIntoRows` (D.5), `analyzePage` (D.5); the document statistics and passes (D.8–D.13); the lexicon (D.14); `struct Para`, `class Assembler` with `startsWithNumber` placed between the class and its members, and `endsSentence` and `endsWithFunctionWord` between `append` and `close` (D.15); the picture functions (D.16); `struct OutlineItem`, `class Outline`, `matchKey` (D.17); the metadata functions (D.18); `parseDocument` and `readDocumentMeta` (D.19); then, outside the unnamed namespace, the public functions (D.19).

The file-local declarations, with their exact signatures:

```cpp
void appendGlyphText(std::string& out, std::string_view t);
bool isBulletCp(char32_t c);
bool isUpperStart(std::string_view s);
bool isLowerStart(std::string_view s);
bool sameSize(float a, float b);
bool startsCaption(std::string_view s);
bool startsListItem(std::string_view s, bool* dash);
class LineBuilder {
 public:
  explicit LineBuilder(const std::vector<pdf::FontStyle>& fonts);
  Line build(const std::vector<const Glyph*>& g, size_t from, size_t to);
 private:
  const std::vector<pdf::FontStyle>& fonts_;
  float maxGap_ = 0, gapX_ = 0;
};
void buildTables(std::vector<Line>& lines);
bool usableImageFilter(pdf::File& file, const Object& img);
template <class T, class GetY, class GetX, class Tol>
std::vector<int> sortIntoRows(std::vector<T>& v, GetY y, GetX x, Tol tol);
void analyzePage(const PageContent& pc, const std::vector<pdf::FontStyle>& fonts, PageLayout& out);
std::string normalizedKey(std::string_view s);
bool isPageNumberText(std::string_view s);
float modeOf(const std::map<int, double>& hist, float unit, float def);
Stats documentStats(const std::vector<PageLayout>& pages);
void dropRepeatedLines(std::vector<PageLayout>& pages, const Stats& st);
void columnEdges(const std::vector<PageLayout>& pages, const Stats& st, std::vector<std::array<Edges, 3>>& out);
void paragraphStyle(const std::vector<PageLayout>& pages, const std::vector<std::array<Edges, 3>>& edges, Stats& st);
bool startsNoteMark(std::string_view s);
void markFootnotes(std::vector<PageLayout>& pages, const Stats& st);
void dropBackgrounds(std::vector<PageLayout>& pages);
void collectWords(std::string_view text, Lexicon& lex);
bool keepsHyphen(const Lexicon& lex, std::string_view prefixWord, std::string_view nextWord);
std::string lastWord(std::string_view s);
std::string firstWord(std::string_view s);
class Assembler {
 public:
  Assembler(Document& doc, const std::vector<PageLayout>& pages, const Stats& st,
            const std::vector<std::array<Edges, 3>>& edges, const Lexicon& lex);
  void run();
  std::vector<std::pair<int, float>> positions;  // (page, y of its first line) of each block, for destinations
 private:
  bool continues(const Line& a, int pa, const Line& b, int pb) const;
  void append(const Line& l, int page);
  void close();
  void emitImage(const PageImage& im, int page);
  void flushImages();
  void flushNotes();
  float pitchFor(float size) const;
  const Edges& edges(int page, int col) const;
  // members: see D.15
};
bool startsWithNumber(std::string_view s);
bool endsSentence(std::string_view s);
bool endsWithFunctionWord(std::string_view s);
bool colorSpaceInfo(pdf::File& file, const Object& csIn, pdf::ImageSpec& spec, int depth = 0);
bool makeImage(pdf::File& file, const Object& img, ImageData& out, int depth = 0);
class Outline {
 public:
  Outline(pdf::File& file, pdf::ContentReader& cr);
  std::vector<OutlineItem> read();
 private:
  void walk(Object node, Object ref, int depth, std::vector<OutlineItem>& items, std::unordered_set<int>& seen);
  void resolveDest(Object dest, OutlineItem& it);
  Object named(const std::string& name);
  void loadNames();
  void walkTree(const Object& node, int depth, std::unordered_set<int>& seen);
  pdf::File& file_;
  pdf::ContentReader& cr_;
  bool namesLoaded_ = false;
  std::unordered_map<std::string, Object> names_;
};
std::string matchKey(std::string_view s);
std::string xmpValue(std::string_view xmp, std::string_view tag);
bool usableTitle(const std::string& t);
void readMeta(pdf::File& file, BookMeta& meta);
void detectLanguage(Document& doc);
bool parseDocument(std::string_view raw, Document& doc, std::string_view fileStem, std::string* error,
                   const PdfOptions& opt);
bool readDocumentMeta(std::string_view head, std::string_view tail, uint64_t fileSize, BookMeta& meta);
```

The pipeline (D.19): every page is interpreted (C) and laid out on its own (D.4–D.7), pictures are converted as they are met; then document-wide statistics, running heads, column edges, paragraph style, footnotes, the lexicon, the cover and background pictures; then the assembler turns the lines into blocks; then drawing labels are removed, the outline (or the headings) becomes the table of contents, and the language is guessed.

### D.2 Text helpers

**`void appendGlyphText(std::string& out, std::string_view t)`** — the text of one glyph as the book model wants it:
1. When every byte of `t` is in 0x20–0x7E (also for empty `t`), `t` is appended as it is.
2. Otherwise per code point:
   - U+FB00 → `ff`, U+FB01 → `fi`, U+FB02 → `fl`, U+FB03 → `ffi`, U+FB04 → `ffl`, U+FB05 and U+FB06 → `st`;
   - U+00A0, U+2000–U+200A (all of them, U+2007 included), U+202F, U+205F, U+3000, U+2028, U+2029 and TAB → one space;
   - U+200B, U+200C, U+200D, U+2060, U+FEFF and U+FFFD → dropped;
   - U+F0B7, U+F0A7, U+F06C, U+F0D8, U+F0FC, U+F076, U+F0A8, U+F0E0, U+F075, U+F06E, U+F0B2 (Symbol/Wingdings bullets in the private-use area) → `•` (U+2022);
   - other code points below U+0020 or in U+007F–U+009F → dropped; other private-use code points U+E000–U+F8FF → dropped;
   - everything else is appended (U+00AD soft hyphens are kept).

**`bool isBulletCp(char32_t c)`**: U+2022, U+25E6, U+25AA, U+25AB, U+25A0, U+25A1, U+25CF, U+25CB, U+25C6, U+25C7, U+25BA, U+25B6, U+27A2, U+27A4, U+2713, U+2714, U+2717, U+2756, U+2023, U+2043, U+00B7, U+2219, U+25B8, U+2192.

**`bool isUpperStart(std::string_view s)`**: skips leading `"`, `'`, U+201C, U+2018, U+00AB, `(` and `[`; true when the next code point is a letter with `toLowerCp(c) != c`. Empty (or only those marks) → false.

**`bool isLowerStart(std::string_view s)`**: the first code point (no skipping) is a letter with `toUpperCp(c) != c`.

**`bool sameSize(float a, float b)`**: `|a − b| <= max(0.35, 0.04 × max(a, b))` — two sizes a book would use for the same kind of text (8 and 9 are different).

**`bool startsCaption(std::string_view s)`**: `s` starts with one of `"Figure "`, `"Fig. "`, `"Table "`, `"Listing "`, `"Exhibit "`, `"Рис. "`, `"Рисунок "`, `"Таблица "` and the byte after it is an ASCII digit.

**`bool startsListItem(std::string_view s, bool* dash)`** (`*dash` is set to false first):
1. Empty → false.
2. The first code point is U+2013, U+2014, U+2212 or `-`: true (and `*dash = true`) only when a space byte follows it.
3. A bullet (`isBulletCp`) or `*` → true, with no space required.
4. Numbering: `paren` = `s[0] == '('` (then `k = 1`). Up to 3 ASCII digits. Without digits, one ASCII letter followed by `)` — or by `.` when not `paren` — counts instead, but a letter followed by `.` must be lower case (`"A. Smith"` is not an item). Then, with `paren`, the byte at `k` must be `)`; without it, `.` or `)`. Then the next byte must be a space.
   Items: `1. x`, `12) x`, `(3) x`, `a) x`, `a. x`, `A) x`, `(a) x`. Not items: `A. x`, `1234. x`, `1.x`, `(a. x`.

Internal flag: `constexpr uint8_t kMono = 0x80;` (a run in a monospaced font, later `kSpanCode`).

### D.3 Layout structures

```cpp
struct Line {
  std::string text;
  std::vector<std::pair<uint32_t, uint8_t>> runs;  // (byte offset, SpanFlag bits | kMono) style changes
  float x0 = 0, x1 = 0, y = 0, size = 0;
  float firstWord = 0;  // width of the first word
  float maxGap = 0;     // widest gap between words, in units of the font size
  float capX = -1;      // the line starts with a drop cap that stood at this x (the paragraph's left edge)
  float textX = 0;      // where the second word starts (for a list item: its text after the mark)
  float gapX = 0;       // where the text after the widest gap starts (a definition list: the definition)
  bool besideImage = false;  // a picture to the left: the text wraps around it, its indent means nothing
  int col = 0;          // 0 = single column or spanning, 1 = left, 2 = right
  uint16_t font = 0;    // font of most characters (ContentReader::fonts index)
  uint8_t flags = 0;    // style of most characters (SpanFlag bits)
  bool mono = false;
  bool tabular = false;   // a wide gap inside (dot leaders, tab stops): a line of a list, table or contents
  bool list = false;      // starts with a list mark
  bool listDash = false;  // ... and the mark is a dash (also used inside sentences)
  bool drop = false;      // running head, page number, repeated stamp
  bool footnote = false;  // in the notes at the foot of the page
  bool tableRow = false;  // a row of a table: its cells joined with " | "
  struct Cell { uint32_t begin; float x0; };  // begin: byte offset in text
  std::vector<Cell> cells;  // set when the line was put together from row segments split at wide gaps
  struct Word { uint32_t begin, end; float x0, x1; };  // byte range in text
  std::vector<Word> words;  // for finding table columns
};
struct PageImage {   // PdfParser's own, not pdf::PageImage
  int image = -1;  // Document::images index
  int src = -1;    // index in PageContent::images
  int obj = 0;
  float x0 = 0, y0 = 0, x1 = 0, y1 = 0;
  int col = 0;
  bool background = false;
};
struct Item { bool image = false; int index = 0; };
struct PageLayout {
  float width = 0, height = 0;
  std::vector<Line> lines;
  std::vector<PageImage> images;
  std::vector<Item> order;  // reading order
};
```

### D.4 `LineBuilder::build(g, from, to)`

`class LineBuilder` holds a reference to the font styles (`ContentReader::fonts()`) and two members `maxGap_` and `gapX_` (0), reset at the end of every `build`. `build` makes a `Line` from the glyphs `g[from:to]` of one row segment, sorted by x:

1. **Dominant size**: a `std::map<int, size_t>` keyed by `lround(size × 4)` adds `max(1, byte length of the glyph's raw text)` per glyph; the key with the largest weight wins (ties: the smallest key). `size = key / 4`.
2. **Baseline**: the y of the first glyph (in x order) whose size is within 0.3 of `size`, else of `g[from]`. `l.size = size`, `l.y = baseline`.
3. **Word-gap threshold**: `0.15 × size`. For letter-spaced text it follows the gaps: collect `g[k].x − g[k−1].ex` for consecutive pairs where neither text is empty or a single space; with at least 6 gaps, sort them, `low` = the element at index `count × 3 / 10`; when `low > 0.08 × size`, `threshold = max(threshold, low + 0.15 × size)`.
4. State: `lastSpace = true`, `spanVisible = false`, `prevEnd = −1e9`, `spaceStart = −1`, character counters `bold`, `italic`, `mono`, `total` = 0, `cur = 0xFF` (no run yet), `haveX0 = false`, `firstWordDone = false`, `lastInkEnd = 0`, and per-font character counts in a `std::map<uint16_t, size_t>`.
5. For each glyph: `piece = appendGlyphText("", glyph.text)`.
   1. **Empty piece**: if the glyph has `kGlyphReplaced` and `spanVisible`, `prevEnd = max(prevEnd, ex)` (it continues the ActualText shown before it); if it does not have `kGlyphReplaced`, `spanVisible = false` (a glyph without text — a dot leader, a decoration — leaves a gap). Next glyph.
   2. `spanVisible = true`.
   3. **Widest gap**: when `haveX0 && size > 0`: `gap = (x − prevEnd) / size`; when a run of space glyphs is open (`spaceStart >= 0`) and the piece contains a non-space, `gap = max(gap, (x − spaceStart) / size)`; a gap larger than `maxGap_` sets `maxGap_ = gap` and `gapX_ = x`.
   4. A piece with a non-space closes the space run (`spaceStart = −1`).
   5. **All-space piece**: open a space run at `x` when none is open; when `!lastSpace`: append `' '`, `lastSpace = true`, and when `haveX0 && !firstWordDone`: `firstWordDone = true`, `firstWord = lastInkEnd − x0`; `prevEnd = max(prevEnd, ex)`; next glyph.
   6. **Space from a gap**: when `!lastSpace` and `x − prevEnd > threshold` (in points): append `' '`, `lastSpace = true`, and the same `firstWord` rule.
   7. **Style**: from the glyph's font style (when its index is inside the table): bold → `kSpanBold`, italic → `kSpanItalic`, mono → `kMono`. When the glyph is smaller than `0.85 × size`: above the baseline by more than `0.18 × size` (`y < baseline − 0.18 size`) → `kSpanSup`, else below it by more than `0.1 × size` → `kSpanSub`.
   8. **A list mark glued to its text gets a space**: when the text is non-empty, `!lastSpace`, and the text is exactly one bullet code point (`isBulletCp`), append `' '`, `lastSpace = true`.
   9. A style different from `cur` records a run `(text.size(), flags)`; `cur = flags`. (So the run starts after a space inserted before the glyph: a space after a superscript belongs to the superscript's run.)
   10. After a space, the piece's leading spaces are dropped (`" self-regulate"`).
   11. **Words**: after a space (or for the first piece) a new `Word{text.size(), 0, x, ex}` starts; the piece is appended; the last word's `end` = the text size and `x1 = max(x1, ex)`. `lastSpace` = the piece ends with a space.
   12. Counters: `n` = code points of the piece as appended (after step 10); `total += n`, the glyph's font `+= n`, and `bold`/`italic`/`mono += n` for those flags.
   13. Edges: the first visible glyph sets `x0 = x`; otherwise the first glyph after the first word boundary (`firstWordDone && textX == 0`) sets `textX = x`. `x1 = max(x1, ex)`, `lastInkEnd = ex`, `prevEnd = max(prevEnd, ex)`.
6. Trailing spaces are removed from the text, then trailing runs that start at or after its end.
7. Without a word boundary `firstWord = x1 − x0`.
8. With `total > 0`: `flags |= kSpanBold` when `bold × 2 > total`, `kSpanItalic` likewise; `mono = mono × 2 > total`. `font` = the font with the most characters (ties: the smallest index).
9. `maxGap = maxGap_`, `gapX = gapX_`, `tabular = maxGap_ > 2.5`; the members are reset to 0. `list = startsListItem(text, &listDash)`.

### D.5 `analyzePage(pc, fonts, out)` — one page's layout

`out.width/height` = the page size `W`, `H`.

**1. Glyph filter.** Count artifact and other glyphs; `keepArtifacts = (no other glyph) && artifacts >= 40` (a page made only of tagged decoration still shows). A glyph takes part unless:
- it is an artifact and `!keepArtifacts`;
- its size is below 1 or above 400;
- its origin is outside `[−2, W + 2] × [−2, H + 2]`;
- it is rotated or mirrored: with `dx = ex − x`, `dy = ey − y`, the advance is not zero (`|dx| + |dy| >= 0.01`) and not `dx > 0 && |dy| <= 0.25 dx`.

Invisible glyphs (`kGlyphInvisible`, the OCR layer of scanned pages) are **kept**: they are the text of such pages.

**2. Drop caps** (only when more than 20 glyphs take part). `median` = the element at `count / 2` after `std::nth_element` on the sizes. At most 16 caps. A glyph is a candidate when its size is at least `2.2 × median` and its text is exactly one letter code point. Its partner is chosen among the other glyphs with size `<= 1.5 × median` and non-empty text, with `y` in `[cap.y − 0.8 × cap.size, cap.y + 0.3 × h.size]` and `x` in `[cap.ex − 2, cap.ex + 3 × h.size]`: the topmost (`h.y < best.y − 0.5`), and on the same height (within 0.5) the leftmost. With a partner, a copy of the cap replaces it in the glyph list: `y = ey = partner.y`, `size = partner.size`, `ex = partner.x`, `x = partner.x − 0.01`; its original x is remembered (`capOrigins`). The copies live in a vector reserved for 16, so the pointers stay valid. The cap therefore starts its partner's line and joins the first word without a space ("T" + "he" → "The").

**3. Rows.** The glyphs are `std::stable_sort`ed by y. A glyph joins the last row when `|y − row.y| <= 0.3 × max(glyph size, row size)`, where `row.y` is the y of the row's first glyph and `row.size` the largest size so far; otherwise it starts a row.

**4. Superscripts and subscripts that formed rows of their own** go back to their line. For each row `r` (in order) with 1–8 glyphs: `maxSize`, `minX`, `maxX` (of `ex`). Try the next row, then the previous one (`k + 1`, then `k − 1`); the target `n` must be non-empty, with `maxSize < 0.85 × n.size`, `r.y` within `[n.y − 0.65 n.size, n.y + 0.35 n.size]`, and horizontally within `2 × n.size` of `n`'s extent (`maxX >= nMin − 2 n.size` and `minX <= nMax + 2 n.size`). The glyphs are appended to `n` (whose `y` and `size` do not change) and `r` is emptied.

**5. Segments.** For each non-empty row: `std::stable_sort` by x; drop overprinted copies (fake bold, shadows): a glyph whose text equals the last kept glyph's non-empty text with both coordinates within `0.15 ×` its size of it. Split at gaps: a new segment starts at glyph `k` when `x − end > 1.8 × max(row.size, 1)`, where `end` is the largest `ex` so far in the row. Each segment is built with `LineBuilder::build`; segments with empty text are dropped.

**6. Cap lines**: a segment whose `y` is within 0.5 of a moved cap's `y` and whose `x0` is within 0.5 of the cap's new `x` gets `capX` = the cap's original x.

**7. Two columns.** Only with at least 10 segments and `W > 100`. `w = (int) W`; a coverage count per integer x in `[0, w]`: every segment not wider than `0.7 W` (spanning titles do not hide a gutter) adds 1 over `[clamp((int) x0, 0, w), clamp((int) x1, 0, w)]` and its byte length to `chars`. The longest run of uncovered x starting in `[(int)(0.2 W), (int)(0.8 W))` (the run may extend beyond `0.8 W`; the first longest wins) is the gutter candidate. It is accepted when its length is at least 8 and, counting all segments, at least 4 lie left of it (`x1 <= from + 1`) and at least 4 right of it (`x0 >= from + len − 1`), with each side holding at least a tenth of `chars` bytes. Then `gutterFrom = from`, `gutterTo = from + len`, and every segment gets `col = 1` (`x1 <= gutterFrom + 1`), `2` (`x0 >= gutterTo − 1`) or `0` (spanning).

**Sorting into rows** — `sortIntoRows(v, y, x, tol)` puts items into rows, top to bottom, each row left to right, without a comparator that treats nearby heights as equal (that is no strict weak ordering, and standard libraries would disagree about its order):
```
byY = the indices 0 .. n−1, std::stable_sort by y(v[i]) (strictly less)
r = 0; for k in 0 .. n−1: if k > 0 and y(v[byY[k]]) − y(v[byY[k−1]]) > tol(v[byY[k−1]], v[byY[k]]): ++r
                          row[byY[k]] = r
std::stable_sort byY by (row, then x(v[i]))
v = the items in that order; return their rows in that order
```
In order of height, an item more than `tol` below the one before it starts a new row (so a row is a chain of items each close to the previous one).

**8. Same-row segments of one column become one line again** ("Contents ... 25", a loosely set justified line). `segRow = sortIntoRows(segs, y, x0, tol(a, b) = 0.3 × max(a.size, b.size))`. For each non-empty segment `l` (index `k`), the following segments `m` (index `j`) are visited while `segRow[j] == segRow[k]`; `m` is skipped (`continue`, not stop) when it is more than `0.3 × max(m.size, l.size)` away from `l` vertically (the row reached it through others), when it is empty, in another column, or starts left of `l.x1`. Otherwise `m` is joined into `l`:
```
joinGap = (m.x0 − l.x1) / max(1, l.size)
if joinGap >= l.maxGap && joinGap >= m.maxGap: l.gapX = m.x0
else if m.maxGap > l.maxGap: l.gapX = m.gapX
l.maxGap = max(l.maxGap, m.maxGap, joinGap); l.tabular = l.maxGap > 2.5
off = l.text.size() + 1
if l.cells is empty: l.cells += {0, l.x0}
l.cells += {off, m.x0}
m's words (offsets + off) are appended to l.words
l.text += ' ' + m.text
m's runs (offsets + off) are appended to l.runs; when m has no run at offset 0, a run (off, 0) is inserted
  before the first run at or after off (back to regular style)
l.x1 = max(l.x1, m.x1)
m.text = ""                     // emptied, removed later
```
`size`, `flags`, `font`, `firstWord`, `textX` and `list` of `l` are not changed.

**9. Tables**: `buildTables(segs)` (D.6). Then the non-empty segments become `out.lines`, in their sorted order.

**10. Pictures** (from `pc.images`, in content order):
- An artifact picture is not shown; when narrower than `0.6 W` its (unclipped) box is kept as a *wrap box*.
- Otherwise a `PageImage` with `src` = its index, `obj` = the XObject's object number, the box clipped to the page (`max(0, x0)`, `max(0, y0)`, `min(W, x1)`, `min(H, y1)`). It is dropped when `w < 0.04 W`, `h < 0.025 H` or `w × h < 1600` (rules, bullets, decorations). `background = w × h > 0.6 W H`. With two columns, `col` = 1 (`x1 <= gutterFrom + 2`), 2 (`x0 >= gutterTo − 2`) or 0.
- Every non-background picture is also a wrap box.

**11. Text beside a picture**: a line gets `besideImage` when a wrap box's right edge lies in `[l.x0 − 3 × l.size, l.x0 + 2]` and the box spans the line vertically (`box.y0 <= l.y` and `box.y1 + 1.5 × l.size >= l.y − l.size`).

**12. Reading order.** Keys: each line `{top = y − 0.7 × size, x = x0, col}`, each picture `{top = y0, x = x0, col}`, lines first, then pictures; sorted with `sortIntoRows(keys, top, x, tol = 0.5)` (rows of keys whose tops are chained within half a point, each row by x; the returned rows are not used). Without a gutter the order is the sorted keys. With two columns the keys are dealt band by band: column-1 keys go to a left list and column-2 keys to a right list; a spanning key (col 0) first flushes the left list and then the right list into the order, then is appended itself; at the end the lists are flushed again. A spanning title or picture therefore closes a band; inside a band the whole left column comes before the right one.

### D.6 `buildTables(lines)` — rows split into cells

Runs of lines that were put together from row segments become table rows. The columns are the vertical strips that no word of the run crosses; every line of the run is cut there (also where its own gap was narrow); a row is the lines up to a wider vertical gap — or, when the lines are evenly spaced, up to a line with text in the first column that does not carry on the row above — and its cells' lines are joined. `lines` are one page's segments in the order of D.5 step 8.

For each column value `col` = 0, 1, 2 separately, `idx` = the indices of the non-empty lines of that column, in order; `i = 0`:
```
while i < idx.size():
  head = lines[idx[i]]
  if head.cells.size() < 2 || head.mono || head.words is empty: ++i; continue
  // the run: lines of the same size close below each other, as long as split lines keep coming
  j = i; lastMulti = i; multi = 1
  while j + 1 < idx.size():
    m = lines[idx[j + 1]]
    if m.mono || !sameSize(m.size, head.size) || m.y − lines[idx[j]].y > 2.6 × m.size: break
    if m.cells.size() >= 2: lastMulti = j + 1; ++multi
    else if j + 1 − lastMulti > 3: break
    ++j
  j = lastMulti + 1
  // lines just below the last split line that carry on its cells (the rest of the last row)
  while j < idx.size() && j − lastMulti <= 3:
    m = lines[idx[j]]
    if m.mono || m.cells.size() >= 2 || !sameSize(m.size, head.size) || m.y − lines[idx[j − 1]].y > 1.6 × m.size: break
    ++j
  if multi < 2: i = lastMulti + 1; continue
```
Then, over the lines `idx[i .. j−1]`:
1. `minX`/`maxX` over all their words (`x0`, `x1`); give up on this run (`i = j`) unless `maxX > minX` and `maxX − minX <= 4000`.
2. Coverage in half points: `n = (int)((maxX − minX) × 2) + 2` cells; each word covers `[clamp((int)((x0 − minX) × 2), 0, n−1), clamp((int)((x1 − minX) × 2), 0, n−1)]`.
3. Column starts: `{minX}`, plus, for every uncovered stretch `[x, e)` with `x >= 1` that ends before `n` and is at least `max(2, 0.3 × head.size)` points wide (`(e − x) × 0.5`), the start `minX + e × 0.5 − 0.25`. Fewer than 2 columns → give up (`i = j`).
4. `minDy` and `maxDy` = the smallest and the largest `y` difference between consecutive lines of the run (1e9 and 0 for one line). Rows are told apart by extra space between them; without any, `evenlySpaced = maxDy <= 1.12 × minDy` (also true for one line).
5. `column(x)` = the last column whose start is `<= x + 0.25`. Every line's `cells` are rebuilt: one cell per change of column along its words, `begin` = the word's offset, `x0` = **the column number** (stored in the float field).
6. **Parts**, each line's cells taken before the rows take the lines apart: `struct Part { size_t col; std::string text; float x1; float firstW; };`. For each line of the run, for each of its cells: the text from its `begin` to the next cell's `begin` (or the end of the text), `trimView`ed; an empty one is skipped. Otherwise a part with `col = min(columns − 1, column number)`, that text, `x1` = the largest `x1` of the line's words whose `begin` lies in the cell's byte range (where its last word ends), and `firstW` = the width (`x1 − x0`) of the first such word; parts are kept in column order. `colRight[c]` = the largest part `x1` in column `c` over the whole run (the right end of the column's longest text).
7. Rows. `cells[c]` — the row being put together, one string per column — and `cellEnd[c]` — where the row's text in column `c` ends on its last line (0 at first); `rowFirst = idx[i]`, `rowBold = true`, `rowX0 = 1e9`, `rowX1 = 0`.

   `carriesOn(k)`: evenly spaced, a line still belongs to the row above when it carries on that row's text: in a column they share, the row's text ran out of room (the line's first word there would not have fitted after it) and the line's text goes on in lower case. A cell's room ends where the next column begins, less the narrowest gap between columns; the last column's at its longest text, which says less, so there the text above must have two or more words. A shared column whose text ended a sentence means a new row. In code: `carried = false`; for each part `p` of line `k`, in column order:
   - `above = cells[p.col]`; empty → next part;
   - `above` ends with `.`, `!`, `?`, `:` or `;` → return **false** (also when an earlier part had carried);
   - `last = (p.col + 1 == columns)`; `limit = last ? colRight[p.col] : colStarts[p.col + 1] − max(2, 0.3 × em)` (`em` = the run's head size);
   - `full = cellEnd[p.col] + 0.3 × em + p.firstW > limit`;
   - `full && isLowerStart(p.text) && (!last || above contains a space)` → `carried = true` (the loop goes on).

   It returns `carried`. For each line `k` of the run:
   - `firstColumn` = its first part is in column 0;
   - a new row starts — `flushRow(rowFirst)`, `rowFirst = idx[k]` — when `k > i` and (`y − previous y > 1.12 × minDy`, or `evenlySpaced && firstColumn && !carriesOn(k)`): in an evenly spaced table a line with text in the first column starts a row, unless it carries on the text above;
   - each part is added to `cells[p.col]`: when that cell is non-empty, a trailing `-` is removed if the part starts lower case (`isLowerStart`), otherwise a space is added unless the cell ends with `/`; then the part's text; `cellEnd[p.col] = p.x1`;
   - `rowBold &= (line.flags & kSpanBold) != 0`; `rowX0 = min`, `rowX1 = max` of the line's `x0`/`x1`;
   - every line except `rowFirst` gets empty text (it is removed later).
8. `flushRow(rowFirst)` at the end; `i = j`.

`flushRow(into)` writes the row into `lines[into]`: trailing empty cells are dropped; for each cell `c < last`: `" |"` before every cell but the first, then, for a non-empty cell, `' '` (except before the first) and the cell text; the cells are cleared and their `cellEnd` set to 0. So `["a", "b"]` → `"a | b"`, `["a", "", "b"]` → `"a | | b"`, `["", "b"]` → `" | b"` (the text starts with a space). The line's `runs` become `{(0, kSpanBold)}` when `rowBold`, else none; `tableRow = tabular = true`, `list = listDash = false`, `x0 = rowX0`, `x1 = rowX1`, `cells` cleared; `rowBold`, `rowX0`, `rowX1` are reset.

Examples (10-point text in a font whose characters are all 5 points wide, the first column at x 20 or 30, the second at x 150):
- `Name`/`Value`, `alpha`/`1`, `beta`/`2`, 13 points apart → evenly spaced; every line has text in column 0 and carries on nothing → three rows `Name | Value`, `alpha | 1`, `beta | 2`.
- `Name`/`Value`, `alpha`/`red`, `beta`/`dark green` (the unit test) → three rows: in the last column `Value` and `red` end well before the column's longest text, and the single words above have no space.
- `apple`/`red`, `banana`/`yellow`, `cherry`/`dark red` → three rows: `yellow` would not have fitted after `red` (the column's longest text, `dark red`, ends at 190), but the text above is one word.
- `Customer`/`Rider request and pickup` over `Journey`/`continue the trust.` (the unit test) → one row `Customer Journey | Rider request and pickup continue the trust.`: `Rider request and pickup` is the last column's longest text, so `continue` does not fit after it, starts lower case, and the text above has spaces.
- `Name`/`Value`, 13 points lower `more` (column 0 only), 22 points lower `alpha`/`1`, 22 points lower `2` at x 150 and `x` at x 200 → not evenly spaced, so only the gaps wider than 1.12 × 13 split: `Name more | Value`, `alpha | 1`, ` | 2 | x`.

### D.7 `bool usableImageFilter(pdf::File& file, const Object& img)`

`f = file.get(img, "Filter")` (resolved): an array is usable unless one of its elements, resolved, is a name whose canonical name is `JPXDecode`, `JBIG2Decode` or `CCITTFaxDecode`; anything else is usable unless it is such a name itself. Missing filters and elements that are not names count as usable. (`DCTDecode` is usable: JPEGs are kept.)

### D.8 Document statistics

`std::string normalizedKey(std::string_view s)`: a key that ignores case, punctuation and numbers: an ASCII digit appends `#` unless the key already ends with `#` (so `12`, and also `1 2`, give one `#`), a letter is appended lower-cased (`toLowerCp`), everything else is dropped. `"Page 12"` → `page#`, `"CHAPTER 1 FOUNDATIONS"` → `chapter#foundations`.

`bool isPageNumberText(std::string_view s)`:
1. `t = trimCopy(s)`; the prefixes `"page "`, `"Page "`, `"PAGE "`, `"стр. "`, `"Стр. "` are tried in this order, each removed once when `t` starts with it.
2. Empty or longer than 16 bytes → false.
3. Per byte: ASCII digits and the letters `ivxlcdmIVXLCDM` are counted (a NUL byte is not a roman letter: `c && std::strchr(...)`); space, `-`, `/`, `|`, `.` and every byte `>= 0x80` (dashes around the number) are ignored; any other byte (NUL included) → false. So `"Page 3 of 9"` is no page number: its letters count as other bytes.
4. True for 1–5 digits and no roman letters, or for no digits and 1–6 roman letters. `"12"`, `"- 7 -"`, `"xiv"`, `"Page 3"`, `"3 / 120"` are page numbers; `"2024 edition"`, `"x1"` are not.

```cpp
struct Stats {
  float bodySize = 10;
  float pitch = 12;     // baseline distance inside paragraphs (body size)
  float paraGap = 15;   // a larger distance starts a paragraph
  int bodyFont = -1;    // the font of most body text
  bool spaced = false;     // extra space between paragraphs
  bool indented = false;   // first-line indent
  bool justified = false;  // most lines end at the right edge
};
```

`float modeOf(const std::map<int, double>& hist, float unit, float def)`: the key with the largest count (ties: the smallest key) times `unit`, or `def` when no count is positive.

**`Stats documentStats(pages)`** (lines with `drop` are ignored throughout):
1. `bodySize` = `modeOf` of a histogram keyed by `lround(size × 2)` adding each line's byte length, unit 0.5, default 10; below 3 → 10.
2. `bodyFont` = `(int) modeOf` of the fonts of the lines with `sameSize(size, bodySize)`, weighted by byte length, default −1.
3. Line distances: per page, along the reading order: a picture resets `prev`; for a line, `body = sameSize(size, bodySize)`; when `prev` exists, `l` is body text and in the same column as `prev`, and `0.8 × bodySize < dy < 3 × bodySize` (`dy = l.y − prev.y`), count `dys[lround(dy × 4)] += 1` and `total += 1`. Then `prev = body ? l : none`.
4. `pitch = modeOf(dys, 0.25, bodySize × 1.2)`.
5. A second cluster: the key with the largest count (strictly larger, so the smallest key on ties) among distances `dy` with `1.15 × pitch < dy < 2.6 × pitch`. When `total > 0`, its count is at least `0.03 × total` and at least 5: `paraGap = (pitch + dy) × 0.5`, `spaced = true`. Otherwise `paraGap = 1.3 × pitch`.

`justified` and `indented` are set by D.11.

### D.9 `dropRepeatedLines(pages, st)` — running heads, page numbers, stamps

1. For each page with lines: the line indices sorted by `y` with `std::stable_sort`. A table row (`tableRow`) is skipped — a row of a table is content, also at the top or foot of a page — but it keeps its place in the ranks. For the line at rank `r` of `n` lines: `where = 1` (top) when `r < 3 && y < 0.12 × height`; `where = 2` (bottom) when `r + 3 >= n && y > 0.86 × height` (this overrides the top). `key = normalizedKey(text)`; skipped when the key is empty and `where == 0`, or longer than 120 bytes. For `where == 0` the key gets `"|" + (int)(y / 6)` appended (its height in 6-point bands). Each `key + digit(where)` is counted once per page (later duplicates on the same page are skipped): `where` 1 → `topKeys[key]`, 2 → `bottomKeys[key]`, 0 → `anyKeys[key]`; the line becomes a candidate.
2. `stampMin = max(4, pageCount / 4)`.
3. `folioHead(l)` — a running head with its page number ("12   CHAPTER 1 FOUNDATIONS", "SECTION TITLE   13"), however few pages repeat it: `l.tabular` and (the text after its last space, or the text before its first space, `isPageNumberText`).
4. For each candidate, `small = size <= 1.12 × bodySize`:
   - top or bottom: `drop` when (its key's count `>= 3` and `small`) or (`isPageNumberText(text)` and `size <= 1.3 × bodySize`) or (`small` and `folioHead`);
   - elsewhere: `drop` when `anyKeys[key] >= stampMin`, `small` and the book has at least 8 pages.
5. Every line whose `normalizedKey` is `thispageintentionallyleftblank` is dropped.

An empty key counts too at the top or bottom: a line of punctuation only (`"* * *"`, `"—"`) in those places on 3 pages is dropped like a running head.

### D.10 `columnEdges(pages, st, out)` — left and right edges of body text

`struct Edges { float left = 0, right = 0; bool known = false; };` — one per page and column (`std::array<Edges, 3>` per page).
1. For every page and column 0–2, over the lines that are not dropped, in that column and `sameSize(size, bodySize)`: a histogram `left[lround(x0)] += 1` (lines with `besideImage` are not counted there) and the list of `x1` values. Skip the column when fewer than 4 lines or the histogram is empty.
2. `e.left`: first `modeOf(left, 1, 0)`; then the **smallest** `x` whose neighbourhood `x − 1 ..= x + 1` holds at least `need = max(2.0, 0.1 × line count)` lines replaces it (not the most common start: a page of list items or quotations has more lines indented than at the margin).
3. `e.right` = the sorted `x1` value at index `count × 9 / 10`. `known = true`. Votes `lround(left)` and `lround(right)` go to the histograms of the page's parity (`page % 2`) and column.
4. Pages with little text borrow: an unknown column whose parity histogram is non-empty gets `left = modeOf(parity left, 1, 0)`, `right = modeOf(parity right, 1, page width)`, `known = true`.

### D.11 `paragraphStyle(pages, edges, st)` — justified text and first-line indents

Over each page's reading order (pictures are skipped without resetting `prev`; dropped lines are skipped): a line is body text when `sameSize(size, bodySize)`, its column's edges are known and it is not `tabular`; any other line sets `prev = none`. For each body line: `++body`; `|x1 − right| < 1.5` → `++atRight`; when `prev` is indented by more than `0.8 × bodySize` and less than `4 × bodySize` from `left`, the line itself is within `0.3 × bodySize` of `left` (`x0 − left < 0.3 bodySize`) and `prev` is not a list item → `++indentStarts`; `prev = line`.

`justified = body > 0 && atRight × 10 >= body × 4`; `indented = indentStarts >= max(5, body / 60)`.

### D.12 Footnotes

`bool startsNoteMark(std::string_view s)`: the first code point is `*`, U+2020, U+2021, U+00A7, U+00B9, U+00B2, U+00B3 or in U+2070–U+2079; or the text starts with 1–3 ASCII digits followed by `.`, `)` or a space.

`markFootnotes(pages, st)`, per page:
1. `lastBody` = the largest `y` of a non-dropped line with `sameSize(size, bodySize)`; none → skip the page.
2. `below` = the non-dropped lines with `y > lastBody`, sorted by `y` (`std::stable_sort`).
3. Skip unless: `below` is non-empty; its first line is below `0.45 × height`; it is at least `1.4 × pitch` below `lastBody`; it `startsNoteMark`; and **every** line of `below` has `size <= 0.92 × bodySize`.
4. Then all of `below` are footnotes.

### D.13 `dropBackgrounds(pages)` — pictures under text

Per page, a picture is a background when the non-dropped lines of at least 15 bytes whose centre (`(x0 + x1) / 2`, `y − 0.3 size`) lies strictly inside it hold at least 60 bytes together. Then, repeatedly until nothing changes, every picture touching a background picture (boxes overlapping or within 2 points: `a.x0 <= b.x1 + 2 && b.x0 <= a.x1 + 2 && a.y0 <= b.y1 + 2 && b.y0 <= a.y1 + 2`) becomes one too (the tiles of a background). Backgrounds get `image = −1` (not shown; the text is the content, also for a scanned page under its OCR text).

### D.14 The lexicon: which line-end hyphens belong to the word

```cpp
struct Lexicon {
  std::unordered_set<std::string> words;       // lowercase, seen whole inside a line
  std::unordered_set<std::string> hyphenated;  // lowercase words with an inner hyphen
};
```

`collectWords(text, lex)`: words are maximal runs of letters (lower-cased with `toLowerCp`) and `-` (a `-` only after at least one letter); trailing `-` are removed from each word. The first and the last word of the line are skipped (they may be halves of a word broken across lines); the others go to `hyphenated` when they contain `-`, else to `words`. It is run over every non-dropped line of the book (footnotes, code and table rows included).

`bool keepsHyphen(lex, prefixWord, nextWord)` (both lower-cased with `toLowerUtf8`):
1. Either empty → true.
2. `pre + "-" + suf` in `hyphenated` → true.
3. `pre + suf` in `words` → false.
4. `pre` is a single code point → true ("e-mail", "x-ray": hyphenation never leaves one letter).
5. `pre` is `self`, `well` or `non` → true.
6. Otherwise false.

`lastWord(s)`: the trailing letters of `s` after removing trailing `-` bytes. `firstWord(s)`: the leading letters of `s`.

### D.15 The assembler: lines → blocks

```cpp
struct Para {
  std::vector<const Line*> lines;
  int page = 0;
  float y = 0;
  float maxX1 = 0;
  std::string text;
  std::vector<std::pair<uint32_t, uint8_t>> runs;
};
```

`class Assembler` holds references to the document, the pages, the final `Stats`, the edges and the lexicon, and: `Para cur_`, `int curPage_ = −1`, `pendingImages_` (pictures met inside a paragraph: `(const PageImage*, page)`), `pendingNotes_` (footnote lines waiting for the paragraph they cut to end), `bool lastWasCode_ = false`, `next_` (the next text line of the same page, for hanging indents) and `next_page_`. Its public `positions` vector receives `(page, y)` for every block it adds, in step with `doc.blocks` (used for outline destinations, D.19). `pitchFor(size) = pitch × size / bodySize`; `edges(page, col)` is that page's `Edges`.

`bool startsWithNumber(std::string_view s)`: the part before the first space (which must exist, at position 1–8) is numeric (only digits, `.` and `)`, with at least one digit) or roman (only the bytes `I V X L C .`; a NUL byte is not roman: `c && std::strchr(...)`) — `"1.13 Transition"`, `"IV Results"`; also `". x"`.

#### `continues(a, pa, b, pb)` — does line `b` (page `pb`) continue the paragraph whose last line is `a` (page `pa`)?

`em = max(a.size, b.size)`. The rules are tested in this order; the first that decides returns:

1. `a.mono || b.mono` → **no**.
2. `definition` = the paragraph has one line, `a.tabular`, `!b.tabular`, `a.gapX > a.x0` and `|b.x0 − a.gapX| < 0.6 em` (a definition list: "Term     definition", continued under the definition). `(a.tabular || b.tabular) && !definition` → **no**.
3. `!sameSize(a.size, b.size)` → **no**.
4. `aEnds` = `a`'s last byte is `.`, `!`, `?`, `:` or `;`, or it ends with `”` (the 3 bytes E2 80 9D) or with `»` (the 2 bytes C2 BB).
5. `b.list` → **no**, except when `b.listDash && !aEnds && !(first line of the paragraph).listDash` (a dash after an unfinished sentence is punctuation; in a paragraph that started with a dash it starts the next item).
6. `startsCaption(b.text)` → **no**. `startsCaption(first line's text) && b.font != a.font` → **no** (a caption ends where the font changes back).
7. `flowBreak` = `pa != pb || b.y < a.y − 0.3 × a.size || a.col != b.col`. `ea = edges(pa, a.col)`, `eb = edges(pb, b.col)`.
8. Without `flowBreak`: `gap` = `paraGap` when `sameSize(a.size, bodySize)`, else `pitchFor(a.size) × 1.3`; `b.y − a.y > gap × (em / max(1, a.size))` → **no**.
9. `hyphen` = `a` ends with `-`, with U+00AD or with U+2010. `hyphen && isLowerStart(b.text) && !flowBreak` → **yes**.
10. Indents are measured from each line's own column edge: `leftA = ea.known ? ea.left : a.x0`, `leftB` likewise; `indA = a.x0 − leftA`, `indB = b.x0 − leftB`. `first` = the paragraph's first line.
   - `hanging` = one line so far, `a.list || startsWithNumber(a.text)`, `a.textX > a.x0` and `|b.x0 − a.textX| < 0.5 em` (continued under the text of a numbered item: "1.13 Transition to ..." under "Transition").
   - `hangingRun` = `!indented && !flowBreak && next_ && next_page_ == pb && sameSize(next_.size, b.size) && |next_.x0 − b.x0| < 0.3 em && next_.y > b.y` (a hanging indent such as a bibliography: the line after `b` is indented like `b`).
   - `skipIndents` = `a.besideImage || b.besideImage || definition || hanging`.
11. When `eb.known && !skipIndents`:
   - `!flowBreak && indB > 0.8 em && indA < 0.4 em && !(one line && first.list) && !hangingRun` → **no** (a first-line indent);
   - `flowBreak && indB − indA > 0.8 em && indB < 6 em` → **no** (more indented than the line before, across a page).
12. When `!skipIndents`:
   - `capEdge` = `first.capX >= 0 && !flowBreak && |b.x0 − first.capX| < em` (lines below a drop cap go back to its edge);
   - `(two or more lines || first.list) && indB < indA − 0.8 em && !capEdge` → **no** (a line left of the paragraph's lines: the end of a list item or a quotation);
   - `one line && a.list && a.textX − a.x0 > 0.8 em && indB < a.textX − leftA − 0.5 em && indB < indA − 0.3 em` → **no** (a list item continues only at its text, not back at the mark).
13. Was `a` full?
   - With `ea.known`: `right = ea.right`; when `!flowBreak`, the paragraph has two or more lines and `block = max(cur_.maxX1, b.x1)` is less than `ea.right − 1.5 em`, `right = block` (a narrower block such as a quotation). `room = right − a.x1`. `strict = justified || !(spaced || indented)`. `full` = `strict ? room <= b.firstWord + 0.8 em : a.x1 − ea.left >= 0.6 × (right − ea.left)`. `!full` → **no** (if the next line's first word would have fitted, the paragraph ended there; ragged text with other paragraph marks only ends at a clearly short line).
   - Without: `a.x1 − a.x0 < 0.6 × (page width × 0.7)` → **no** (`room` stays 0).
14. `!flowBreak && !hyphen`: `a` ends with `.`, `!`, `?` or `:`, `isUpperStart(b.text)` and `b.y − a.y > pitchFor(a.size) × 1.15` → **no** (a sentence end with a little extra space).
15. `flowBreak && hyphen` → **yes**.
16. `flowBreak`: `justified && ea.known && room <= 1.0 em` → **yes** (a full justified line goes on); otherwise **yes** exactly when `isLowerStart(b.text) || !aEnds`.
17. **Yes.**

#### `append(l, page)` — joining a line to the paragraph

The first line: `page`, `y = l.y − l.size`, `text`, `runs`, `maxX1 = l.x1` are taken from it. For a further line, with `t` = the paragraph text, the join is decided first (`joined` means no space is inserted):
1. `t` ends with U+00AD (`C2 AD`): it is removed, `joined` (a soft hyphen is always hyphenation).
2. Else `t` ends with `-` or U+2010 and the code point before it is a letter: when `isLowerStart(l.text)` and `!keepsHyphen(lexicon, lastWord(t without the hyphen), firstWord(l.text))`, the hyphen is removed ("popu-" + "lation" → "population"); in every case `joined` ("self-" + "made" → "self-made", "Anglo-" + "Saxon" → "Anglo-Saxon").
3. Else `t` ends with U+2014 or U+2013 and a letter precedes it: `joined` ("system—" + "which").
4. Else, when `t` ends with `/`, the byte before it is not a space and `l.text` is non-empty: `joined` exactly when the first code point of `l.text` (decoded) is a letter or an ASCII digit ("client/" + "server", web addresses; `client/` + `«server»` keeps its space).
5. Otherwise a space is appended.

Then `off` = the text size (after the space); `maxX1 = max(maxX1, l.x1)`. Runs: when `l` has no run at offset 0 and the paragraph's last run has non-zero flags, `(off, 0)` is appended. Each run `(o, f)` of `l` is appended as `(o + off, f)` unless the paragraph has no run yet and `f == 0`, or `f` equals the paragraph's last run's flags. The line's text is appended and the line recorded.

`endsSentence(s)`: the last byte is `.`, `;` or `,`.

`endsWithFunctionWord(s)`: the word after the last space (or the whole text), `toLowerUtf8`, is one of `to the a an of and or for with in on by at from that as is are и в на с к о что по` (a heading does not end with a word that needs a continuation).

#### `close()` — a paragraph becomes a block

1. Without lines: `flushImages()` and return.
2. Every U+00AD left inside the text was drawn: each becomes `-`, and every run starting after it moves back one byte.
3. **Spans** from the runs, `lastFlags = 0`: a run's flags without `kMono`, plus `kSpanCode` when it had `kMono`; runs at or after the end of the text are skipped; a leading regular run is skipped; a run at the same offset as the last span replaces that span's flags; a run whose flags equal `lastFlags` is skipped (when spans exist); otherwise `Span{o, flags, −1}`. Then trailing spans at or after the end are removed. A style covering the whole paragraph stays.
4. `first` = the first line, `chars = utf8Length(text)`, `size = first.size`, `allBold` = every line has `kSpanBold`, `e = edges(paragraph page, first.col)`, `distinct = (first.flags & kSpanBold) || first.font != bodyFont`.
5. **Title** when: at most 3 lines, `chars <= 160`, the text does not end with `.`, `first` is neither `tabular` nor a list item, `!endsWithFunctionWord(text)`, and (`size >= 1.25 × bodySize`, or `size >= 1.08 × bodySize && distinct && one line && chars <= 100`). `level` by `r = size / bodySize`: `r >= 1.9` → 1, `r >= 1.4` → 2, else 3. Spans are cleared.
6. Else **Subtitle** when: `allBold`, one line, `chars <= 90`, `!endsSentence(text)`, not a list item, not `tabular`. Spans are cleared.
7. Else **Cite** when: `e.known`, `first` is not a list item, at least 2 lines, and every line has `x0 − e.left > 1.6 × its size` and `x1 < e.right − 1.0 × its size` (a quotation indented on both sides; spans are kept).
8. A remaining **Paragraph** of at most 12 code points whose non-space code points (at least 2 of them) are all `*`, `•`, `~`, U+2217, `·` or `#` becomes a **Separator** (`* * *`).
9. `positions += (page, y)`; the block is added; `cur_ = Para{}`; `lastWasCode_ = false`; `flushImages()`.

`emitImage(im, page)`: nothing when `im.image < 0`; else an `Image` block with that image and `positions += (page, im.y0)`.

`flushImages()`: emits the pending pictures in order, clears them, then `flushNotes()`.

`flushNotes()` (nothing when no note is pending): the pending lines are taken; a note block starts at the first line and at every line that `startsNoteMark`; a further line is joined to the current note — when the note ends with `-` (at least 2 bytes), the code point before it is a letter and the line starts lower case, the hyphen is removed and the line appended directly; otherwise with a space. Each note becomes a `Paragraph` block with `notes = true`, no spans, and position `(page, y − size)` of its first line.

#### `run()`

For each page `p`, `textLines` = the page's lines in reading order that are not dropped, not footnotes and not `mono`; `nextIdx = 0`. For each item of the reading order:
1. A line item first updates the look-ahead: `std::find` searches `textLines` from `nextIdx` for this line. Found → `nextIdx` = its index and `next_ = textLines[nextIdx + 1]` when that exists, else null. Not found (a dropped line, a footnote, a code line) → `next_ = nullptr` and `nextIdx` stays, so the search for the following lines goes on after the last one found. `next_page_ = p` in both cases.
2. A picture item: skipped when `image < 0`; emitted at once when no paragraph is open, otherwise queued in `pendingImages_` (placed after the paragraph it interrupts).
3. A dropped line: skipped.
4. A footnote line: queued in `pendingNotes_`; when no paragraph is open and no picture is queued, `flushNotes()` at once.
5. A table row: `close()`; a `TableRow` block with the line's text and, when its first run has `kSpanBold`, the span `{0, kSpanBold, −1}`; position `(p, y − size)`; `lastWasCode_ = false`.
6. A `mono` line (code): `close()`; a `Verse` block with `stanzaStart = !lastWasCode_`; `base = edges.known ? edges.left : l.x0`; `indent = clamp(lround((l.x0 − base) / (0.6 × l.size)), 0, 40)`; the text is `indent` NBSPs (U+00A0, bytes C2 A0) followed by the line's text; one span `{0, kSpanCode, −1}`; position `(p, y − size)`; `lastWasCode_ = true`. Every code line is a block of its own. (`close()` only resets `lastWasCode_` when it closes a paragraph, so consecutive code lines keep `stanzaStart = false`.)
7. Any other line: `lastWasCode_ = false`; when a paragraph is open and `!continues(last line, curPage_, l, p)` → `close()`; when no paragraph is open (now) → `flushImages()`; `append(l, p)`; `curPage_ = p`.

After the last page, `close()`. Page boundaries close nothing by themselves: `continues` decides (its `flowBreak` rules).

### D.16 Pictures

**`bool colorSpaceInfo(pdf::File& file, const Object& csIn, pdf::ImageSpec& spec, int depth = 0)`** — `cs = resolve(csIn)`; false when `depth > 4`. The family name is `cs` itself when a name, the resolved first element when a non-empty array (empty when that is not a name), `DeviceGray` when `cs` is null.

| family | result |
|---|---|
| `DeviceGray`, `CalGray`, `G` | Gray, 1 component |
| `DeviceRGB`, `CalRGB`, `RGB`, `Lab` | Rgb, 3 (Lab samples are shown as RGB) |
| `DeviceCMYK`, `CMYK` | Cmyk, 4 |
| `ICCBased` | `N` of the resolved stream `cs[1]` (default 3; 3 when it is not a dictionary): 1 → the result for a null colour space (Gray); 4 → Cmyk, 4; anything else → Rgb, 3 |
| `Separation`, `DeviceN` | Gray; comps 1 for Separation, `max(1, size of resolved cs[1])` for DeviceN; `invert` is toggled (a tint of 1 is full ink); true only when comps is 1 |
| `Indexed`, `I` | the base `cs[1]` (into a fresh spec, `depth + 1`) must succeed and not be Indexed; `hival = clamp(resolved cs[2] .integer(), 0, 255)`; the lookup `cs[3]` is a string or a stream (decoded; a failure leaves it empty). For each index `0 ..= hival`, the base's components at `index × base.comps` (missing bytes read as 0) become an RGB triplet: Gray `v` (or `255 − v` when the base was inverted) three times; Rgb as they are; Cmyk `(255 − c)(255 − k) / 255` and so on. Then Indexed, 1 component, true |
| anything else (Pattern, a missing name…) | false |

**`bool makeImage(pdf::File& file, const Object& img, ImageData& out, int depth = 0)`** — builds the `ImageData` of an image XObject; false when it cannot be shown:
1. `img` must be a stream with `usableImageFilter(file, img)`.
2. `Width` and `Height` (resolved `integer()`) must be 1–20 000 each with `w × h <= kMaxImagePixels` (50 000 000, `PdfReader.h`; larger pictures are not shown, their RGBA would need 200 MB).
3. `ImageSpec`: `width`, `height`; `bpc = BitsPerComponent.integer(8)`; `ImageMask` true (a `Bool`) → `stencil`, `bpc = 1`, `comps = 1`; a `Decode` array of at least 2 elements whose first value is greater than its second → `invert`.
4. The filter chain from the resolved `Filter` and `DecodeParms` (only these names, not `F`/`DP`), built like `decodeStream`'s; `rawStream(img, data)` (decrypted, still encoded) must succeed.
5. **JPEG**: when the chain contains `DCTDecode`, the filters before it are applied now (`applyFilter(..., kMaxStreamBytes)`; one that fails → false), the chain is cleared (filters after the codec are dropped) and `jpeg = true`.
6. Neither JPEG nor stencil: `colorSpaceInfo(ColorSpace)` must succeed.
7. `bpc` must be 1, 2, 4, 8 or 16.
8. Only at `depth == 0`: an `SMask` stream goes through `makeImage(..., depth + 1)`; on success its bytes are the mask. (`/Mask` is ignored.)
9. A plain JPEG picture stays a JPEG file — only when `jpeg`, the mask is empty **and** `depth == 0`: `probeImageSize(data)` must succeed; `mime = "image/jpeg"`, `bytes` = the JPEG, `width/height` = the probed size. A soft mask is always a container, also when it is a JPEG, because the picture's decoder reads its mask as one (A.12).
10. Otherwise a container (A.12): `jpeg`, `filters` = the remaining chain (all filters for samples, none for a JPEG), `data`, `mask`; `mime = "application/x-lanternleaf-pdf-image"`, `width/height` = the PDF's `Width`/`Height`. The samples stay compressed until the picture is shown.

### D.17 The outline

```cpp
struct OutlineItem {
  std::string title;
  int depth = 0;
  int page = -1;
  float y = 0;  // page space; 0 = top
};
```

`class Outline` (file, content reader; `namesLoaded_`, `names_`: name → resolved destination):
- `read()`: `ol = get(Root, "Outlines")` must be a dictionary; `walk(get(ol, "First"), ol's direct First entry or null, 0, items, seen)`.
- `walk(node, ref, depth, ...)` — a loop over siblings while `node` is a dictionary, fewer than 20 000 items exist and `depth < 16`: a `ref` that is a reference already seen ends the walk (cycles); `title = textToUtf8(Title)`; `dest = Dest`, or, without one, `A`'s `D` when `A` is a dictionary whose `S` is the name `GoTo`; `resolveDest(dest)`; the item is added only when the title is non-empty (its children are walked anyway); a direct `First` entry → `walk(resolve(First), First, depth + 1)`; no direct `Next` → return; else `ref = Next`, `node = resolve(Next)`.
- `resolveDest(dest, it)`: up to 4 times while `dest` is a name, a string or a dictionary: a dictionary is replaced by its `D`; a name (PDF 1.1) or a string by `named(dest.s)`. Then `dest` must be a non-empty array. Element 0 (direct): a reference → `page = pageIndexOf(number)`; an `Int` → used as the page index. `page < 0` → return. `kind` = resolved element 1: `XYZ` with at least 4 elements → `top` = element 3; `FitH`/`FitBH` with at least 3 → element 2; `FitR` with at least 6 → element 5 (each resolved `num(−1)`). When `top >= 0` and `userToPage(page, 0, top)` succeeds, `y = max(0, py)`. Other kinds, a null or negative top → `y = 0`.
- `named(name)`: loads the names once, then the stored destination or null. `loadNames()`: every entry of the catalog's `Dests` dictionary (key without `/`, value resolved), then the `Dests` name tree of the catalog's `Names` dictionary: `walkTree(node, depth)` stops at depth > 32 or when more than 200 000 names are stored; its `Names` array gives (string key, resolved value) pairs; `Kids` are walked in order, a reference already seen is skipped. `emplace` keeps the first definition of a name.

`std::string matchKey(std::string_view s)`: the letters and digits of `s`, lower-cased (`toLowerCp`), everything else dropped.

### D.18 Metadata

`std::string xmpValue(std::string_view xmp, std::string_view tag)`:
1. `a` = the first `<` + tag; `b` = the first `</` + tag after it; either missing → empty. `inner = xmp[a:b]`.
2. With an `<rdf:li` in `inner`: the text from after the next `>` to the following `</rdf:li` (when both are found; otherwise `inner` stays the whole element, tags included). Without one: the text after the first `>` (empty when there is none).
3. Entities: an `&` with a `;` at most 6 bytes later is replaced by `&`, `<`, `>`, `"` or `'` for `amp`, `lt`, `gt`, `quot`, `apos`, and **dropped** for any other name (numeric references such as `&#233;` disappear); other bytes are kept.
4. `collapseSpaces`.

`bool usableTitle(const std::string& t)`: false when empty; with `l = toLowerUtf8(t)`, false when `l` ends with `.doc`, `.pdf`, `.indd`, `.qxd`, `.tex`, `.dvi`, `.rtf`, `.odt`, `.pages` or `.ps` (and is longer than that suffix), starts with `microsoft word` or `untitled-`, equals `untitled`, `title`, `unknown`, `document` or `layout 1`, or is shorter than 2 bytes; otherwise true.

**`readMeta(file, meta)`**:
1. `info = get(trailer, "Info")`; when it is a dictionary:
   - `title = textToUtf8(Title)`; when `usableTitle` → `meta.title`;
   - `author = textToUtf8(Author)`; unless empty or (lower-cased) `unknown` or `author`, it is split at `;`, each part `trimCopy`ed, the non-empty parts appended to `meta.authors`;
   - `subject = textToUtf8(Subject)`; non-empty → `meta.annotation`.
2. `root = resolve(trailer["Root"])`; when it is a dictionary:
   - `lang = textToUtf8(Lang)`; with at least 2 bytes, `meta.lang = toLowerUtf8(first 2 bytes)` (`en-US` → `en`);
   - when the title or the authors are still empty and `Metadata` is a stream that decodes with `maxOut` 4 MiB (`4 * 1024 * 1024`): an empty title takes `xmpValue(xmp, "dc:title")` when `usableTitle`; empty authors take `xmpValue(xmp, "dc:creator")` as one author when non-empty.

**`detectLanguage(doc)`**: only when `meta.lang` is empty. Counts Cyrillic (`isCyrillicCp`) and Latin (`isLatinLetterCp`) letters over the blocks' texts, stopping at 20 000 counted letters; with any letter counted, `lang = cyr > lat ? "ru" : "en"`.

### D.19 Public functions

**`bool looksLikePdf(std::string_view head)`**: `%PDF-` occurs in the first `min(size, 1024)` bytes.

Damaged files are handled where they are read; what remains — a file whose objects or pictures do not fit in memory — must not end the app either, so the three public functions below never let an exception out.

**`bool parsePdf(raw, doc, fileStem, error, opt)`**: returns `parseDocument(raw, doc, fileStem, error, opt)` inside `try`; on a `std::exception`: `doc = Document{}`, `*error = "The PDF file is too large or too damaged to open."` (when `error` is non-null), false.

**`bool parseDocument(raw, doc, fileStem, error, opt)`** (file-local) — every failure writes `*error` (when non-null) and returns false:
1. `doc = Document{}`.
2. `pdf::File file; file.open(raw, &err)`; failure → its message (A.7, B.4).
3. `pdf::ContentReader cr(file)`; `n = cr.pageCount()`; `n <= 0` → `"The PDF file has no pages."`.
4. `readMeta(file, doc.meta)`; `guessMetaFromFileStem(fileStem, doc.meta)` (fills only what is still empty, 04 B.12); `meta.format = "PDF"`; `meta.encoding = "PDF " + file.version()` (e.g. `"PDF 1.7"`).
5. **Pages**, in order, with one reused `PageContent`: `cr.readPage(p, pc, opt.loadImages)` (its result is ignored), `analyzePage(pc, cr.fonts(), pages[p])`. Then for each `PageImage` of the page, in order:
   - `imagePages[obj]` counts the pages it is drawn on (once per page, objects with a number only);
   - the picture is converted now, because `pc` is overwritten by the next page: `key = obj` when non-zero; a picture without an object number is a picture of its own, with the key `−(++anonymous)` (a counter starting at 0, so every such key is used once); an unknown key runs `makeImage(file, pc.images[src].image, data)`; on success `data.id = "pdf" + std::to_string(obj)`, or `"pdf-" + std::to_string(anonymous)` without an object number, and it is appended to `doc.images`; the key maps to the new index or −1;
   - `im.image` = the mapped index.
6. **Decoration**: `decoration = max(4, n / 10)`; every picture with an object number drawn on at least that many pages gets `image = −1` (logos, ornaments).
7. `st0 = documentStats(pages)`; `dropRepeatedLines(pages, st0)`; `st = documentStats(pages)` (now without the dropped lines); `columnEdges(pages, st, edges)`; `paragraphStyle(pages, edges, st)`; `markFootnotes(pages, st)`; the lexicon from every non-dropped line.
8. **Cover**: on page 0, `chars` = the bytes of its non-dropped lines; `big` = the largest picture with `image >= 0` covering at least `0.45 ×` the page area (strictly larger wins). With `big` and `chars < 400`: `doc.coverImage = big.image`; an `Image` block for it is the first block; every line of page 0 is dropped and every picture of page 0 gets `image = −1` (the page is the cover).
9. `dropBackgrounds(pages)`.
10. `Assembler(doc, pages, st, edges, lex)`; with a cover, `positions` starts with `(0, 0)`; `run()`; `pos` = its positions (one per block).
11. **Labels of drawings**: the vector graphics of a figure are not shown, so its text labels — short fragments just before a caption — would only be noise. For each block `k >= 1` that is not an `Image` and `startsCaption(text)`: walk back from `j = k` while `j > 0` and block `j − 1` is not an `Image`, not a `Verse`, not `notes` and not a `Title` of level 1 or 2, has at most 40 code points, at most 6 words (spaces + 1) and does not end with `.`, `:`, `?`, `!`, `;` or `,`. When the walk stopped at an `Image` (`j > 0` and block `j − 1` is an `Image`), nothing happens (a picture's own caption). Otherwise, when `k − j >= 2`, blocks `j .. k − 1` are marked. Marked blocks are removed together with their positions.
12. **Table of contents**. `items = Outline(file, cr).read()`; `firstText = cover ? 1 : 0`.
    - `pageFirst[p]` (for `p` in `0 .. n`, initialised to the block count): the first block whose position's page is `p` (pages clamped to `0 .. n − 1`), then from the last page down `pageFirst[p] = min(pageFirst[p], pageFirst[p + 1])`. Blocks follow the pages, but notes and queued pictures can come later than their page.
    - `blockAt(page, y)`: from `pageFirst[clamp(page, 0, n − 1)]` on, the first block that belongs to a later page, or belongs to that page with position `y >= y − 4` (destination minus 4 points), is returned; blocks of earlier pages are passed over; nothing → −1.
    - `confirmed` flags; `demoteHeadingRuns()`: every run of 3 or more consecutive unconfirmed `Title`/`Subtitle` blocks of the same type and level becomes `Paragraph` with level 0 (the lines of a box; a title page with title, subtitle and author has different levels). Their spans were cleared in `close`.
    - **With outline items**: for each item with `page >= 0`: `bi = blockAt(page, y)`, skipped when −1. `key = matchKey(title)`. The heading may be further down the page when the destination is its top (below a picture, a quotation, the rows of an index), so the rest of the page is searched, up to 64 blocks: among blocks `bi .. bi + 63` (skipping `Image` blocks, and stopping at the first block of another page after `bi`), the first whose `bk = matchKey(text)` is non-empty, prefix-related with `key` (either starts with the other) and `min(len) × 2 >= max(len)` (byte lengths) becomes `bi`. Then block `bi` is confirmed as a heading when, in addition to those conditions, `len(bk) <= len(key) + 12`, it is not an `Image` and has at most 200 code points: `type = Title`, `level = min(depth + 1, 6)`, spans cleared, `confirmed`. Independently, an item of depth 0 gives block `bi` `pageBreakBefore` when `bi > firstText`. A `TocEntry{outline title, bi, depth + 1}` is added for every such item, confirmed or not. Afterwards `demoteHeadingRuns()`.
    - **Without outline**: `demoteHeadingRuns()` first; then every `Title` block becomes a `TocEntry{text, index, level}`, and a level-1 title after `firstText` gets `pageBreakBefore`.
    - Headings the outline did not confirm keep their size-based level (1–3).
13. With a cover and more than one block, block 1 gets `pageBreakBefore`.
14. `detectLanguage(doc)`; `doc.finalize()` (03 § 4.7: character offsets, the TOC sorted stably by block, web addresses linked).
15. No blocks → `"No text or pictures were found in this PDF file (it may consist of scanned pages in a format Lanternleaf cannot show)."`. Otherwise true; `*error` is not touched.

**`bool parsePdfMeta(head, tail, fileSize, meta)`**: returns `readDocumentMeta(head, tail, fileSize, meta)` inside `try`; on a `std::exception`: `meta = BookMeta{}`, false.

**`bool readDocumentMeta(head, tail, fileSize, meta)`** (file-local):
1. `meta = BookMeta{}`; `whole = head.size() >= fileSize`.
2. `file.open(head)` when whole, else `file.openPartial(head, tail, fileSize)`; failure → false.
3. When the trailer's direct `Info` is a reference whose object does not load as a dictionary: false unless `whole` (the information dictionary lies outside the bytes that were read).
4. `readMeta(file, meta)`; `format = "PDF"`; `encoding = "PDF " + version`; true. (No file-stem guess here; `loadBookMeta` does that.)

**`void pdfExtractText(raw, text, meta, fileStem)`**: `text` cleared; when `parsePdf(raw, doc, fileStem, &err, {loadImages = false})` succeeds, every block with non-empty text is appended followed by `'\n'` (one paragraph per line) — inside `try`; on a `std::exception` `text` is cleared. In every case, `*meta = doc.meta` when `meta` is non-null (after a failure that is whatever `parseDocument` had filled in, or an empty `BookMeta` after an exception).

---

## Part E — Tests in `tests/core_tests.cpp` that constrain these files

`testPdf` (group `pdf`) builds its PDFs in memory with a small `PdfBuilder` (numbered objects, a classic cross-reference table) and a test font whose glyphs are all 500/1000 wide (`/FirstChar 32 /LastChar 126`, WinAnsiEncoding), so that lines of 50 characters at 10 pt are full lines of a 300-point page.

- **Primitives**: `md5("abc")` = `900150983cd24fb0d6963f7d28e17f72`; `md5` of 1000 × `a` = `cabe45dcc9ae5b66ba86600cca6b8ba8`; `sha256("abc")` = `ba7816bf…20015ad`; `sha256` of 1000 × `a` = `41edece4…b9737ea3`; `sha384("abc")`; `sha512` of 1000 × `a`; `rc4("Key", "Plaintext")` = `bbf316e8d940af0ad3`; AES-128 of `00112233…eeff` with key `000102…0f` and a zero IV = `69c4e0d86a7b0430d8cdb78070b4c55a` (FIPS 197 C.1); AES-256 with key `000102…1f` = `8ea2b7ca516745bfeafc49904b496089`, and `aesCbcDecrypt` gives the plaintext back.
- **Lexer**: `<< /Na#20me (a\(b\)c\101\` + LF + `) /Hex <48 65 6C6> /Arr [-.5 4. --3 7 0 R (x)] /K true /N null >>` → key `Na me` = `a(b)cA` (the escaped line end disappears), `Hex` = `Hel` + 0x60 (odd digit), `Arr` = 5 elements −0.5, 4.0, −3, a reference to 7, `x`; `K` a `Bool` true; `N` null.
- **Filters**: Flate of `"Hello, PDF!"`; `Fl` of 100 000 bytes through a 1 MiB limit (the pending-output rule of A.6); `ASCIIHexDecode` `"48 65 6c 6C6F7>"` → `Hellop`; `ASCII85Decode` `"<~9jqo^~>"` → `Man `; `RunLengthDecode` `\x02abc\xFEz\x80` → `abczzz`; `LZWDecode` `800b6050220c0c8501` → `-----A---B` (ISO 32000-1 § 7.4.4.2); Flate with predictor 12, 3 columns, rows *None* `abc` and *Up* `01 01 01` → `abcbcd`; the same 8 bytes with `Columns` 2²⁴ (a row longer than the stream) → an output no larger than the input (A.6); `DCTDecode` → false.
- **Strings and names**: `textToUtf8("\x93fi\x94ne")` → `ﬁfiﬂne` (PDFDocEncoding 0x93/0x94 are the ligatures); UTF-16BE with BOM `04 1F 04 40 00 20 00 21` → `Пр !`; `glyphNameToUtf8`: `afii10017` → `А`, `f_f_i` → `ffi`, `uni0416.sc` → `Ж`, `g123` → empty.
- **The two-page book** (`pdfTestBook`): running heads `TEST BOOK` with the page number at the top right of both pages (8 pt), a 16 pt `Chapter One`, a hyphenated line end, a paragraph that runs over the page break, `self-` + `made`, two bullet items, an outline with `Chapter One` (page 1) and its child `Page two` (page 2), and `/Info` with a UTF-16 `Test Book` and `Jane Doe`. `checkTestBook` requires: format `PDF`, title `Test Book`, one author `Jane Doe`, exactly 5 blocks — `Title` level 1 `Chapter One`; `The first paragraph of this book has many words to fill several lines, and this one ends with a population broken by hyphenation.`; `A second paragraph begins here, and its final line on the first page is full, and so the text runs on to the next page; the next line carries on with no break. A compound word broken at its hyphen: self-made keeps the hyphen in the joined text of lines. That is all.`; `• first item`; `• second item` — and 2 TOC entries, `Chapter One` at block 0 level 1 and `Page two` at level 2. The running heads go because each page's `TEST BOOK` and number form one tabular line whose last word is a page number (`folioHead`), not because they repeat.
- **Repair**: the same book with every cross-reference offset 3 bytes too large must give the same document (the objects are found by scanning, A.10).
- **Metadata from parts**: `parsePdfMeta(first 64 bytes, the bytes from size / 3 to the end, size)` → true with title `Test Book` (the cross-reference table, trailer and `/Info` lie in the tail).
- **Text extraction**: `pdfExtractText` contains `a population broken`; `meta.authorsJoined() == "Jane Doe"`.
- **Compressed file** (`pdfCompressed`): a cross-reference stream (`/W [1 4 2]`, PNG *Up* predictor 12 with 7 columns), an object stream holding the Type 0 font and its CIDFont, a Flate content stream, `Identity-H` with a ToUnicode CMap of one bfrange `<0001> <0003> <0041>` and one bfchar `<0004> <0020>`; shown codes `1 2 3 4 1 2` → exactly one block `ABC AB`; title `Compressed Title` and author `Author` from the file stem `Author - Compressed Title`. `pdfCompressed(true)` gives the cross-reference stream an indirect `/Length` (object 10): `File::open` succeeds with `!repaired()` and version `1.5`; the same `File` then opens the test book with `!repaired()` and version `1.4` (every file starts afresh, A.7); `parsePdf` gives the one block `ABC AB`.
- **Picture** (`pdfWithImage`): a 2×2 DeviceRGB Flate image drawn above a line of text → 2 blocks, `Image` first, then `A picture above.`; one `ImageData` of 2×2 (a container); `decodeImageRgba` gives 16 bytes with red, green, blue and white pixels (`rgba[0] = 255`, `rgba[1] = 0`, `rgba[5] = 255`, `rgba[10] = 255`, `rgba[12] = 255`).
- **Encryption**: RC4 40-bit (V 1, R 2), AES-128 (V 4, R 4, `AESV2`) and AES-256 (V 5, R 5, `AESV3`), all with the empty user password and an owner password set → each opens with 2 blocks `Secret Chapter` and `Only readers with the key can see this line.` and the encrypted `/Info` title `Locked Book`. `pdfEncrypted(1, true)` stores the content stream unencrypted with `/Filter [/Crypt] /DecodeParms [<< /Name /Identity >>]` → 2 blocks, the first `Secret Chapter` (A.11).
- **Damaged content** (`pdfDamagedContent`): the page runs `q /Fm1 Do Q`, where the form's content is `/Artifact BMC q Q Q Q` (an artifact left open and more `Q` than `q`), then two text lines; the Type 0 font's ToUnicode CMap has a block of 3 bfrange entries `<0001> <0003> [<0041> <0042> <0043>]`, `<0004> <0004> <0020>`, `<0005> <0006> <0058>` and a block `<FFFFFF00> <FFFFFFFF> <0041>`. → exactly 2 blocks, `ABC XY` and `after the form` (the artifact ends with the form, the extra `Q` do not touch the page's state, the array range and the entries after it are read, the last range ends).
- **Tables** (`pdfTable`, two pages, lines 14 points apart, the second column 120 points right of the first): page 1 `Name`/`Value`, `alpha`/`red`, `beta`/`dark green` (values in lower case) → 3 `TableRow` blocks `Name | Value`, `alpha | red`, `beta | dark green`; page 2 `Customer`/`Rider request and pickup` over `Journey`/`continue the trust.` → one `TableRow` `Customer Journey | Rider request and pickup continue the trust.` (a row whose cells go on over two lines). 4 blocks in all (D.6).
- **Not readable**: `parsePdf("%PDF-1.4\ngarbage")` → false with a non-empty message (`"The PDF file is damaged: its document catalog was not found."`).
- The group prints `  pdf: 5 blocks, 2 contents entries, repaired 5 blocks, encrypted files opened 3 of 3`; with the layout tests the program ends with `840 checks, 0 failures` (the expected test output is listed in spec 13).

---

## Checklist

Each item was checked against a build of the sources this file describes. `F1` is a font with every code 0.5 em wide and WinAnsiEncoding; pages are 300 × 400 points; texts are shown with `BT /F1 10 Tf x y Td (…) Tj ET` unless stated otherwise.

**Reader**
1. Tokens: `>` → keyword `>>`; `)` → keyword `)`; `1.2.3` → keyword; `+-5` → `Int` −5; `.5` and `4.` → `Real`; `99999999999999999999` → `Int` 999999999999999999.
2. `<< 1 /A 2 /B ] /C 3 >>` → `A` = 2, `B` = the keyword `]`, `C` = 3.
3. `textToUtf8("  a\tb \x01 c  ")` → `"a b c"`; `textToUtf8("  a\tb \x01 c\n ", false)` → `"  a\tb  c\n "` (only the `\x01` is dropped); `"\xC3\xA9t\xC3\xA9"` → `été` (UTF-8 without BOM); UTF-16 `FE FF 00 1B 00 65 00 6E 00 1B 00 41` → `A` (the language escape is dropped).
4. Flate: raw deflate data without a zlib header decode; a zlib stream whose Adler-32 is missing decodes; a stream cut short keeps the bytes decoded so far; `maxOut` 1000 on 300 000 bytes gives exactly 1000.
5. RunLength `81 'a' 81 'b'` with `maxOut` 10 → 128 bytes (the first run is not cut). ASCIIHex `"4"` → one byte 0x40.
6. A cross-reference stream whose `/Length` is an indirect reference opens without a repair, `repaired()` false: its data end at `endstream`. The same with a direct `/Length`.
7. `"hello"` → `"This is not a PDF file."`; `"%PDF-1.4\ngarbage"` → `"The PDF file is damaged: its document catalog was not found."`; `parsePdfMeta` with only the last 200 bytes of the test book as the tail → false (the cross-reference table lies before them).

**Layout and assembly**
8. Three rows `Name`/`Value`, `alpha`/`1`, `beta`/`2` at x 20 and 150, 13 points apart → three `TableRow` blocks `Name | Value`, `alpha | 1`, `beta | 2`, no spans. The same layout with `apple`/`red`, `banana`/`yellow`, `cherry`/`dark red` → three rows `apple | red`, `banana | yellow`, `cherry | dark red` (the one-word text above never carries on in the last column, D.6).
9. Rows with larger gaps: `Name`/`Value` at y 350, `more` at 337, `alpha`/`1` at 315, and `2` at x 150 plus `x` at x 200 at 293 → three rows `Name more | Value`, `alpha | 1`, ` | 2 | x` (leading space).
10. `Some words of a sentence end in a quote»` followed by `– the next line starts with a dash` and `and then it goes on here` (13 points apart) → two paragraphs, `Some words of a sentence end in a quote»` and `– the next line starts with a dash and then it goes on here`; the same with a final `.` instead of `»`.
11. A ToUnicode CMap `2 beginbfrange <01> <02> [<0041> <0042>] <03> <03> <0043> endbfrange 1 beginbfchar <04> <0044> endbfchar` on a simple font, showing codes `01 02 03 04` and `xyz` → `ABCDxyz`.
12. `a long line of words that ends in client/` + `«server» and more words follow here` → `…client/ «server» and more…` (the space stays); `…ends in system—` + `which goes on…` → `…system—which goes on…`.
13. After four body lines, Courier lines `int main() {` at x 20, `return 0;` at x 32 and `}` at x 20 → three `Verse` blocks with span `{0, 32, −1}`: `stanzaStart` true, false, false; the second is two U+00A0 followed by `return 0;` (12 / (0.6 × 10) = 2 NBSPs).
14. `Chapter Two` at 20 pt and `A Smaller Heading` at 16 pt over 10 pt body text, no outline → `Title` level 1 and level 2, TOC `{Chapter Two, 0, 1}`, `{A Smaller Heading, 1, 2}`, no page break (block 0); `A bold line` in `Helvetica-Bold` 10 pt → `Subtitle`; `* * *` on its own → `Separator`.
15. Two 8 pt lines at the foot (`1 The footnote text …`, `continued on a second line.`) below 10 pt text → one `Paragraph` with `notes = true`, `1 The footnote text that is long enough to be one line, continued on a second line.`, placed after the paragraph above it.
16. `E = mc` + `2` at 6 pt with rise 5 + ` is famous.` → `E = mc2 is famous.` with `kSpanSup` from the `2` up to the `i` of `is` (the space after the superscript belongs to its run).
17. `/Span << /ActualText (fi) >> BDC (X) Tj EMC (nd) Tj` → `find`; `/ActualText ( )` over `Chapter` → ignored, `Chapter word`; `/Artifact BMC … (17) Tj … EMC` → no text.
18. Six lines at x 20 and six at x 170 on the same rows (`left column words k`, `right column text k`) → the left column first, then the right one (here one paragraph, the lines being full).
19. A 40 pt `T` beside `he first line beside the drop cap goes on` (x 45) and the next line, then a line at x 20 → `The first line beside the drop cap goes on and the second line is also beside it now the third line is back at the left margin of`.
20. `x axis`, `y axis`, `origin` as separate short blocks just before `Figure 3 The drawing.` → removed; the caption stays.
21. The test book: TOC `{Chapter One, 0, 1}`, `{Page two, 3, 2}` (`Page two` points at `• first item`, the first block of page 2 at the destination, and is not confirmed as a heading); `meta.lang` `en`, `meta.encoding` `PDF 1.4`.
22. A page `/Fm1 Do BT … (After the form.) Tj ET` whose form content is just `Q Q` → one block `After the form.` (the form's `Q` stop at its floor).
23. Evenly spaced rows (14 points) `Customer`/`Rider request and pickup` over `Journey`/`continue the trust.`, the columns at x 30 and 150 → one row `Customer Journey | Rider request and pickup continue the trust.`.
24. Evenly spaced rows (13 points) `Name`/`Description`, `alpha`/`the first one of`, `them all` (second column only), `beta`/`Second.`, the columns at x 20 and 150 → 2 rows, `Name alpha | Description the first one them all | of` and `beta | Second.`. With this font's 5-point word spaces the stretch between `one` (ends at 215) and `of` (starts at 220) is wide enough (≥ 3 points) to start a third column at 219.75, so column 1 is not the last one: its room ends at 216.75, `Description` ends at 205, and `the` (15 points) does not fit after it — `alpha`'s line carries on and joins the first row.
