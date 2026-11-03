# 04 — Book formats: FB2, TXT, zip and the book loader

This file specifies three translation units that turn the bytes of a book file into the in-memory model. `src/core/Fb2Parser.cpp` converts FictionBook 2 into a `Document`, and also provides a metadata fast path and plain-text extraction. `src/core/TxtParser.cpp` converts plain text into a `Document`, rebuilding paragraphs, headings and typography, and guesses title and author from the file name. `src/core/BookLoader.cpp` covers UTF-8 paths, file-name rules, reading files, unpacking zip archives with miniz, the `loadBook*` entry points and `bookFingerprint`. The verbatim headers `Fb2Parser.h`, `TxtParser.h` and `BookLoader.h` hold the declarations, and `Document.h` holds the data model; this file does not restate them. The helpers these files call (`Unicode.h`, `Encoding.h`, `XmlReader.h` and `Document::finalize()`) are specified in `03-core-foundation.md`. `probeImageSize` is declared in `ImageCodec.h`. All code lives in namespace `ll`, and a helper called "file-local" sits in an unnamed namespace in its `.cpp`. Unless stated otherwise, string comparisons are exact and case-sensitive on bytes, a "size" or "length" is in bytes, and a length "in code points" means `utf8Length`.

---

## 0. Behaviour of shared helpers that the results depend on

These helpers are specified in 03. They are summarised here only because the rules below depend on them.

- `isSpaceCp(c)` is true for U+0009–U+000D, U+0020, U+1680, U+2000–U+200A except U+2007, U+2028, U+2029, U+205F and U+3000. U+00A0 (NBSP), U+2007 and U+202F are **not** white space, so every white-space normalisation below keeps them.
- `trimView` / `trimCopy` remove only ASCII space, tab, CR, LF and the two-byte NBSP (`C2 A0`), at both ends.
- `collapseSpaces` replaces every run of `isSpaceCp` characters with one U+0020 and removes leading and trailing runs. NBSP is left alone.
- `toLowerUtf8` lowercases one code point at a time: ASCII, Latin-1, Latin Extended-A, Greek and Cyrillic, including `Ё`→`ё`.
- `endsWithNoCase` tests a suffix case-insensitively for ASCII letters only.
- `utf8Decode` never stalls. Every buffer parsed below is valid UTF-8, because `bytesToUtf8` guarantees that.
- `XmlReader`:
  - It reports local names (`l:href` → `href`, `fb:p` → `p`).
  - A self-closing tag produces a `StartTag` and then an `EndTag` with the same name.
  - `attr(local)` returns the first attribute with that local name, or an empty view.
  - `text()` is entity-decoded; CDATA is passed through verbatim.
  - Comments, processing instructions and DOCTYPE produce no tokens.
  - Malformed markup never stops it.
  - The views returned by `name()` point into the UTF-8 buffer, which outlives every use below.
- `bytesToUtf8(bytes, hint, used)` chooses the charset in this order:
  1. A BOM wins and is stripped.
  2. Otherwise a non-`Unknown` hint is used. A `Utf8` hint is re-checked on the first 512 KiB and replaced by detection when `errors > 0 && multi < errors * 50`.
  3. Otherwise `detectCharset` decides.
- `charsetName` returns `"UTF-8"`, `"UTF-16LE"`, `"UTF-16BE"`, `"windows-1251"`, `"KOI8-R"`, `"CP866"`, `"ISO-8859-5"`, `"windows-1252"` or `"unknown"`.
- Both parsers call `Document::finalize()` as their last step. It fills `charStart`/`totalChars`, sorts the TOC stably by block, and turns web addresses written as plain text into links.

---

## Part A — `src/core/Fb2Parser.cpp`

### A.1 Purpose and includes

Includes: `core/Fb2Parser.h`, `<algorithm>`, `<array>`, `<cstdlib>`, `<unordered_map>`, `core/ImageCodec.h`, `core/Unicode.h`, `core/XmlReader.h`.

A file-local state machine, `Fb2Builder`, makes one streaming pass over the XmlReader tokens. It fills a `Document`, or only a `BookMeta` in "meta only" mode. Four public functions use it: `fb2ToUtf8`, `parseFb2`, `parseFb2Meta` and `fb2ExtractText`. `fb2ExtractText` also has its own small token loop.

### A.2 File-local helpers

#### `void base64Decode(std::string_view in, std::vector<unsigned char>& out)`

The decoding table is a function-local static `std::array<signed char, 256>`, built once:
- every entry is −1, except:
- `'A'..'Z'` → 0..25, `'a'..'z'` → 26..51, `'0'..'9'` → 52..61;
- `'+'` → 62 and `'/'` → 63;
- the URL-safe variants `'-'` → 62 and `'_'` → 63.

```
out.clear(); out.reserve(in.size() * 3 / 4)
acc: uint32_t = 0; bits: int = 0
for each byte c of in:
  v = table[c]
  if v < 0:
    if c == '=': break          // the first '=' ends decoding, even in the middle of the data
    continue                    // white space and any other garbage are skipped
  acc = (acc << 6) | v; bits += 6
  if bits >= 8: bits -= 8; out.push_back((acc >> bits) & 0xFF)
```
Bits left over at the end (fewer than 8) are discarded.

#### `std::string_view findDeclaredEncoding(std::string_view raw)`

Only the first `min(raw.size(), 512)` bytes (`head`) are searched.
1. `decl = head.find("<?xml")`. If not found, return empty.
2. `end = head.find("?>", decl)`. If not found, `end = head.size()`.
3. `d = head.substr(decl, end - decl)`; `e = d.find("encoding")`. If not found, return empty.
4. `q = d.find_first_of("\"'", e)`: the first double or single quote at or after `encoding`. If none, return empty.
5. `q2 = d.find(d[q], q + 1)`: the next occurrence of the same quote character. If none, return empty.
6. Return `d.substr(q + 1, q2 - q - 1)`: the raw bytes between the quotes, untrimmed.

The search is case-sensitive and runs on raw bytes, so it never finds a declaration in UTF-16 data.

#### `std::string stripHash(std::string_view href)`

Applies `trimView`. If the result is non-empty and starts with `'#'`, that one byte is removed. The rest is returned as a string without trimming again.

#### `bool isAllSpace(std::string_view t)`

Returns true when every code point is `isSpaceCp`. Empty input returns true; any NBSP makes the result false.

#### `bool isSeparatorText(std::string_view t)` — FB2 scene-break detection

```
if t.empty() || t.size() > 40: return false
marks = 0
for each code point c of t:
  if c is U+0020, U+00A0, U+2009 or U+202F: continue          // ignored
  if c is in FB2_MARKS: ++marks; continue
  return false
if marks >= 3: return true
return marks >= 1 && t contains no byte 'x' && t contains no byte 'X'
       && utf8Length(t) <= 3 && marks == utf8Length(t) && marks >= 2
```
`FB2_MARKS` = `*`, `~`, `#`, U+2022 `•`, U+2042 `⁂`, U+2217 `∗`, U+2014 `—`, `-`, U+2013 `–`, U+00B7 `·`, `x`, `X`, U+0445 `х` (Cyrillic small ha).

What this means:
- Three or more marks always qualify, with or without spaces. This includes `x x x`, `XXX`, `ххх` and `---`.
- With fewer than three marks, the text qualifies only if it is exactly two marks and nothing else, and neither mark is an ASCII `x`/`X`:
  - Qualify: `**`, `——`, `хх` (Cyrillic).
  - Do not qualify: `* *`, `xx`, `—`, `*`.

#### `bool isTextBlockTag(std::string_view n)`

Used only by `fb2ExtractText`. It is true for exactly these local names:
```
p v title subtitle section epigraph text-author empty-line stanza poem cite tr td th
book-title first-name middle-name last-name nickname author annotation date body sequence
```

### A.3 `Fb2Builder`: construction, state and the token loop

`Fb2Builder(Document* doc, BookMeta& meta, bool metaOnly, bool loadImages)` stores its four arguments. `doc_` may be null. `meta_` is a reference, and the builder writes to it directly. The callers are:
- `parseFb2`: `(&doc, doc.meta, false, opt.loadImages)`.
- `parseFb2Meta` and `fb2ExtractText`: `(nullptr, meta, true, false)`.

The state, with its exact initial values:

```cpp
struct StyleEntry { std::string_view tag; uint8_t prevFlags; int32_t prevLink; };

// description
bool inDescription_ = false, inTitleInfo_ = false, inAuthor_ = false, inCoverpage_ = false;
bool inMetaAnnotation_ = false;
std::string first_, middle_, last_, nick_, genre_, coverId_;
std::string* capture_ = nullptr;        // where description text currently goes
std::string_view captureTag_;           // element whose end tag stops the capture
// body
int bodyCount_ = 0;
bool inBody_ = false, notesBody_ = false;
int sectionDepth_ = 0, epigraphDepth_ = 0, citeDepth_ = 0, poemDepth_ = 0, annotationDepth_ = 0, tableDepth_ = 0;
bool inTitle_ = false, poemTitle_ = false, stanzaFirst_ = false, pendingPageBreak_ = false;
int titleFirstBlock_ = -1;
int cellIndex_ = 0;
std::vector<std::string> sectionIds_;   // one entry per open <section>; "" when it has no id
std::vector<std::string> pendingIds_;   // ids waiting for the next block
// current paragraph
bool inPara_ = false, lastSpace_ = true;
Block cur_;
std::vector<StyleEntry> styleStack_;
size_t paraStyleBase_ = 0;
uint8_t flags_ = 0;                     // SpanFlag bits in effect
int32_t link_ = -1;                     // Document::links index in effect
// binaries
bool inBinary_ = false;
std::string binId_, binType_, binData_;
std::unordered_map<std::string, int> imageIdx_;   // image id -> Document::images index
```

`run(XmlReader& r)`, verbatim:

```cpp
for (;;) {
  const XmlReader::Token tok = r.next();
  if (tok == XmlReader::Token::End) break;
  if (tok == XmlReader::Token::StartTag) {
    if (!onStart(r)) break;
  } else if (tok == XmlReader::Token::EndTag) {
    if (!onEnd(r.name())) break;
  } else {
    onText(r.text());
  }
}
finish();
```

`onStart(r)` runs these checks in order, with `n = r.name()`:
1. If `inBinary_`: ignore the tag and return true.
2. If `n == "description"`: set `inDescription_ = true` and return true. This is recognised anywhere, even inside a body.
3. If `inDescription_`: call `startDescriptionTag(r)` and return true.
4. If `n == "body"`: return **false** (stop parsing) when `metaOnly_ || !doc_`; otherwise call `startBody(r)` and return true.
5. If `n == "binary"`: return **false** when `metaOnly_ || !doc_`. Otherwise run `closePara()`, set `inBinary_ = true`, `binId_ = attr("id")`, `binType_ = attr("content-type")`, clear `binData_`, and return true.
6. If `!inBody_ || !doc_`: ignore the tag and return true. This covers the `FictionBook` root and anything between bodies.
7. Otherwise call `startBodyTag(r, n)` and return true.

`onEnd(n)`, in order:
1. If `inBinary_`: call `finishBinary()` when `n == "binary"`; return true either way. Every other end tag inside a binary is ignored.
2. If `n == "description"`:
   - call `endCapture()`;
   - set `inDescription_ = false` and `inTitleInfo_ = inAuthor_ = inCoverpage_ = inMetaAnnotation_ = false`;
   - return `!metaOnly_`. This is where meta-only parsing stops.
3. If `inDescription_`: call `endDescriptionTag(n)` and return true.
4. If `!inBody_ || !doc_`: return true.
5. Handle the body end tags (table in A.6). Any end tag not listed there calls `popStyle(n)`. The result is always true.

`onText(t)`:
1. If `inBinary_`: append `t` to `binData_` when `loadImages_`, then return.
2. If `capture_` is set: call `appendCapture(t)` and return.
3. If `!inBody_ || !doc_`: drop the text.
4. If no paragraph is open: drop the text when `isAllSpace(t)`; otherwise open an implicit paragraph with `startPara(tableDepth_ > 0 ? BlockType::TableRow : contextType())`.
5. Call `appendText(t)`.

### A.4 The `<description>`: metadata

The capture mechanism:
- `beginCapture(target, tag)` sets `capture_ = target` and `captureTag_ = tag`. It replaces any capture in progress and does not clear the target.
- `appendCapture(t)` walks the code points of `t`:
  - for an `isSpaceCp` code point, it appends one `' '`, but only when the target is non-empty and its last byte is neither `' '` nor `'\n'`;
  - for any other code point, it appends the code point's bytes;
  - it does not filter control characters.
- `endCapture()` first removes trailing `' '` and `'\n'` bytes from the target, if a capture is active. It then sets `capture_ = nullptr` and `captureTag_ = {}`.

`startDescriptionTag(r)`, with `n = r.name()`:
1. `"title-info"`: set `inTitleInfo_ = true` and return.
2. If `!inTitleInfo_`: return. This ignores the start tags of `document-info`, `publish-info`, `src-title-info`, `custom-info` and so on.
3. `"author"`: set `inAuthor_ = true`, clear `first_`, `middle_`, `last_` and `nick_`, and return.
4. If `inAuthor_`:
   - `"first-name"` → capture into `first_`; `"middle-name"` → `middle_`; `"last-name"` → `last_`; `"nickname"` → `nick_`;
   - any other element → nothing;
   - then return.
5. Otherwise, the first match of:
   - `"book-title"`: clear `meta_.title` and capture into it.
   - `"lang"`: clear `meta_.lang` and capture into it.
   - `"genre"`: clear `genre_` and capture into it.
   - `"annotation"`: set `inMetaAnnotation_ = true` and capture into `meta_.annotation`. The annotation is **not** cleared, so several annotations concatenate.
   - `"p"` while `inMetaAnnotation_`: if `meta_.annotation` is non-empty and does not end in `'\n'`, remove its trailing `' '` bytes and append `'\n'`. As a result, annotation paragraphs are joined by a single `'\n'`.
   - `"sequence"`, only while `meta_.series` is empty:
     - `meta_.series = collapseSpaces(attr("name"))`;
     - `meta_.seriesIndex = std::atoi(std::string(attr("number")).c_str())`. A missing or non-numeric value gives 0, and `"3.5"` gives 3.
     - A sequence with an empty name leaves the series empty, so a later sequence can still set both fields.
   - `"coverpage"`: set `inCoverpage_ = true`.
   - `"image"` while `inCoverpage_`: if `coverId_` is empty, set `coverId_ = stripHash(attr("href"))`.

`endDescriptionTag(n)`:
1. If a capture is active and `n == captureTag_`, call `endCapture()`.
2. Then the first match of:
   - `"title-info"`: set `inTitleInfo_ = false`.
   - `"author"` while `inAuthor_`:
     - set `inAuthor_ = false`;
     - build `name` from `first_`, `middle_` and `last_`: apply `trimView` to each, skip the empty ones, and join the rest with single spaces;
     - if `name` is empty, use `trimCopy(nick_)` instead;
     - append `name` to `meta_.authors` if it is non-empty and not already present (exact string comparison).
   - `"genre"`: compute `g = trimCopy(genre_)` and append it to `meta_.genres` if non-empty. Duplicates are allowed. This branch is not limited to `title-info`. For example, the start tags in `src-title-info` were ignored, but a `</genre>` there still appends the last genre captured in `title-info` again.
   - `"annotation"`: set `inMetaAnnotation_ = false`.
   - `"coverpage"`: set `inCoverpage_ = false`.

Other description rules:
- Description text that is not being captured is discarded.
- A captured element left unclosed keeps capturing until its own end tag or `</description>`.
- Without a `</description>`, the builder stays in description mode for the rest of the file, so no body is parsed.
- In meta-only mode, parsing stops at `</description>`. It also stops at the first `<body>` or `<binary>` start tag met outside the description, for example when a binary comes first or the description is missing.

### A.5 Paragraph machinery

`contextType()` returns the first that applies:
1. `inTitle_` → `PoemTitle` if `poemTitle_`, else `Title`;
2. `epigraphDepth_ > 0` → `Epigraph`;
3. `citeDepth_ > 0` → `Cite`;
4. `annotationDepth_ > 0` → `Annotation`;
5. otherwise `Paragraph`.

`addId(r)`: if `attr("id")` is non-empty, it is appended to `pendingIds_`.

`startPara(type)`:
1. `closePara()`.
2. `inPara_ = true`; `cur_ = Block{}`; `cur_.type = type`.
3. `cur_.level` = `min(sectionDepth_, 6)` when `type == Title`, otherwise `min(epigraphDepth_ + citeDepth_, 6)`. Only `Title` takes the section depth; `PoemTitle`, `Verse`, `Subtitle`, `TableRow` and the rest take the epigraph+cite nesting depth.
4. `lastSpace_ = true`; `paraStyleBase_ = styleStack_.size()`.

`ensureSpan()` runs before each piece of text is appended to `cur_.text`. Verbatim:

```cpp
std::vector<Span>& spans = cur_.spans;
const uint32_t off = static_cast<uint32_t>(cur_.text.size());
if (spans.empty()) {
  if (flags_ == 0 && link_ < 0) return;
  spans.push_back(Span{off, flags_, link_});
  return;
}
Span& last = spans.back();
if (last.flags == flags_ && last.link == link_) return;
if (last.begin == off) {
  last.flags = flags_;
  last.link = link_;
  // Merge with the previous span when they became identical.
  if (spans.size() >= 2 && spans[spans.size() - 2].flags == flags_ && spans[spans.size() - 2].link == link_)
    spans.pop_back();
  return;
}
spans.push_back(Span{off, flags_, link_});
```
Spans are created only where text actually appears. A paragraph that is all regular text has no spans. Once a span exists, returning to regular style adds an explicit `{off, 0, -1}` span.

`appendText(t)` normalises white space:

```
for each code point c of t (keeping its original bytes):
  if isSpaceCp(c):
    if !lastSpace_: ensureSpan(); append ' '; lastSpace_ = true
    continue
  if c == U+FEFF || c == U+200B || c < U+0020 || c == U+007F: continue   // dropped; lastSpace_ unchanged
  ensureSpan(); append the bytes of c; lastSpace_ = false
```
`lastSpace_` carries across inline tags, so no space is ever added at a tag boundary:
- `a <b> b</b>` gives `a b`;
- `похожи<a>1</a> друг` gives `похожи1 друг`.

Leading white space in a paragraph is dropped, because `lastSpace_` starts true. NBSP, U+2007, U+202F, U+00AD, U+200C/U+200D and C1 characters are kept.

`closePara()`, in order:
1. If `!inPara_`, return. Otherwise set `inPara_ = false`.
2. If `styleStack_.size() > paraStyleBase_`, restore `flags_`/`link_` from `styleStack_[paraStyleBase_]` and `resize(paraStyleBase_)`. This closes any inline elements left open in the paragraph.
3. Remove trailing `' '` bytes from `cur_.text`, then remove trailing spans whose `begin >= text.size()`.
4. If the text is now empty, return without adding a block. Pending ids and a pending page break wait for the next block.
5. If `type` is `Paragraph` or `Subtitle` and `isSeparatorText(text)` is true, set `type = Separator`. Spans and level are kept.
6. `addBlock(std::move(cur_))`; then `cur_ = Block{}`.

`addBlock(Block&& b)`:
1. If `pendingPageBreak_`: set `b.pageBreakBefore = true` and `pendingPageBreak_ = false`.
2. `b.notes = notesBody_`.
3. With `idx = blocks.size()`, set `anchors[id] = Anchor{idx, idx + 1}` for every pending id; this overwrites an existing anchor with the same id. Then clear `pendingIds_`.
4. Append `b` to `blocks`.

### A.6 Body elements

All handlers in this section run only inside a body (see A.3, `onStart` step 6 and `onEnd` step 4). `n` is the local name.

**`<body>` start tag — `startBody(r)`:**
1. `closePara()`; `++bodyCount_`; `inBody_ = true`.
2. `notesBody_ = bodyCount_ > 1`: every body after the first is a notes body, whatever its `name` attribute says.
3. `sectionDepth_ = 0`.
4. If any block exists, `pendingPageBreak_ = true`.
5. If `bodyCount_ == 1 && !coverId_.empty() && loadImages_`: add an `Image` block with `image = imageIndex(coverId_)`, then set `pendingPageBreak_ = true`.

**`</body>` end tag:**
1. `closePara()`.
2. Call `closeSectionId()` until `sectionIds_` is empty.
3. `inBody_ = false`.
4. `sectionDepth_ = epigraphDepth_ = citeDepth_ = poemDepth_ = annotationDepth_ = tableDepth_ = 0`.
5. `inTitle_ = false`. An open title is dropped without a TOC entry.

`stanzaFirst_`, `poemTitle_`, `titleFirstBlock_`, `pendingPageBreak_`, `pendingIds_` and `cellIndex_` are not touched. A pending break or pending ids therefore carry over to the next body's first block.

**Start tags** (`startBodyTag`; the first matching row applies):

| element | start-tag action |
|---|---|
| `section` | `closePara()`; `++sectionDepth_`; if `sectionDepth_ == 1 && !notesBody_ && blocks non-empty` then `pendingPageBreak_ = true`; push `attr("id")` (possibly empty) onto `sectionIds_`, and also onto `pendingIds_` if non-empty |
| `title` | `closePara()`; `inTitle_ = true`; `poemTitle_ = poemDepth_ > 0`; `titleFirstBlock_ = blocks.size()` |
| `epigraph` | `closePara()`; `++epigraphDepth_` |
| `cite` | `closePara()`; `++citeDepth_`; `addId` |
| `poem` | `closePara()`; `++poemDepth_`; `addId` |
| `stanza` | `closePara()`; `stanzaFirst_ = true` |
| `annotation` | `closePara()`; `++annotationDepth_` |
| `p` | `startPara(contextType())`; `addId` |
| `v` | `startPara(Verse)`; `cur_.stanzaStart = stanzaFirst_`; `stanzaFirst_ = false`; `addId` |
| `subtitle` | `startPara(Subtitle)`; `addId` |
| `text-author` | `startPara(t)` where `t` is `EpigraphAuthor` if `epigraphDepth_ > 0`, else `CiteAuthor` if `citeDepth_ > 0`, else `TextAuthor` (no `addId`) |
| `date` | only if `poemDepth_ > 0`: `startPara(TextAuthor)`; elsewhere the tag is ignored and its text flows like any other text |
| `empty-line` | `closePara()`; `addBlock` a `Block` with `type = EmptyLine` and empty text |
| `image` | see A.9 |
| `table` | `closePara()`; `++tableDepth_` |
| `tr` | `startPara(TableRow)`; `cellIndex_ = 0` |
| `td`, `th` | see below |
| `emphasis`, `strong`, `strikethrough`, `sub`, `sup`, `code`, `a`, `style` | inline style, see A.7 |
| anything else | ignored: the tag disappears but its text stays (`<br/>` therefore adds nothing, not even a space) |

`td` / `th`:
```
if !inPara_: startPara(TableRow); cellIndex_ = 0
if (cellIndex_++ > 0):                               // not the first cell of the row
  saved = flags_; flags_ = 0; appendText(" | "); flags_ = saved; lastSpace_ = true
if n == "th": pushStyle("th", kSpanBold, -1)
```
- The separator goes through `appendText`. Its leading space is therefore dropped when the row text already ends with a space or is still empty; an empty first cell gives `"| b"`.
- `link_` is not cleared for the separator.
- A cell does not need a `tr`. A `td` inside some other open paragraph just adds a separator to that paragraph.
- Because a `<p>` inside a cell starts its own paragraph, it splits the row into separate blocks.

**End tags** (checked after the A.3 checks; first match):

| end tag | action |
|---|---|
| `p`, `v`, `subtitle`, `text-author`, `tr` | `closePara()`, whatever opened the paragraph |
| `date` | `closePara()`, only if `poemDepth_ > 0` |
| `td` | nothing |
| `th` | `popStyle("th")` |
| `title` | `closePara()`; if `inTitle_`, `endTitle()` |
| `section` | `closePara()`; if `inTitle_`, `endTitle()` (the TOC level is the depth before the decrement); if `sectionDepth_ > 0`, `--sectionDepth_`; `closeSectionId()` |
| `epigraph`, `cite`, `poem`, `annotation`, `table` | `closePara()`; decrement the matching depth if it is above 0 |
| `stanza` | `closePara()`; `stanzaFirst_ = false` |
| anything else (`emphasis`, `a`, `image`, `empty-line`, unknown names …) | `popStyle(n)` |

### A.7 Inline styles, links and note references

When an inline element starts, `add` and `link` (initially −1) are set as follows:

| element | `add` |
|---|---|
| `emphasis` | `kSpanItalic` (1) |
| `strong` | `kSpanBold` (2) |
| `strikethrough` | `kSpanStrike` (64) |
| `sub` | `kSpanSub` (8) |
| `sup` | `kSpanSup` (4) |
| `code` | `kSpanCode` (32) |
| `a` | if `attr("href")` is non-empty: `link = registerLink(href)` and `add = kSpanLink` (16); if also `attr("type") == "note"` (exact, case-sensitive), `add \|= kSpanNoteRef \| kSpanSup` (128 + 4). With an empty href, `add = 0`, but the element is still pushed so that its end tag pops it. |
| `style` | 0 |

Then, if no paragraph is open, `startPara(tableDepth_ > 0 ? TableRow : contextType())` runs, followed by `pushStyle(n, add, link)`.

- `registerLink(href)` appends `trimView(href)` to `doc.links` and returns its index. Links are not de-duplicated and keep their `#` (for example `"#n1"`). A whitespace-only href counts as non-empty, so it registers an empty link.
- `pushStyle(tag, add, link)` pushes `{tag, flags_, link_}`, then sets `flags_ |= add`, and sets `link_ = link` only if `add & kSpanLink`. Other styles therefore inherit an enclosing link.
- `popStyle(tag)` searches the stack from the top for the nearest entry with that tag. If it finds one at index `i`, it restores `flags_`/`link_` from that entry, calls `resize(i)` (which also discards every style opened after it), and lowers `paraStyleBase_` to the new size if it is larger. If it finds none, nothing happens.

Consequences:
- In `<strong>a<emphasis>b</strong>c</emphasis>`, `a` is bold, `b` is bold+italic and `c` is regular; the late `</emphasis>` finds nothing to close.
- Styles never outlive a paragraph, because `closePara` rewinds the stack.
- A note reference produces one span with flags 148 (`kSpanLink|kSpanNoteRef|kSpanSup`) whose link is the note's index.

### A.8 Sections, titles, the table of contents, anchors and page breaks

**Title text and TOC — `endTitle()`:**

```
inTitle_ = false
first = titleFirstBlock_; last = blocks.size(); titleFirstBlock_ = -1
if first < 0 || first >= last || poemTitle_: return            // poem titles never enter the TOC
if notesBody_ && sectionDepth_ > 0: return                     // titles of single notes ("1", "2", ...)
text = ""
for i in [first, last):
  t = blocks[i].text; if t is empty: continue
  if text is non-empty:
    if the last byte of text is not one of  .  !  ?  :  ,   → append '.'
    append ' '
  text += t
if text is non-empty: toc.push_back(TocEntry{text, first, sectionDepth_})
```
- Every block added between `<title>` and the end of the title belongs to it: `Title` paragraphs, but also a `Subtitle`, an `Image`, an `EmptyLine` and so on. Blocks with empty text are skipped in the join.
- The punctuation check looks at the last *byte*, so a title line ending in `…` (U+2026) still gets a `.` added.
- The TOC `level` is `sectionDepth_`, not clamped: 0 for a body title, 1 for a top-level section, 2 for its children, and so on. The notes body's own title has depth 0, so it is in the TOC; titles of sections inside a notes body are not.
- An unclosed `<title>` ends at `</section>`; everything up to there is title text, typed `Title`. At `</body>` or the end of the input it is dropped without a TOC entry.
- Another `<title>` start while one is still open just resets `titleFirstBlock_`.

**Anchors:**
- Ids come from `section`, `p`, `v`, `subtitle`, `cite` and `poem`; ids on other elements are ignored. Each id attaches to the next block added, as `{idx, idx + 1}`.
- An id on an element that produces no block, such as an empty `<p id="x"/>`, attaches to the next block instead.
- `closeSectionId()` pops the last entry of `sectionIds_`. If the entry is non-empty and present in `anchors`, it sets that anchor's `endBlock = blocks.size()`, one past the section's last block. If the section produced no block, its id is still pending; it later attaches to the next block with `endBlock = idx + 1` and is never extended.
- Anchors for `cite` and `poem` cover only their first block.

**Page breaks:** `pendingPageBreak_` is set in three cases:
1. at `<body>` when blocks already exist, so each notes body starts a page;
2. right after the cover image block;
3. at a `<section>` that reaches depth 1 in the main (non-notes) body, when blocks already exist.

The next `addBlock`, of any block type, consumes it. `</body>` does not clear it.

### A.9 Images, the cover and binaries

`imageIndex(id)` returns the index already mapped to `id`. Otherwise it appends `ImageData` with that `id` to `doc.images`, maps it, and returns the new index. Indices therefore follow the order of first reference: the cover, then `<image>` elements, then binaries that nothing referenced.

**Body `<image>` start tag:**
1. `href = stripHash(attr("href"))`.
2. If `href` is empty or `!loadImages_`: ignore the tag.
3. If a paragraph is open and already has text: ignore it, so pictures inside running text are dropped.
4. Otherwise run `closePara()` and add a block with `type = Image` and `image = imageIndex(href)`. An open paragraph that is still empty is discarded by the `closePara()`, and its pending ids attach to the image block.

Text after the image inside the same `<p>` opens a new implicit paragraph. External hrefs (`http://…`) become image ids that no binary ever fills.

**`finishBinary()`** (at `</binary>`):
1. `inBinary_ = false`.
2. If `!loadImages_ || !doc_ || binId_.empty()`: clear `binData_` and return.
3. Base64-decode `binData_`, then clear `binData_`.
4. `img = images[imageIndex(binId_)]`. The id is used as written; no `#` is stripped.
5. `img.mime = binType_` (verbatim) and `img.bytes = decoded`.
6. If `!probeImageSize(bytes.data(), bytes.size(), img.width, img.height)`: set `width = height = 0` and clear `bytes`; the mime stays. `probeImageSize` succeeds only when stb_image recognises the header and both dimensions are above 0 (its implementation and the stb configuration are specified in `03-core-foundation.md` § 6).

A later binary with the same id overwrites the earlier one. A self-closing `<binary .../>` registers an image with width 0.

### A.10 `finish()` and `compactBlocks()`

`finish()`:
1. `closePara()`. An unclosed final paragraph is kept.
2. If `!doc_`, return.
3. Call `closeSectionId()` until `sectionIds_` is empty.
4. `compactBlocks()`.
5. If `coverId_` is non-empty, is mapped in `imageIdx_`, and that image has `width > 0`: `doc.coverImage = that index`.
6. If `meta_.title` is empty and the TOC is not: `meta_.title = toc.front().title`. This is the first entry in creation order, taken before `finalize` sorts the TOC.

A title still open at the end of the input gets no TOC entry. Ids still pending at the end are lost.

`compactBlocks()` removes `Image` blocks whose image is missing or unusable and remaps the indices. Verbatim:

```cpp
std::vector<Block>& blocks = doc_->blocks;
const int n = static_cast<int>(blocks.size());
std::vector<int> remap(static_cast<size_t>(n) + 1);
int w = 0;
for (int i = 0; i < n; ++i) {
  remap[i] = w;
  Block& b = blocks[i];
  bool keep = true;
  if (b.type == BlockType::Image) keep = b.image >= 0 && doc_->images[b.image].width > 0;
  if (!keep) {
    if (b.pageBreakBefore && i + 1 < n) blocks[i + 1].pageBreakBefore = true;
    continue;
  }
  if (w != i) blocks[w] = std::move(b);
  ++w;
}
remap[n] = w;
blocks.resize(w);
for (auto& t : doc_->toc) t.block = remap[std::clamp(t.block, 0, n)];
for (auto& kv : doc_->anchors) {
  kv.second.block = remap[std::clamp(kv.second.block, 0, n)];
  kv.second.endBlock = remap[std::clamp(kv.second.endBlock, 0, n)];
  if (kv.second.endBlock <= kv.second.block) kv.second.endBlock = std::min(kv.second.block + 1, w);
}
```
- `doc.images` itself is not compacted, so unusable or unreferenced images stay in it.
- A removed block maps to the next kept block.
- When the cover image is unusable, its block disappears, but the block after it keeps the page break it already had. The book's first block then has `pageBreakBefore == true`.

### A.11 What broken markup leads to

This is a summary of the rules above:
- Inline elements left open end with their paragraph. A stray or mis-nested end tag restores the state from before the matching start tag, or does nothing when there is no match.
- `</p>`, `</v>`, `</subtitle>`, `</text-author>` and `</tr>` each close the current paragraph, whatever opened it. Block-level start tags close it too, so a `<p>` inside a `<p>` splits it.
- Text or an inline element outside a paragraph opens an implicit paragraph of `contextType()`, or `TableRow` inside a table. Whitespace-only text between blocks is ignored.
- Depth counters never go below 0. An unclosed `epigraph`, `cite`, `poem`, `annotation` or `table` lasts until `</body>`.
- Unclosed sections are closed at `</body>` and at the end of the input. An unclosed final paragraph is kept.
- An unclosed `<binary>` swallows the rest of the file.
- Unknown elements disappear but keep their text.

### A.12 Public functions

#### `std::string fb2ToUtf8(std::string_view raw, Charset* used)`

Verbatim:
```cpp
size_t bomLen = 0;
const Charset bom = detectBom(raw, bomLen);
Charset hint = Charset::Unknown;
if (bom == Charset::Unknown) {
  const std::string_view enc = findDeclaredEncoding(raw);
  hint = enc.empty() ? Charset::Utf8 : charsetFromName(enc);
  if (hint != Charset::Utf8 && hint != Charset::Unknown && hint != Charset::Utf16LE && hint != Charset::Utf16BE) {
    // Some files declare windows-1251 but are actually saved as UTF-8.
    size_t multi = 0, errors = 0;
    utf8Validate(raw.substr(0, std::min<size_t>(raw.size(), 256 * 1024)), &multi, &errors);
    if (errors == 0 && multi > 16) hint = Charset::Utf8;
  }
  if (hint == Charset::Utf16LE || hint == Charset::Utf16BE) hint = Charset::Unknown;  // no BOM: detect
}
return bytesToUtf8(raw, hint, used);
```
The resulting decisions:

| BOM | declaration found by `findDeclaredEncoding` | hint passed to `bytesToUtf8` |
|---|---|---|
| UTF-8 / UTF-16LE / UTF-16BE | (not looked at) | `Unknown`; the BOM decides |
| none | none, or no `encoding` value | `Utf8`; `bytesToUtf8` re-checks validity and falls back to detection |
| none | a UTF-8 name | `Utf8` (same as above) |
| none | a single-byte charset known to `charsetFromName` | `Utf8` if the first 256 KiB are error-free UTF-8 with **more than 16** multi-byte sequences; otherwise the declared charset, used without further checks |
| none | `utf-16`, `utf-16le`, `unicode`, `utf-16be` | `Unknown`, so `detectCharset` decides |
| none | a name `charsetFromName` does not know | `Unknown`, so `detectCharset` decides |

Details that follow from this:
- The 256 KiB prefix is not aligned to a code point. A multi-byte sequence cut at the 262 144th byte counts as an error, which keeps the declared single-byte charset.
- A UTF-16 file without a BOM has no findable declaration, so it gets the `Utf8` hint.
- `*used` receives the charset `bytesToUtf8` actually used.

#### `bool parseFb2(std::string_view raw, Document& doc, std::string* error, const Fb2Options& opt)`

1. `Charset cs = Unknown; utf8 = fb2ToUtf8(raw, &cs)`.
2. `doc = Document{}`.
3. Run an `XmlReader` over `utf8` with `Fb2Builder(&doc, doc.meta, false, opt.loadImages)`.
4. `doc.meta.format = "FB2"`; `doc.meta.encoding = charsetName(cs)`.
5. `doc.finalize()`.
6. If `doc.blocks` is empty: set `*error = "No readable text was found in this FB2 file."` (when `error` is non-null) and return false. A document holding only a valid cover image is not empty.
7. Return true. `*error` is not touched on success.

#### `bool parseFb2Meta(std::string_view raw, BookMeta& meta)`

1. `end = raw.find("</description>")` on the raw bytes. `head` is the whole of `raw` if not found, otherwise `raw.substr(0, end + 14)` (14 = the length of `</description>`).
2. `utf8 = fb2ToUtf8(head, &cs)`. The encoding decision sees only the head.
3. `meta = BookMeta{}`. Run `Fb2Builder(nullptr, meta, true, false)` over it. Parsing stops at `</description>`, `<body>` or `<binary>`.
4. `meta.format = "FB2"`; `meta.encoding = charsetName(cs)`.
5. Return `!meta.title.empty() || !meta.authors.empty()`. The title is never taken from the TOC here.

#### `void fb2ExtractText(std::string_view raw, std::string& text, BookMeta* meta)`

1. `utf8 = fb2ToUtf8(raw, &cs)`, over the whole file.
2. If `meta` is non-null: `*meta = BookMeta{}`; run `Fb2Builder(nullptr, *meta, true, false)` over `utf8`; set `meta->format = "FB2"` and `meta->encoding = charsetName(cs)`.
3. `text.clear()` and `text.reserve(utf8.size() / 2)`. The reserve is a capacity hint only.
4. Run a fresh `XmlReader` over `utf8` with three flags, `inBinary`, `inBody` and `inTitleInfo`, all false, and a `newline()` helper:
   ```cpp
   auto newline = [&] {
     if (!text.empty() && text.back() != '\n') {
       if (text.back() == ' ') text.back() = '\n';
       else text.push_back('\n');
     }
   };
   ```
   - **Start tag `n`:**
     - `"binary"` sets `inBinary = true`; `"body"` sets `inBody = true`; `"title-info"` sets `inTitleInfo = true`.
     - Then, if `isTextBlockTag(n)`, call `newline()`.
   - **End tag `n`:**
     - `"binary"`, `"body"` and `"title-info"` reset their flag to false.
     - Then, if `isTextBlockTag(n)`, call `newline()`.
   - **Text:** only when `!inBinary && (inBody || inTitleInfo)`. Walk its code points:
     - an `isSpaceCp` code point appends `' '` only if `text` is non-empty and does not end in `' '` or `'\n'`;
     - any other code point appends its bytes (no control-character filtering).

The result contains the `title-info` texts (genre codes, author name parts, book title, annotation, language code and so on) and the bodies' texts. It excludes binaries and all other description sections. Inline tags join their text without separators. The output may end in `'\n'` or `' '`.

---

## Part B — `src/core/TxtParser.cpp`

### B.1 Purpose and includes

Includes: `core/TxtParser.h`, `<algorithm>`, `<cctype>`, `<cstring>`, `<vector>`, `core/Encoding.h`, `core/Unicode.h`.

The pipeline is: decode, strip controls, cut Project Gutenberg boilerplate, split lines, detect the paragraph mode and the wrap width, rebuild paragraphs, classify each paragraph (separator, heading or paragraph), apply typography, then `finalize`.

### B.2 Lines

```cpp
struct Line {
  std::string_view text;  // trimmed
  int indent = 0;
  size_t len = 0;  // code points of `text`
  bool blank = true;
};
```

`std::vector<Line> splitLines(std::string_view s)` reserves `s.size() / 40 + 16` entries (capacity only), then:
```
i = 0
loop:
  e = first position >= i of '\r', '\n' or '\f'   (s.size() if none)
  raw = s[i, e)
  k = 0; indent = 0
  while k < raw.size():                 // measure the leading indentation
    ' '            → indent += 1, k += 1
    '\t'           → indent += 4, k += 1
    C2 A0 (U+00A0) → indent += 1, k += 2
    E3 80 80 (U+3000 ideographic space) → indent += 2, k += 3
    anything else  → stop
  text  = trimView(raw.substr(k))
  blank = text.empty()
  len   = blank ? 0 : utf8Length(text)
  push Line{text, indent, len, blank}
  if e >= s.size(): break
  formFeed = (s[e] == '\f')
  i = (s[e] == '\r' && e + 1 < s.size() && s[e + 1] == '\n') ? e + 2 : e + 1
  if formFeed: push Line{}            // an extra blank line after the line the form feed ended
```
- CRLF, a lone CR, LF and FF each end a line.
- `"\n\r"` counts as two line breaks.
- The last segment is always pushed. Input ending in a line break therefore yields a final blank line, and empty input yields one blank line.
- A line holding only characters that `trimView` does not strip (for example U+2003) is not blank, even though `collapseSpaces` later reduces it to an empty string.

### B.3 Wrap width — `size_t detectWrapWidth(const std::vector<Line>& lines)`

Returns the column at which the text is hard-wrapped, or 0. Verbatim:
```cpp
std::vector<size_t> lens;
lens.reserve(lines.size());
for (const Line& l : lines) {
  if (!l.blank) lens.push_back(l.len + static_cast<size_t>(l.indent));
}
if (lens.size() < 8) return 0;
std::sort(lens.begin(), lens.end());
const size_t p95 = lens[lens.size() * 95 / 100];
const size_t p99 = lens[std::min(lens.size() - 1, lens.size() * 99 / 100)];
if (p95 < 30 || p95 > 120) return 0;
if (p99 > p95 + p95 / 8 + 3) return 0;  // long tail: lines are paragraphs, not wrapped
size_t nearMax = 0;
for (size_t v : lens) {
  if (v * 4 >= p95 * 3) ++nearMax;
}
if (nearMax * 10 < lens.size() * 3) return 0;
return p95;
```

### B.4 Paragraph mode — `TxtParagraphMode detectMode(const std::vector<Line>& lines)`

```
skip leading and trailing blank lines; over the remaining range count:
  blank, nonBlank, indented (= non-blank lines with indent >= 2)
if nonBlank == 0                                                    → EveryLine
if blank * 100 >= nonBlank * 15                                     → BlankLines
if indented * 100 >= nonBlank * 15 && indented * 100 <= nonBlank * 95 → Indented
otherwise                                                           → EveryLine
```
The public `detectTxtParagraphMode(utf8)` is `detectMode(splitLines(utf8))`. It does not strip controls or Gutenberg text.

### B.5 Chapter headings

`bool isRoman(std::string_view w)`: false if `w` is empty or longer than 8 bytes. Otherwise true when every byte is in `"IVXLCDMivxlcdm"` (checked with `std::strchr`). Numeral syntax is not checked, so `mild`, `dim` and `civil` count as roman numerals.

`bool isNumberToken(std::string_view tok)`:
1. Repeatedly remove trailing `.`, `:`, `,` and `)`. If nothing is left, return false.
2. If it is all ASCII digits, return `size <= 4`.
3. If `isRoman`, return true.
4. Return true if `toLowerUtf8(tok)` equals one of these words, verbatim and in this order:
```cpp
"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
"first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "last",
"первая", "вторая", "третья", "четвертая", "четвёртая", "пятая", "шестая", "седьмая", "восьмая",
"девятая", "десятая", "первый", "второй", "третий", "четвертый", "четвёртый", "пятый",
"шестой", "седьмой", "восьмой", "девятый", "десятый", "первое", "второе", "третье",
"последняя", "заключительная"
```

`bool isHeadingLine(std::string_view t, int& level)`. Level 1 means part or book; level 2 means chapter.
1. `len = utf8Length(t)`. If `len == 0 || len > 80`, return false.
2. **Bare numeral.** Let `w` be `t` with trailing `.` and `:` removed repeatedly.
   - If `w` is non-empty, at most 8 bytes, and every byte is in `"IVXLCDM"` (upper case only), set `level = 2` and return true.
   - Else, if `w` is non-empty, at most 3 bytes, and all ASCII digits, set `level = 2` and return true.
3. **Keywords.** `low = toLowerUtf8(t)`. Try the keywords below in order; each is `{word, level, needsNumber}`, verbatim:
```cpp
{"часть", 1, true},         {"part", 1, true},          {"book", 1, true},           {"книга", 1, true},
{"том", 1, true},           {"volume", 1, true},        {"глава", 2, true},          {"chapter", 2, true},
{"stave", 2, true},         {"act", 2, true},           {"действие", 2, true},       {"letter", 2, true},
{"пролог", 2, false},       {"эпилог", 2, false},       {"prologue", 2, false},      {"epilogue", 2, false},
{"предисловие", 2, false},  {"послесловие", 2, false},  {"введение", 2, false},      {"заключение", 2, false},
{"preface", 2, false},      {"introduction", 2, false}, {"foreword", 2, false},      {"afterword", 2, false},
{"appendix", 2, false},     {"приложение", 2, false},   {"от автора", 2, false},     {"contents", 2, false},
{"оглавление", 2, false},   {"содержание", 2, false}
```
   For each keyword with byte length `kl`: skip it unless `low` starts with `word`; otherwise continue verbatim:
```cpp
const std::string_view rest = std::string_view(low).substr(kl);
if (!rest.empty() && rest[0] != ' ' && rest[0] != '.' && rest[0] != ':' && rest[0] != '-' &&
    static_cast<unsigned char>(rest[0]) < 0x80 && !(rest[0] >= '0' && rest[0] <= '9'))
  continue;  // keyword is a prefix of a longer word
if (!rest.empty() && static_cast<unsigned char>(rest[0]) >= 0x80) {
  // Cyrillic continuation means a longer word ("главами") unless it is a dash/space variant.
  size_t p = 0;
  const char32_t c = utf8Decode(rest, p);
  if (isLetterCp(c)) continue;
}
if (kw.needsNumber) {
  std::string_view r = trimView(rest);
  if (r.empty()) continue;
  const size_t sp = r.find(' ');
  if (!isNumberToken(r.substr(0, sp))) continue;
} else if (len > 60) {
  continue;
}
level = kw.level;
return true;
```
4. Return false.

In words:
- A keyword may be followed by nothing, a space, `.`, `:`, `-`, an ASCII digit (`chapter1`), or a non-letter non-ASCII character (NBSP, `—`, `«`).
- Any other ASCII character after it rejects the keyword (`Prologue,` → no; `Actually` → no). So does a following letter (`главами` → no).
- Keywords that need a number require the first space-delimited token after the keyword (after `trimView`) to be an `isNumberToken`.
- Keywords that need no number accept any continuation, as long as the whole line is at most 60 code points (`Introduction to X`).
- Because `low` is lowercase, `CHAPTER I` matches with the token `i`.

### B.6 `bool isSeparatorLine(std::string_view t)`

```
if t.empty() || t.size() > 40: return false
marks = 0
for each code point c:
  if c == U+0020 or c == U+00A0: continue
  if c is in TXT_MARKS: ++marks; continue
  return false
return marks >= 3 || (marks >= 1 && t contains '*')
```
`TXT_MARKS` = `*`, `~`, `#`, `=`, U+2022 `•`, U+2014 `—`, `-`, U+00B7 `·`, `_`.

For example, `*`, `* *`, `---`, `===`, `___` and `• • •` are separators; `—`, `##` and `- -` are not. Unlike FB2, `x` and `X` are not marks here.

### B.7 `void joinLine(std::string& para, std::string_view next)`

1. If `para` is empty, it becomes `next`.
2. Else, if `para` ends in `'-'` and `para.size() >= 2`:
   - `before` = the code point just before the hyphen (found with `utf8PrevPos(para, para.size() - 1)` and decoded);
   - `after` = the first code point of `next`, or U+0020 if `next` is empty;
   - if `isLetterCp(before) && isLetterCp(after) && toLowerCp(after) == after`, append `next` directly. The hyphen stays and no space is added: `con-` + `tinue` → `con-tinue`.
3. Otherwise append `' '` and then `next`. An uppercase letter after the hyphen therefore keeps the space: `Москва-` + `Река` → `Москва- Река`.

### B.8 Dashes — `std::string fixDashes(const std::string& p)`

If `p` contains no `'-'`, return it unchanged. Otherwise reserve `p.size() + 8` bytes; `em` is the 3-byte sequence `E2 80 94` (U+2014). Walk the bytes:
```
for i in 0 .. p.size()-1:
  c = p[i]
  (1) if c == '-' && i+1 < size && p[i+1] == '-':
        j = end of the run of '-' starting at i
        if j - i <= 3: out += em; i = j - 1; continue     // "--" or "---" → one em dash
        // a run of 4 or more falls through, handled one hyphen at a time
  (2) if c == '-' && (i == 0 || p[i-1] == ' ') && (i+1 == size || p[i+1] == ' '):
        out += em; continue                              // free-standing hyphen
  (3) if c == '-' && i > 0 && i+1 < size && p[i+1] == ' ' && p[i-1] is one of  . , ! ? ; :
        out += ' '; out += em; continue                  // "дочка...- ответил" → "дочка... — ответил"
  (4) out += c
```
A run of n ≥ 4 hyphens comes out as (n − 3) plain hyphens followed by one em dash (`a----b` → `a-—b`). A hyphen inside a word (`по-своему`) or before a non-space (`-5`) is kept.

### B.9 Underscore italics — `void applyUnderscoreItalics(Block& b)`

This runs only for Gutenberg texts (see B.13).

1. If `b.text` has no `'_'`, return.
2. A *word byte* is any byte `>= 0x80`, or a byte for which `std::isalnum` is true; for ASCII that means letters and digits. Multi-byte characters such as `—` therefore count as word bytes.
3. Build `out` and a list of spans with `italic = false`. For each byte `c` at index `i`:
   - If `c == '_'`:
     - `prevWord` = `i > 0` and `t[i-1]` is a word byte; `nextWord` = `i + 1 < size` and `t[i+1]` is a word byte.
     - If `!italic && !prevWord`: set `italic = true`, push `Span{out.size(), kSpanItalic, -1}`, and drop the `_`.
     - Else, if `italic && !nextWord`: set `italic = false`, push `Span{out.size(), 0, -1}`, and drop the `_`.
     - Otherwise the `_` is kept as an ordinary byte.
   - Append every byte that was not dropped to `out`.
4. If no span was pushed, return; the text stays unchanged, which happens for `snake_case`.
5. Merge the spans: a span whose `begin` equals the previous merged span's `begin` replaces it. Then remove trailing merged spans with `begin >= out.size()`.
6. `b.text = out`; `b.spans = merged`.

An unclosed italic runs to the end of the paragraph. A closing `_` directly followed by a multi-byte character (for example an em dash) does not close the italic.

### B.10 Project Gutenberg — `std::string_view stripGutenberg(std::string_view text, BookMeta* meta)`

1. Search for `"*** START OF"` only within the first `min(size, 60000)` bytes. If not found, return `text` unchanged.
2. If `meta` is non-null, read header fields from `head = text[0, start)`. For each key, find its first occurrence anywhere in `head`; the value is the rest of that line (up to `\r` or `\n`, or the end of `head`), passed through `trimCopy`:
   - `"Title:"` → `meta->title` if non-empty;
   - `"Author:"` → `meta->authors = {author}` if non-empty;
   - `"Language:"` → `meta->lang` if non-empty.
   The keys are case-sensitive, and only the first line of a multi-line value is taken.
3. The body starts just after the first `'\n'` at or after `start`, so the rest of the START line is skipped. If there is no such `'\n'`, the body is empty.
4. The body ends at the first `"*** END OF"` after the body start, or at the end of the text.
5. Return the view `text[bodyStart, end)`.

### B.11 `void stripControls(std::string& s)`

Removes, in place, every byte `c` with `(c < 0x20 && c != '\n' && c != '\r' && c != '\t' && c != '\f') || c == 0x7F`. This removes lib.ru's `\x14`/`\x15` markers, NULs, `\v` and so on.

### B.12 `void guessMetaFromFileStem(std::string_view stem, BookMeta& meta)`

```cpp
std::string s(stem);
for (const char* sep : {" - ", "_-_", " — ", " – ", "--"}) {
```
The third separator is U+0020 U+2014 U+0020 and the fourth is U+0020 U+2013 U+0020; both are 5 bytes.

For each separator in that order:
1. `p = s.find(sep)` (first occurrence). Skip this separator if it is not found or `p == 0`.
2. `author = s[0, p)`; `title = s[p + strlen(sep), end)`.
3. In both, replace every `'_'` with `' '`, then apply `collapseSpaces`.
4. If both are non-empty:
   - if `meta.authors` is empty, set it to `{author}`;
   - if `meta.title` is empty, set it to `title`;
   - return, even when neither field changed.
5. Otherwise try the next separator.

If no separator succeeded: replace `'_'` with `' '` in `s`, and if `meta.title` is empty set `meta.title = collapseSpaces(s)`. No author is guessed in this case.

Examples:
- `"A - B - C"` → author `A`, title `B - C`.
- `"Foo - "` → the first split fails (empty title) and no other separator matches, so the title becomes `Foo -`.

### B.13 `bool parseTxt(std::string_view raw, Document& doc, std::string_view fileStem, std::string* error)`

Set-up:
1. `doc = Document{}`.
2. `utf8 = bytesToUtf8(raw, Charset::Unknown, &cs)`, so the BOM or detection decides; then `stripControls(utf8)`.
3. `text = stripGutenberg(utf8, &doc.meta)`; `gutenberg = (text.size() != utf8.size())`, i.e. the START marker was found.
4. `doc.meta.format = "TXT"`; `doc.meta.encoding = charsetName(cs)`.
5. `guessMetaFromFileStem(fileStem, doc.meta)`. Gutenberg header values win; the file stem only fills fields that are still empty.
6. `lines = splitLines(text)`; `mode = detectMode(lines)`; `wrap = detectWrapWidth(lines)`; `shortLimit = wrap * 7 / 10`.
7. Local state: `std::string para`, `paraIsSingleLine = true`, `blankRun = 0`, `seenTopHeading = false`, `prevLen = 0`, `prevIndent = 0`.

Classifying a finished paragraph, verbatim:
```cpp
auto addParagraph = [&](std::string&& t, bool singleLine) {
  Block b;
  int level = 0;
  if (singleLine && isSeparatorLine(t)) {
    b.type = BlockType::Separator;
  } else if (singleLine && isHeadingLine(t, level)) {
    b.type = BlockType::Title;
    if (level == 1) seenTopHeading = true;
    b.level = static_cast<uint8_t>(level == 1 || !seenTopHeading ? 1 : 2);
    b.pageBreakBefore = b.level == 1 && !doc.blocks.empty();
    doc.toc.push_back(TocEntry{t, static_cast<int>(doc.blocks.size()), b.level});
  }
  if (b.type == BlockType::Paragraph) {
    b.text = fixDashes(t);
    if (gutenberg) applyUnderscoreItalics(b);
  } else {
    b.text = std::move(t);
  }
  doc.blocks.push_back(std::move(b));
};
auto flush = [&] {
  if (!para.empty()) addParagraph(std::move(para), paraIsSingleLine);
  para.clear();
  paraIsSingleLine = true;
};
```
What this does:
- Chapter-level headings (level 2) are promoted to level 1 until the first part-level heading has been seen.
- Only level-1 headings that are not the first block get a page break.
- The TOC entry uses the heading text as written, and its level is the block level.
- Separators and headings are never dash-fixed.

The line loop, verbatim:
```cpp
for (const Line& l : lines) {
  if (l.blank) {
    flush();
    ++blankRun;
    prevLen = 0;
    prevIndent = 0;
    continue;
  }
  // Scene breaks: two blank lines in blank-line mode, any blank line in the other modes.
  const int sceneBreakAt = mode == TxtParagraphMode::BlankLines ? 2 : 1;
  if (blankRun >= sceneBreakAt && !doc.blocks.empty() && doc.blocks.back().type != BlockType::EmptyLine &&
      doc.blocks.back().type != BlockType::Title) {
    Block e;
    e.type = BlockType::EmptyLine;
    doc.blocks.push_back(std::move(e));
  }
  blankRun = 0;
  const std::string line = collapseSpaces(l.text);
  bool startNew = para.empty() || wrap == 0;
  if (!startNew) {
    if (mode == TxtParagraphMode::Indented && l.indent >= 2) startNew = true;
    else if (l.indent >= 2 && l.indent > prevIndent) startNew = true;  // red-line indent starts a paragraph
    else if (prevLen < shortLimit) startNew = true;  // a short previous line ended its paragraph
  }
  if (!startNew && para.size() < 200) {
    // A heading followed by text on the next line must not swallow it.
    int lvl = 0;
    if (paraIsSingleLine && isHeadingLine(para, lvl)) startNew = true;
  }
  if (startNew) {
    flush();
    para = line;
  } else {
    joinLine(para, line);
    paraIsSingleLine = false;
  }
  prevLen = l.len + static_cast<size_t>(l.indent);
  prevIndent = l.indent;
}
flush();
```
Notes:
- When no wrap width is detected (`wrap == 0`), every non-blank line is its own paragraph, whatever the mode. The mode then only decides how many blank lines make a scene break: 2 in `BlankLines` mode, 1 otherwise.
- An `EmptyLine` block is never inserted directly after a `Title` or another `EmptyLine`, nor before the first block. It *is* inserted after a `Separator`, and it may precede a heading.
- `prevLen` counts code points of the trimmed line plus its indent. `para.size()` is in bytes.

Tail:
1. Remove trailing `EmptyLine` blocks.
2. Clamp every TOC `block` into `[0, blocks.size() - 1]`: indices at or past the end become `size - 1`, and anything negative then becomes 0.
3. `doc.finalize()`.
4. If there are no blocks: set `*error = "The text file is empty."` (when `error` is non-null) and return false. Otherwise return true.

### B.14 `void txtExtractText(std::string_view raw, std::string& text, BookMeta* meta, std::string_view fileStem)`

1. `utf8 = bytesToUtf8(raw, Unknown, &cs)`; `stripControls(utf8)`.
2. `m` is `*meta`, or a local `BookMeta` when `meta` is null; reset `m = BookMeta{}`.
3. `body = stripGutenberg(utf8, &m)`.
4. `m.format = "TXT"`; `m.encoding = charsetName(cs)`; `guessMetaFromFileStem(fileStem, m)`.
5. `text` = all of `utf8` (moved) when `body.size() == utf8.size()`, otherwise a copy of `body`. Line breaks are kept as they are; no paragraphs are rebuilt.

---

## Part C — `src/core/BookLoader.cpp`

### C.1 Includes and constants

Includes: `core/BookLoader.h`, `<miniz.h>` (miniz 3 from vcpkg), `<algorithm>`, `<cstdio>`, `<cstring>`, `<fstream>`, `core/Fb2Parser.h`, `core/TxtParser.h`, `core/Unicode.h`.

`constexpr size_t kMaxBookBytes = size_t(256) * 1024 * 1024;` is 268 435 456 bytes. It is the hard cap on how much of any book is ever read, and protects against zip bombs.

Every file this unit opens goes through `pathFromUtf8`, as a `std::ifstream` in binary mode.

### C.2 Paths

- `pathFromUtf8(utf8)` returns `std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(utf8.data()), utf8.size()))`. On Windows the UTF-8 is converted to the native wide path, so non-ASCII names work whatever the ANSI code page is. On POSIX and Android the bytes are used unchanged.
- `pathToUtf8(p)` takes `p.u8string()` and copies its bytes into a `std::string`.

### C.3 File-name rules

- `formatFromName(name)` uses `endsWithNoCase` and checks, in this order:
  - `".fb2.zip"` → `Fb2Zip`
  - `".txt.zip"` → `TxtZip`
  - `".zip"` → `Zip`
  - `".fb2"` → `Fb2`
  - `".txt"` → `Txt`
  - anything else → `Unknown`

  It works on full paths too, since only the suffix matters.
- `isSupportedBookName(name)` is `formatFromName(name) != Unknown`. Any `.zip` counts as supported.
- `fileNameOf(path)` returns everything after the last `'/'` or `'\\'`, or the whole input if there is none.
- `fileStemOf(path)` takes `name = fileNameOf(path)` and makes 2 passes. In each pass, the first of `".zip"`, `".fb2"`, `".txt"` that `name` ends with (case-insensitively) is cut off, but only if `name` is longer than that extension; at most one extension is removed per pass. Examples:
  - `Book.fb2.zip` → `Book`
  - `a.zip.zip.zip` → `a.zip`
  - `.fb2` → `.fb2`
  - `Book.epub` → `Book.epub`

### C.4 `bool readFile(const std::string& path, std::string& out, size_t maxBytes, std::string* err)`

1. Open the file. On failure: `"Cannot open the file."`, return false.
2. `seekg(0, end)`; `size = tellg()`. If `size < 0`: `"Cannot read the file."`, return false.
3. `seekg(0, beg)`; `n = min(size, min(maxBytes, kMaxBookBytes))`.
4. `out.assign(n, '\0')`; if `n > 0`, `read(out.data(), n)`.
5. `out.resize(gcount())`; return true.

A file larger than the cap is silently truncated. Error strings are written only when `err` is non-null; this applies throughout this unit.

### C.5 Zip archives

Verbatim:
```cpp
struct ZipSource {
  std::ifstream f;
  uint64_t size = 0;
};

size_t zipRead(void* opaque, mz_uint64 ofs, void* buf, size_t n) {
  auto* z = static_cast<ZipSource*>(opaque);
  z->f.clear();
  z->f.seekg(static_cast<std::streamoff>(ofs));
  if (!z->f) return 0;
  z->f.read(static_cast<char*>(buf), static_cast<std::streamsize>(n));
  return static_cast<size_t>(z->f.gcount());
}
```

`bool looksLikeFb2(std::string_view raw)` is true when the first `min(size, 4096)` bytes contain `"<FictionBook"` (case-sensitive, raw bytes).

`bool readZipEntry(path, raw, fmt, err, maxBytes)`:
1. Open `src.f`. On failure: `"Cannot open the file."`, return false.
2. `src.size = tellg()` after seeking to the end.
3. Zero an `mz_zip_archive` with `memset`, set `m_pRead = zipRead` and `m_pIO_opaque = &src`.
4. If `!mz_zip_reader_init(&zip, src.size, 0)`: `"The zip archive is damaged or unsupported."`, return false.
5. Choose the entry. For `i` in `0 .. mz_zip_reader_get_num_files(&zip) - 1`:
   - skip directories (`mz_zip_reader_is_file_a_directory`) and entries whose `mz_zip_reader_file_stat` fails;
   - `name = st.m_filename`; `fb2 = endsWithNoCase(name, ".fb2")`; `txt = endsWithNoCase(name, ".txt")`; skip the entry if neither;
   - update the choice with this condition, verbatim:
     ```cpp
     if (best < 0 || (fb2 && !bestFb2) || (fb2 == bestFb2 && !fb2 && st.m_uncomp_size > bestSize)) {
       best = static_cast<int>(i); bestFb2 = fb2; bestSize = st.m_uncomp_size;
     }
     ```
   The **first** `.fb2` entry wins. Without any `.fb2`, the **largest** `.txt` wins; with equal sizes the earlier one stays. Directory prefixes in entry names do not matter.
6. If `best < 0`: `mz_zip_reader_end`, then `"The archive does not contain an FB2 or TXT book."`, return false.
7. If `bestSize > kMaxBookBytes`: `mz_zip_reader_end`, then `"The book inside the archive is too large."`, return false. This is checked before `maxBytes` is applied.
8. Extract:
   - `want = min(bestSize, maxBytes)`; `raw.assign(want, '\0')`; `got = 0`;
   - if `mz_zip_reader_extract_iter_new(&zip, best, 0)` returns an iterator: `got = mz_zip_reader_extract_iter_read(it, raw.data(), raw.size())`, then `mz_zip_reader_extract_iter_free(it)`;
   - `mz_zip_reader_end(&zip)`; `raw.resize(got)`.

   Only the first `want` bytes are decompressed. A short or partial read is accepted.
9. If `got == 0 && want > 0`: `"Could not unpack the book from the archive."`, return false. An empty entry (`want == 0`) succeeds with empty `raw`.
10. `fmt` = `Fb2` if `bestFb2`, else `Txt`. A `Txt` result whose content `looksLikeFb2` becomes `Fb2`. Return true.

### C.6 `bool readBookRaw(path, raw, contentFormat, err, maxBytes, zipped)`

1. If `zipped` is non-null, set `*zipped = false`.
2. Open the file and read up to 4 bytes into `char magic[4] = {}`. If the open fails: `"Cannot open the file."`, return false.
3. If `magic` is `'P' 'K' 0x03 0x04`: set `*zipped = true` (if non-null) and return `readZipEntry(path, raw, fmt, err, maxBytes)`. Content decides, not the name, so a zip named `.fb2` or `.txt` is unpacked.
4. `byName = formatFromName(path)`. If it is `Zip`, `Fb2Zip` or `TxtZip`: `"The file is not a valid zip archive."`, return false.
5. `readFile(path, raw, maxBytes, err)`; return false if it fails.
6. `fmt` = `Fb2` if `byName == Fb2`, else `Txt` (this includes unknown extensions). A `Txt` result that `looksLikeFb2` becomes `Fb2`. Return true.

On success `contentFormat` is only ever `Fb2` or `Txt`.

### C.7 `loadBook`, `loadBookMeta`, `loadBookText`

**`loadBook(path, doc, err)`:**
1. `readBookRaw(path, raw, fmt, err, kMaxBookBytes, &zipped)`. On failure, return false and leave `doc` untouched.
2. `ok` = `parseFb2(raw, doc, err)` for `Fb2` (default options, so images are loaded), otherwise `parseTxt(raw, doc, fileStemOf(path), err)`. The stem comes from the outer file name, even for zips.
3. If `ok && zipped`: `doc.meta.format += " (zip)"`, giving `"FB2 (zip)"` or `"TXT (zip)"`.
4. If `ok` and `doc.meta.title` is empty: `doc.meta.title = fileStemOf(path)`.
5. Return `ok`.

**`loadBookMeta(path, meta, err)`:** with `kHead = 256 * 1024`:
1. `readBookRaw(path, raw, fmt, err, kHead, &zipped)`; return false if it fails.
2. `meta = BookMeta{}`.
3. For `Fb2`:
   - if `raw.size() >= kHead` and `raw` has no `"</description>"`, read again with `maxBytes = size_t(16) * 1024 * 1024` (16 MiB), returning false if that read fails;
   - then call `parseFb2Meta(raw, meta)` and ignore its result.
4. Otherwise (TXT): if `raw.size() > 64 * 1024`, truncate it to 65 536 bytes. Then `txtExtractText(raw, text, &meta, fileStemOf(path))` with a local `text` that is thrown away.
5. If `zipped`: `meta.format += " (zip)"`.
6. If `meta.title` is empty: `meta.title = fileStemOf(path)`.
7. Return true, even when no metadata was found.

**`loadBookText(path, text, meta, err)`:**
1. `readBookRaw(..., kMaxBookBytes, &zipped)`; return false if it fails.
2. `fb2ExtractText(raw, text, meta)` for `Fb2`, otherwise `txtExtractText(raw, text, meta, fileStemOf(path))`.
3. If `meta` is non-null: append `" (zip)"` to the format when zipped, and set the title to `fileStemOf(path)` when it is empty.
4. Return true.

### C.8 `std::string bookFingerprint(const std::string& path)`

1. Open the file. If that fails, return `""`.
2. `size = static_cast<uint64_t>(tellg())` after seeking to the end; then seek back to the start.
3. `head = std::string(min(size, 64 * 1024), '\0')`, then `read(head.data(), head.size())`. `gcount` is not checked, so a short read leaves zero bytes, which are hashed too.
4. Hash `head`, verbatim:
```cpp
uint64_t h = 1469598103934665603ull;  // FNV-1a 64
for (unsigned char c : head) {
  h ^= c;
  h *= 1099511628211ull;
}
char buf[48];
std::snprintf(buf, sizeof(buf), "%016llx-%llx", static_cast<unsigned long long>(h),
              static_cast<unsigned long long>(size));
return buf;
```
**Write the offset basis exactly as `1469598103934665603` (19 digits, `0x14650fb0739d0383`).** It differs from the textbook FNV-1a basis 14695981039346656037, and fingerprints stored in the settings (the recent-books list) depend on this value.

The output is 16 lowercase hex digits, zero-padded, then `-`, then the file size in lowercase hex without padding. The hash covers the file's raw bytes (for a zip, the container bytes).

---

## Part D — Tests in `tests/core_tests.cpp` that constrain these files

**`testFb2` with `sampleFb2` and `checkSampleDoc`.** Three variants must produce the same document: UTF-8 declared and stored; `windows-1251` declared and stored; `windows-1251` declared but stored as UTF-8. The checks pin:
- **Metadata.**
  - Title `Анна Каренина`.
  - Exactly one author, `Лев Николаевич Толстой`. The `document-info` author `converter` must not be added.
  - Series `Классика` with index 3; language `ru`.
  - Annotation exactly `Роман о любви.`: whitespace trimmed, no `\n` for a single `<p>`.
- **Cover.** `coverImage == 0` and `blocks[0]` is the `Image` block. The cover is referenced first, and base64 decoding plus the PNG probe must succeed on the 1×1 PNG.
- **TOC.** Four entries in this order:
  1. `Лев Толстой. Анна Каренина` (body title, paragraphs joined with `". "`);
  2. `Часть первая` at level 1;
  3. `I` at level 2;
  4. `Примечания` (the notes body title). The note's own title `1` must be absent.
- **Block types.** 3 `Verse` blocks, 2 of them with `stanzaStart`; a `Separator` from `<p>* * *</p>`; an `EmptyLine`; an `Epigraph` block.
- **Inline styles.**
  - The paragraph text is `Все счастливые семьи похожи1 друг на друга.` (no space added around the note reference).
  - It is italic at byte 7 and not at 0. At the `1` the flags contain `kSpanNoteRef` and `kSpanSup`, and the link indexes `"#n1"` (stored with `#`).
  - White space normalises to `Второй абзац с жирным и курсивом текстом.`, with bold+italic on `курсивом`.
  - An unclosed `<emphasis>` must not leak: `Обычный текст` has flags 0 at offset 0.
- **Anchors and totals.**
  - Anchor `n1` covers the note: `plainText` contains `Текст сноски.` and the first block of the anchor has `notes == true`.
  - Anchor `part1` exists.
  - `totalChars > 100` (from finalize).
- **Encoding.** `meta.encoding == "windows-1251"` for the cp1251 file.
- **Other entry points.**
  - `parseFb2Meta(cp1251)` returns true with the title.
  - `fb2ExtractText` contains `друг на друга`, does not contain `iVBOR` (no binary text), and fills the title.
  - The broken input `<FictionBook><body><section><p>broken <emphasis>text</section` yields at least one block.

**`testTxt`:**
- **Gutenberg, CRLF, hard-wrapped, blank-line separated.**
  - Title `Test Book` and author `Jane Doe` come from the header; the stem `"whatever"` must not override them.
  - TOC has 2 entries (`CHAPTER I`, `CHAPTER II`, through the roman-numeral token rule).
  - Exactly 7 `Paragraph` blocks, none containing `\n` (wrap detection, then joining lines with spaces).
  - `license` appears nowhere (END marker cut).
  - `blocks[1]` is the first joined paragraph. No `EmptyLine` comes after a heading, and one blank line is not a scene break in `BlankLines` mode.
- **cp1251, lib.ru style with indentation.**
  - The stem `Толстой - Анна Каренина` supplies title and author.
  - Encoding is `windows-1251`.
  - TOC has 2 entries: `Глава 1` and `Глава вторая` (the number-word rule).
  - Exactly 6 paragraphs: `Indented` mode plus wrap detection, so every indented line starts a paragraph and unindented lines join it.
- **20 long, unwrapped lines** give exactly 20 blocks. Wrap detection must reject them, because p95 > 120.

**`testTxtTypography`:**
- A Gutenberg marker at offset 0 with no header fields.
- `--` becomes `—`, and ` - ` becomes ` — `.
- `_very_` becomes `very` with italic exactly over those bytes (offsets 6..9; offset 11 is regular).
- `...- he` becomes `... — he`, and a leading `- ` becomes `— `.
- The result is exactly 2 blocks.

**`testLibrarySearch`:**
- `loadBook` on `Tolstoy_Anna.fb2.zip` gives the title `Анна Каренина` and `meta.format == "FB2 (zip)"`.
- `bookFingerprint` of that file is non-empty.
- Through `LibrarySearch`:
  - `loadBookMeta` must succeed for the cp1251 FB2, the KOI8-R TXT with stem `Неизвестный - Записки`, and the zipped FB2. Search counts all three books and matches authors from FB2 metadata.
  - `loadBookText` must return the decoded TXT text with its case kept, so the phrase `Уникальная фраза для поиска` and its snippet are found.
  - LibrarySearch also uses `formatFromName`, `fileStemOf` and `isSupportedBookName`.

**`readAsset` / `testHyphenation`:** `readFile` with the default `maxBytes` must return complete files.

---

## Checklist

Notation: `B(x)` means `parseFb2("<FictionBook><body>" + x + "</body></FictionBook>", doc, &err)`. Byte offsets are given in UTF-8.

### FB2 — text, blocks and spans

1. `B("<p>Hello</p>")` → returns true:
   - one `Paragraph` block, text `Hello`, level 0, no spans, `pageBreakBefore == false`, `notes == false`;
   - TOC empty, `meta.title == ""`;
   - `meta.format == "FB2"`, `meta.encoding == "UTF-8"`.
2. `B("<p>  a \n\t b  </p>")` → text `a b`.
3. `B("<p>a&#160;&#160;b</p>")` → text `a`, U+00A0, U+00A0, `b`. NBSP is kept and not collapsed.
4. `B("<p>a&#8203;b&#xFEFF;c</p>")` → text `abc`.
5. `B("<p>Все <emphasis>счастливые</emphasis> семьи</p>")` → spans `[{7,1,-1},{27,0,-1}]`.
6. `B("<p>a<a l:href=\"#n1\" type=\"note\">1</a> b</p>")` → text `a1 b`; spans `[{1,148,0},{2,0,-1}]`; `links == {"#n1"}`.
7. `B("<p><a l:href=\" http://x.org \">x</a></p>")` → `links == {"http://x.org"}` (trimmed); spans `[{0,16,0}]`.
8. `B("<p><strong>a<emphasis>b</strong>c</emphasis>d</p>")` → text `abcd`; spans `[{0,2,-1},{1,3,-1},{2,0,-1}]`.
9. `B("<p>x <emphasis>y</p><p>z</p>")` → block `z` has no spans.
10. `B("<p>a<span>b</span>c<br/>d</p>")` → text `abcd`.
11. `B("<section>loose text</section>")` → one `Paragraph`, `loose text`.
12. `B("<p>text <image l:href=\"#i\"/> more</p>")` → one `Paragraph`, `text more`; no `Image` block.

### FB2 — separators

13. Become `Separator`:
    - `<p>* * *</p>`, `<p>**</p>`, `<p>x x x</p>`, `<p>XXX</p>`, `<p>ххх</p>` (Cyrillic);
    - `<subtitle>***</subtitle>`.
14. Do not become `Separator`:
    - `<p>* *</p>`, `<p>xx</p>`, `<p>—</p>` stay `Paragraph`;
    - `<v>***</v>` stays `Verse`;
    - `<epigraph><p>***</p></epigraph>` stays `Epigraph`;
    - `<title><p>***</p></title>` stays `Title`.

### FB2 — block types and levels

15. `B("<poem><title><p>T</p></title><stanza><v>a</v><v>b</v></stanza><stanza><v>c</v></stanza><date>1830</date></poem>")` → blocks:
    - `PoemTitle` `T` (no TOC entry);
    - `Verse` `a` with `stanzaStart`; `Verse` `b` without;
    - `Verse` `c` with `stanzaStart`;
    - `TextAuthor` `1830`.
16. `B("<section><date>1830</date></section>")` → `Paragraph` `1830`.
17. `B("<epigraph><p>q</p><text-author>A</text-author></epigraph><cite><p>c</p><text-author>B</text-author></cite><p>t</p><text-author>C</text-author>")` → types and levels:
    - `Epigraph` 1, `EpigraphAuthor` 1;
    - `Cite` 1, `CiteAuthor` 1;
    - `Paragraph` 0, `TextAuthor` 0.
18. `B("<epigraph><cite><p>q</p></cite></epigraph>")` → `Epigraph` with level 2.
19. `B("<annotation><p>a</p></annotation>")` → `Annotation`.
20. `B("<p>a</p><empty-line/><p>b</p>")` → `Paragraph`, then `EmptyLine` (text `""`, adds 1 to `totalChars`), then `Paragraph`.

### FB2 — tables

21. `B("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")` →
    - `TableRow` `A | B`, spans `[{0,2,-1},{1,0,-1},{4,2,-1}]`;
    - `TableRow` `1 | 2`, no spans.
22. `B("<table><tr><td></td><td>b</td></tr></table>")` → `TableRow` `| b`.

### FB2 — sections, TOC, page breaks and anchors

23. `B("<section><title><p>A</p></title><section><title><p>B</p></title><p>x</p></section></section>")` →
    - blocks: `Title` `A` (level 1), `Title` `B` (level 2), `Paragraph` `x`;
    - TOC `[{"A",0,1},{"B",1,2}]`;
    - `meta.title == "A"`; no block has `pageBreakBefore`.
24. `B("<p>x</p><section><p>y</p></section><section><p>z</p></section>")` → `y` and `z` have `pageBreakBefore`; `x` does not.
25. Title joining:
    - `B("<title><p>Глава 1</p><p>Начало</p></title>")` → TOC title `Глава 1. Начало`, level 0;
    - with `Часть первая:` + `Детство` → `Часть первая: Детство`.
26. `B("<section id=\"s\"><title><p>T</p></title><p>x</p></section><p id=\"p\">y</p>")` → `anchors["s"] == {0,2}`, `anchors["p"] == {2,3}`.
27. `B("<p id=\"e\"/><p>z</p>")` → `anchors["e"] == {0,1}`.
28. Notes body. Input: `<FictionBook><body><p>m</p></body><body name="notes"><title><p>Notes</p></title><section id="n1"><title><p>1</p></title><p>t</p></section></body></FictionBook>`. Result:
    - blocks `m`, `Notes`, `1`, `t`; `notes` is false, true, true, true;
    - `Notes` has `pageBreakBefore`, level 0;
    - TOC is `[{"Notes",1,0}]` only;
    - `anchors["n1"] == {2,4}`.

### FB2 — images and the cover

29. Cover present and valid: the description has `<coverpage><image l:href="#c.png"/></coverpage>`, the body holds at least one paragraph, and the file has a `<binary id="c.png" content-type="image/png">` holding the 1×1 PNG of the tests. Result:
    - `blocks[0]` is `Image` with image 0; `coverImage == 0`;
    - `blocks[1].pageBreakBefore == true`;
    - `images[0]`: `mime == "image/png"`, `width == 1`, `height == 1`.
30. The same file without the binary:
    - no `Image` block; `coverImage == -1`;
    - `images.size() == 1` (id `c.png`, width 0);
    - the first block has `pageBreakBefore == true`.
31. The same file parsed with `Fb2Options{false}`: no `Image` blocks, `images` empty, `coverImage == -1`, and the first block has no page break.
32. `B("<p><image l:href=\"#i\"/>caption</p>")` with a valid binary `i` → `Image`, then `Paragraph` `caption`. If the binary is missing, only `caption` remains.
33. Base64 decoding:
    - binary text with line breaks and spaces between the base64 characters gives the same image bytes;
    - for the file-local helper itself (visible only through image bytes): `base64Decode("QUJD")` → `ABC`; `base64Decode("QQ==QUJD")` → `A`, because decoding stops at the first `=`; `-` and `_` decode like `+` and `/`.

### FB2 — description and metadata

34. Authors: `<title-info>` with authors (Лев, Толстой), (nickname `Nick`), (Лев, Толстой) → `authors == {"Лев Толстой", "Nick"}`.
35. Genres: `<genre>a</genre><genre> b </genre><genre></genre>` → `genres == {"a", "b"}`.
36. Annotation: `<annotation><p>One.</p>\n<p>Two.</p></annotation>` → `annotation == "One.\nTwo."`.
37. Series:
    - `<sequence name="  Big   Series " number="12"/>` followed by a second sequence → series `Big Series`, index 12;
    - `number="x"` → index 0.

### FB2 — encodings

38. No declaration and valid UTF-8 → `"UTF-8"`.
39. A UTF-8 BOM → `"UTF-8"`; an `FF FE` BOM with UTF-16LE content → `"UTF-16LE"`.
40. Declared `windows-1251`:
    - stored as cp1251 → `"windows-1251"`;
    - stored as UTF-8 (file under 256 KiB) with more than 16 multi-byte sequences → `"UTF-8"`, decoded correctly;
    - stored as UTF-8 with 16 or fewer multi-byte sequences → `"windows-1251"`, decoded as cp1251.

    A declaration in single quotes (`encoding='koi8-r'`) is found the same way. A declaration more than 512 bytes into the file is not found.

### FB2 — public functions

41. `parseFb2("<FictionBook><body></body></FictionBook>")` → false; `err == "No readable text was found in this FB2 file."`.
42. `parseFb2Meta` on `<FictionBook><description><title-info><lang>ru</lang></title-info></description>` → false, with `lang == "ru"`, `format == "FB2"`, `encoding == "UTF-8"`. With a `book-title` it returns true, and parsing never goes past `</description>`.
43. `fb2ExtractText` on `<FictionBook><description><title-info><book-title>T</book-title></title-info></description><body><section><p>Hello <emphasis>big</emphasis> world</p><p>Second</p></section></body><binary id="b">QUJD</binary></FictionBook>` → text `"T\nHello big world\nSecond\n"`; `meta->title == "T"`.

### TXT

44. `detectTxtParagraphMode` returns:
    - `BlankLines` for `"a\n\nb\n\nc"`;
    - `Indented` for 10 lines, 5 of them starting with 4 spaces, no blank lines;
    - `EveryLine` for 10 lines that are all indented;
    - `EveryLine` for `"\n\n"`;
    - `EveryLine` for 20 non-blank lines with 2 single blank lines among them.
45. `guessMetaFromFileStem`:
    - `"Толстой - Анна Каренина"` → author `Толстой`, title `Анна Каренина`;
    - `"Tolstoy_-_Anna_Karenina"` → `Tolstoy` / `Anna Karenina`;
    - `"Tolstoy--War and Peace"` → `Tolstoy` / `War and Peace`;
    - `"Anna_Karenina"` → title `Anna Karenina`, no author;
    - `" - Title"` → title `- Title`, no author;
    - when the title is already set, only an empty author is filled.
46. `parseTxt("Глава 1\nПервая строка.\nВторая строка.\n", d, "x")` →
    - blocks: `Title` `Глава 1` (level 1, no page break), `Paragraph`, `Paragraph`;
    - TOC `[{"Глава 1",0,1}]`;
    - `meta.title == "x"`, `format == "TXT"`, `encoding == "UTF-8"`.
47. `"Часть 1\nтекст\nГлава 2\nтекст\nЧасть 3\nтекст"` → title levels 1, 2, 1; `pageBreakBefore` false, false, true.
48. `"Глава 1\nтекст\nЧасть 2\nтекст\nГлава 3\nтекст"` → title levels 1, 1, 2; `pageBreakBefore` false, true, false.
49. Heading recognition for single-line paragraphs:
    - **Headings:** `Глава 1`, `ГЛАВА ПЕРВАЯ`, `Chapter XIV.`, `CHAPTER I`, `Part One`, `Book 2`, `Том 1`, `Act 3`, `Letter 4`, `Stave I`, `Пролог`, `Пролог.`, `Prologue`, `Contents`, `Оглавление`, `От автора`, `XIV`, `I`, `12.`, `7:`.
    - **Not headings:** `Chapter`, `Главами`, `Actually`, `Prologue, continued`, `2024`, `xiv`, `Book of Ruth`, and a 61-code-point line starting `Introduction `.
50. Separator lines:
    - `* * *`, `*`, `---`, `===`, `___`, `~~~`, `• • •` → `Separator`;
    - `—` → `Paragraph` `—`;
    - `-` → `Paragraph` `—` (the dash fix);
    - `##` → `Paragraph`;
    - `XXX` → `Title` (bare roman numeral).
51. Dash fixes in paragraphs:
    - `a--b` → `a—b`; `a---b` → `a—b`; `a----b` → `a-—b`;
    - `a - b` → `a — b`; `- Да.` → `— Да.`; `word -` → `word —`;
    - `сказал,- он` → `сказал, — он`;
    - unchanged: `по-своему`, `-5`.
52. With the Gutenberg marker:
    - `It is _very_ good` → `It is very good`, spans `[{6,1,-1},{10,0,-1}]`;
    - `_all italic` → `all italic`, spans `[{0,1,-1}]`;
    - `snake_case` → unchanged.

    Without the marker, underscores are kept.
53. Wrapped text: 8 lines of 60 ASCII characters (no hyphens, no headings), where line 4 has only 20 → 2 paragraphs, lines 1–4 and 5–8 (wrap 60, `shortLimit` 42).
54. In a wrapped text, `…con-` + `tinue…` joins to `con-tinue`, and `…Москва-` + `Река…` joins to `Москва- Река`.
55. Scene breaks:
    - `"Alpha.\n\nBeta.\n\n\nGamma."` → `Paragraph`, `Paragraph`, `EmptyLine`, `Paragraph`;
    - in `EveryLine` mode (4 lines, 1 blank line, 3 lines) → 4 paragraphs, `EmptyLine`, 3 paragraphs;
    - `"Глава 1\n\n\nтекст"` → `Title`, `Paragraph`, with no `EmptyLine`.
56. Form feed and control characters: `"a\fb"` splits into lines `a`, blank, `b`; `"a\x01b"` → `ab`.
57. Gutenberg header and markers: `"Title: T\nAuthor: A\nLanguage: English\n*** START OF X ***\nText.\n*** END OF X ***\nLicense"` →
    - title `T`, authors `{"A"}`, lang `English`;
    - a single block `Text.`.

    A START marker beginning after byte 60000 is not recognised.
58. `parseTxt("")` and `parseTxt("  \n\t\n")` → false; `err == "The text file is empty."`.
59. `txtExtractText` on cp1251 bytes → UTF-8 text with its original line breaks; `meta.encoding == "windows-1251"`, `meta.format == "TXT"`.

### Book loader

60. `formatFromName` returns:
    - `Fb2Zip` for `a.FB2.ZIP`, `TxtZip` for `a.txt.zip`, `Zip` for `a.zip`;
    - `Fb2` for `a.fb2`, `Txt` for `a.TXT`, `Txt` for `a.fb2.txt`;
    - `Unknown` for `a.epub`.
61. `fileNameOf` returns `a.fb2` for `C:\books\a.fb2`, `b.txt` for `dir/sub/b.txt`, and `plain` for `plain`.
62. `fileStemOf` returns:
    - `Book` for `/x/Book.fb2.zip` and for `Book.FB2`;
    - `a.zip` for `a.zip.zip.zip`;
    - `.fb2` for `.fb2`;
    - `Book.epub` for `Book.epub`.
63. Round trip: `pathToUtf8(pathFromUtf8("Загрузки/книга.fb2")) == "Загрузки/книга.fb2"`.
64. `readFile` on a 300 MiB file → true with exactly 268 435 456 bytes. On a missing file → false, `"Cannot open the file."`.
65. `readBookRaw`:
    - a zip renamed `book.fb2` → unzipped, `*zipped == true`;
    - `book.zip` that is not a zip → false, `"The file is not a valid zip archive."`;
    - a `.txt` (or unknown extension) whose first 4096 bytes contain `<FictionBook` → `Fb2`.
66. Choosing the zip entry:
    - `a.txt` (10 B), `b.txt` (20 B), `c.fb2` → `c.fb2`;
    - only the two `.txt` entries → `b.txt`;
    - two `.fb2` entries → the first one;
    - only `readme.md` → false, `"The archive does not contain an FB2 or TXT book."`;
    - a garbage file starting with `PK\3\4` → `"The zip archive is damaged or unsupported."`.
67. `loadBook`:
    - a zipped FB2 → `meta.format == "FB2 (zip)"`; a zipped TXT → `"TXT (zip)"`;
    - for `___.txt`, the stem guess collapses to an empty title, so `loadBook` sets `title == "___"` from `fileStemOf`;
    - when reading fails, `doc` is left untouched.
68. `loadBookMeta` returns true for an FB2 without title or author, with `title == fileStemOf(path)`. For a TXT it uses only the first 65 536 bytes.
69. `bookFingerprint`:
    - empty file → `14650fb0739d0383-0`;
    - file `a` → `44bd8ad473cd9906-1`;
    - file `abc` → `e16801510db89efd-3`;
    - a 100 000-byte file → the hash of its first 65 536 bytes, then `-186a0`;
    - missing file → `""`.
