# 07 — Fonts, shaping and the book layout engine

This file specifies three implementation files of the text layer. `src/text/FontLibrary.cpp` loads font faces with
FreeType and HarfBuzz and measures them. `src/text/Shaper.cpp` turns UTF-8 strings into cached, resolution-independent
glyph runs with per-character font fallback. `src/text/BookLayout.cpp` is the reflowable layout engine: document blocks
become box/glue/penalty items, the items become broken and justified lines of positioned glyph runs, and the lines
become pages, built forwards or backwards from any position, counted in the background and hit-tested. The
declarations are in the verbatim headers `src/text/FontLibrary.h`, `src/text/Shaper.h` and `src/text/BookLayout.h`
(ai/files/02-source-interfaces.md), which this file does not restate. The helpers these files call are specified
elsewhere: UTF-8 and character classes (`utf8Decode`, `isLetterCp`, `isDigitCp`, `isCombiningMarkCp`, `kNbsp`,
`kSoftHyphen`) and the document model (`spanFlagsAt`, `isWebLink`, `Document::finalize`) in spec 03; `readFile` and
`fileNameOf` in spec 04; `HyphenationService` and the line breaker (`breakLinesOptimal`, `breakLinesGreedy`,
`lbLineWidth`, `LbItem`, `LbParams`, `kLbInfPenalty` = 10000, `kLbFillStretch` = 100000) in spec 05; glyph
rasterisation and run drawing in spec 08; the application that drives the engine in spec 09.

## 1. Conventions

- **Units.** *em*: a multiple of the font size (all `FontFace` metrics, `ShapedGlyph` and `ShapedRun` values).
  *px*: framebuffer pixels (`LayoutParams` and everything in `BlockLayout`, `BlockMetrics`, `Page`). *Offset*: a byte
  offset into `Block::text` (UTF-8).
- **Arithmetic.** Layout arithmetic is `float`, with the expressions below evaluated as written. `std::round` rounds
  halves away from zero. The line breaker computes internally in `double` (spec 05).
- Everything is in namespace `ll` and runs on one thread (the UI thread); there is no locking and no global state.
- File-local definitions: only the helpers in BookLayout.cpp's anonymous namespace (§4.2) and the struct
  `BookLayout::BlockStyle` (forward-declared in the header, defined in BookLayout.cpp).

---

## 2. `src/text/FontLibrary.cpp`

Includes: `"text/FontLibrary.h"`, `<ft2build.h>`, `FT_FREETYPE_H`, `FT_TRUETYPE_TABLES_H`, `<hb.h>`, `<cmath>`,
`"core/BookLoader.h"` (for `readFile`, `fileNameOf`).

### 2.1 Purpose

`FontLibrary` owns the FreeType library handle and every loaded face. Each face is used in two ways: HarfBuzz shapes
with it (`hbFont`, scaled to font units), and FreeType rasterises its glyphs (`ft`, sized by `setPixelSize` for the
glyph atlas, spec 08). Each face also stores the few metrics the layout needs, in em.

### 2.2 `FontFace::hasChar(cp)`

`return ft && FT_Get_Char_Index(ft, cp) != 0;`. It looks the character up in FreeType's selected charmap, which is
the Unicode charmap selected at load time. The Shaper uses it to choose fallback faces.

### 2.3 Constructor and destructor

- `FontLibrary()`: `FT_Init_FreeType(&lib_)`. If it returns non-zero, set `lib_ = nullptr`: `ok()` is then false and
  every add returns -1.
- `~FontLibrary()`: for each face in order, `hb_font_destroy(hbFont)`, then `hb_face_destroy(hbFace)`, then
  `FT_Done_Face(ft)`, each only when non-null. Then `faces_.clear()`, then `FT_Done_FreeType(lib_)` if `lib_` is
  non-null.

### 2.4 `addFromFile(utf8Path, faceIndex)`

Read the whole file with `readFile(utf8Path, bytes)` (default arguments). Return -1 if reading fails or the file is
empty. Otherwise return `addFromMemory(std::vector<unsigned char>(bytes.begin(), bytes.end()), fileNameOf(utf8Path),
faceIndex)`. The face's `name` is therefore the file name without its directories, e.g. `PTSerif-Regular.ttf`.

### 2.5 `addFromMemory(data, name, faceIndex)`

Returns the new face id (its index in `faces_`) or -1. Ids are dense and only faces that load get one; a failed load
uses no id.

1. `if (!lib_ || data.empty()) return -1;`
2. Create the `FontFace` with `std::make_unique<FontFace>()`, set `name` and move `data` in. The heap object never
   moves afterwards, so FreeType and HarfBuzz can point into `data` without copying it.
3. `FT_New_Memory_Face(lib_, f->data.data(), static_cast<FT_Long>(f->data.size()), faceIndex, &f->ft)`. Non-zero →
   return -1.
4. `if (!FT_IS_SCALABLE(f->ft))`: call `FT_Done_Face(f->ft)` and return -1. Bitmap-only fonts are refused.
5. `FT_Select_Charmap(f->ft, FT_ENCODING_UNICODE);` (result ignored).
6. Create the HarfBuzz objects over the same bytes, without a copy:
   ```cpp
   hb_blob_t* blob = hb_blob_create(reinterpret_cast<const char*>(f->data.data()),
                                    static_cast<unsigned>(f->data.size()), HB_MEMORY_MODE_READONLY, nullptr, nullptr);
   f->hbFace = hb_face_create(blob, static_cast<unsigned>(faceIndex));
   hb_blob_destroy(blob);
   f->hbFont = hb_font_create(f->hbFace);
   ```
   `hb_font_create` installs HarfBuzz's built-in OpenType font functions. The code never uses hb-ft and never sets a
   ppem, ptem or variation coordinates.
7. `f->upem = static_cast<int>(hb_face_get_upem(f->hbFace));`. If `upem <= 0`, use `f->ft->units_per_EM` when it is
   `> 0`, else 1000.
8. `hb_font_set_scale(f->hbFont, f->upem, f->upem);`. HarfBuzz then reports positions and advances in font units,
   which are converted to em by dividing by `upem`.
9. Vertical metrics and advances (verbatim):
   ```cpp
   const float inv = 1.0f / static_cast<float>(f->upem);
   FT_Face ft = f->ft;
   float asc = static_cast<float>(ft->ascender);
   float desc = static_cast<float>(-ft->descender);
   if (const TT_OS2* os2 = static_cast<const TT_OS2*>(FT_Get_Sfnt_Table(ft, FT_SFNT_OS2))) {
     if (os2->fsSelection & (1 << 7)) {  // USE_TYPO_METRICS
       asc = static_cast<float>(os2->sTypoAscender);
       desc = static_cast<float>(-os2->sTypoDescender);
     }
     if (os2->version >= 2 && os2->sxHeight > 0) f->xHeight = os2->sxHeight * inv;
     if (os2->version >= 2 && os2->sCapHeight > 0) f->capHeight = os2->sCapHeight * inv;
   }
   if (asc > 0) f->ascender = asc * inv;
   if (desc > 0) f->descender = desc * inv;

   auto advanceOf = [&](char32_t cp, float fallback) {
     hb_codepoint_t g = 0;
     if (!hb_font_get_nominal_glyph(f->hbFont, cp, &g)) return fallback;
     return static_cast<float>(hb_font_get_glyph_h_advance(f->hbFont, g)) * inv;
   };
   f->spaceAdvance = advanceOf(U' ', 0.25f);
   f->hyphenAdvance = advanceOf(U'-', 0.33f);
   ```
   In words:
   - Ascender and descender start as FreeType's `FT_Face::ascender` and the negated `FT_Face::descender` (font units,
     as FreeType reports them; for OpenType fonts normally the hhea values). If the OS/2 table exists and
     `fsSelection` bit 7 (USE_TYPO_METRICS) is set, `sTypoAscender` and `-sTypoDescender` replace them.
   - A value replaces the header default (0.8 / 0.2 em) only when it is positive.
   - `xHeight` and `capHeight` come from OS/2 version ≥ 2 when positive; otherwise they keep 0.5 / 0.7 em. No other
     code currently reads them. Line gaps are never read.
   - `spaceAdvance` and `hyphenAdvance` are the unhinted horizontal advances of the nominal glyphs for U+0020 and
     U+002D, in em. A font without the character gets 0.25 / 0.33 em.
10. `faces_.push_back(std::move(f)); return static_cast<int>(faces_.size()) - 1;`

### 2.6 `setPixelSize(id, sizePx)`

```cpp
FontFace& f = face(id);
const uint32_t s = static_cast<uint32_t>(std::lround(sizePx * 64.0f));
if (f.currentSize26_6 == s) return;
FT_Set_Char_Size(f.ft, 0, static_cast<FT_F26Dot6>(s), 72, 72);
f.currentSize26_6 = s;
```
The size is in 26.6 fixed point. A char width of 0 means "the same as the height". At 72 dpi in both directions a
point equals a pixel. The FreeType result is ignored, and the cached size is updated anyway. Only the glyph atlas
calls this function, with sizes quantised to quarter pixels (spec 08). Shaping and layout never depend on the
FreeType size.

---

## 3. `src/text/Shaper.cpp`

Includes: `"text/Shaper.h"`, `<hb.h>`, `"core/Unicode.h"`.

### 3.1 Purpose and cache

`shape(utf8, style)` turns a UTF-8 string into a `ShapedRun` in em units. The run holds one `ShapedGlyph` per HarfBuzz
output glyph (face id, glyph id, pen position x/y in em relative to the run origin) and the total advance. Because
the result does not depend on the font size, it is cached. `cache_` maps a key string to the run, and the returned
reference stays valid until `clear()`: `std::unordered_map` nodes do not move when entries are added, and
`PlacedRun::run` in the layout points into this cache. There is no eviction; the app clears a book shaper that holds
more than 150000 entries when it opens a book (spec 09). The family must be valid (`faces[0] >= 0`) before anything is
shaped or measured.

### 3.2 Small members

- Constructor: stores the library reference and sets `buf_ = hb_buffer_create()`. Destructor: `hb_buffer_destroy(buf_)`
  if non-null. The one buffer is reused for every segment.
- `setFamily(family)`: `family_ = family; clear();`. `setFallbacks`, which is inline in the header, does **not**
  clear the cache.
- `clear()`: `cache_.clear()`.
- `spaceWidth(style)` returns `primary(style).spaceAdvance` and `hyphenWidth(style)` returns
  `primary(style).hyphenAdvance`, both in em. They always use the primary face of that style, never a fallback face.

### 3.3 `pickFace(cp, primaryFace)`

```cpp
if (cp == U' ' || cp == kNbsp || lib_.face(primaryFace).hasChar(cp)) return primaryFace;
for (int f : fallbacks_) {
  if (f >= 0 && f < lib_.count() && lib_.face(f).hasChar(cp)) return f;
}
return primaryFace;
```
U+0020 SPACE and U+00A0 NO-BREAK SPACE always use the primary face. Any other character uses the primary face if that
face has it. Otherwise it uses the first face in `fallbacks_` order that has it, skipping ids outside
`[0, lib_.count())`. If no face has it, it uses the primary face, which then draws its .notdef glyph.

### 3.4 `shape(text, style)`

1. Key: `key_.assign(1, static_cast<char>('0' + (style & 3))); key_.append(text);`, i.e. one ASCII digit `'0'`..`'3'`
   followed by the text's bytes. `style` and `style + 4` therefore share entries. If the key is in the cache, return
   the cached run.
2. Split the text into font segments and shape each one (verbatim):
   ```cpp
   ShapedRun run;
   const int primaryFace = family_.face(style);
   float x = 0;
   int curFace = -1;
   size_t segStart = 0;
   size_t i = 0;
   while (i < text.size()) {
     const size_t st = i;
     const char32_t cp = utf8Decode(text, i);
     int f;
     if (curFace >= 0 && (isCombiningMarkCp(cp) || cp == 0x200D || cp == 0xFE0F || cp == 0xFE0E)) {
       f = curFace;  // marks stay with their base character
     } else {
       f = pickFace(cp, primaryFace);
     }
     if (f != curFace) {
       if (curFace >= 0) shapeSegment(text, segStart, st, curFace, x, run);
       curFace = f;
       segStart = st;
     }
   }
   if (curFace >= 0) shapeSegment(text, segStart, text.size(), curFace, x, run);
   run.advance = x;
   return cache_.emplace(key_, std::move(run)).first->second;
   ```
   - A segment is a maximal run of consecutive code points that chose the same face.
   - Combining marks (`isCombiningMarkCp`), U+200D ZERO WIDTH JOINER, U+FE0F VARIATION SELECTOR-16 and U+FE0E
     VARIATION SELECTOR-15 keep the face of the current segment rather than choosing their own. At the very start of
     the text there is no segment yet, so a leading mark goes through `pickFace`.
   - Spaces always go to the primary face, so a run of fallback characters is split at every space. Each part is
     shaped on its own, and the spaces are shaped with the primary face.
   - `run.advance` is the sum of all x advances. An empty text gives a run with no glyphs and advance 0, which is also
     cached.

### 3.5 `shapeSegment(text, begin, end, faceId, x, out)`

1. `hb_buffer_clear_contents(buf_)` empties the buffer and resets its segment properties.
2. `hb_buffer_add_utf8(buf_, text.data(), static_cast<int>(text.size()), static_cast<unsigned>(begin),
   static_cast<int>(end - begin))`. The whole text is passed and `[begin, end)` is the item, so HarfBuzz sees the
   neighbouring characters as context.
3. `hb_buffer_guess_segment_properties(buf_)`, then `hb_buffer_set_direction(buf_, HB_DIRECTION_LTR)`. The script is
   guessed from the item's characters. The language is HarfBuzz's default language, taken from the process locale;
   the code never sets one. The direction is always left to right: there is no bidi and no RTL.
4. `hb_shape(face.hbFont, buf_, nullptr, 0)`: no user features, so HarfBuzz applies its defaults (kerning, standard
   ligatures, mark positioning, contextual alternates and so on). Cluster level and buffer flags stay at their
   defaults.
5. Read the glyph infos and positions. With `inv = 1.0f / static_cast<float>(face.upem)`, first
   `out.glyphs.reserve(out.glyphs.size() + n)`, then append for each output glyph k in order:
   ```cpp
   g.face = static_cast<uint16_t>(faceId);
   g.glyph = static_cast<uint16_t>(info[k].codepoint);
   g.x = x + pos[k].x_offset * inv;
   g.y = pos[k].y_offset * inv;
   x += pos[k].x_advance * inv;
   ```
   `y_advance` is ignored. Positive y is up, as in HarfBuzz. `x` carries on into the next segment.

---

## 4. `src/text/BookLayout.cpp`

Includes: `"text/BookLayout.h"`, `<algorithm>`, `<chrono>`, `<cmath>`, `"core/LineBreaker.h"`, `"core/Unicode.h"`.

### 4.1 Purpose, terms and coordinates

`BookLayout` lays out one `Document` for one `LayoutParams`. The unit of layout is the block: each
`Document::blocks[i]` becomes a `BlockLayout` (its lines with positioned runs, or a picture). A `BlockMetrics` is
extracted from it: line heights, line start offsets, spacing and the two pagination flags. Pagination needs only the
metrics; drawing and hit testing need the full layouts. A position is a `LinePos{block, line}`. A page is built on
demand from any position, forwards (`pageFrom`) or backwards (`pageStartBefore`), so after a change only the blocks
around the reading position are laid out. `countStep` paginates the whole book in time slices to give page numbers.

Terms used below:
- *word*: a maximal run of bytes other than U+0020 in `Block::text`.
- *cut*: a byte offset strictly inside a word where the word may be split, together with its kind (§4.6.4).
- *piece*: the bytes between two consecutive bounds of a word (word start, cuts, starts of style spans inside the
  word, word end). Each piece is shaped separately.
- *fragment* (`Frag`): a shaped piece.
- *item*: an `LbItem` (box, glue or penalty) for the line breaker.

Coordinates:
- `PlacedRun::x` is px from the left edge of the text column, with the block's margins included.
- `PlacedRun::baseline` is px from the top of its line.
- `PageLine::y` is px from the top of the page.
- The `BlockLayout` image fields are px from the column's left edge and the line's top.

### 4.2 File-local definitions

```cpp
struct BookLayout::BlockStyle {
  enum Align : uint8_t { Left, Center, Right, Justify };
  float scale = 1.f;
  uint8_t flags = 0;
  Align align = Justify;
  float indent = 0;          // em of this block's size
  float hang = 0;            // em, indent of continuation lines (verse)
  float marginLeft = 0;      // em of the base size
  float marginRight = 0;     // em of the base size
  float marginLeftFrac = 0;  // fraction of the column width (epigraphs)
  float before = 0;          // em of the base size
  float after = 0;
  bool hyphenate = true;
  bool keepWithNext = false;
  float maxLineSpacing = 0;  // titles use tighter leading
};
```

Anonymous namespace:

```cpp
int styleIndex(uint8_t flags) { return ((flags & kSpanBold) ? 2 : 0) | ((flags & kSpanItalic) ? 1 : 0); }
float runScale(uint8_t flags) { return (flags & (kSpanSup | kSpanSub)) ? 0.68f : 1.0f; }

// "—", "–" possibly followed by punctuation: a dash that must not start a line.
bool isDashWord(std::string_view w) {
  if (w.empty()) return false;
  size_t i = 0;
  const char32_t c = utf8Decode(w, i);
  if (c != 0x2014 && c != 0x2013 && c != 0x2015) return false;
  while (i < w.size()) {
    const char32_t d = utf8Decode(w, i);
    if (isLetterCp(d) || isDigitCp(d)) return false;
  }
  return true;
}
```
A dash word starts with U+2014 EM DASH, U+2013 EN DASH or U+2015 HORIZONTAL BAR, and none of its other code points is a
letter or a digit: "—", "–,", "―…" are dash words, "—Да" is not.

`BlockMetrics extractMetrics(const BlockLayout& bl)` copies every line's `height` into `lineHeights` and its `start`
into `lineStarts`, in line order, plus `spaceBefore`, `spaceAfter`, `keepWithNext` and `pageBreakBefore`.

Span flags in layout:
- Only the Bold and Italic bits choose a face. Only Sup and Sub change size and baseline.
- Link marks web addresses (§4.6.4). The span's link index becomes `PlacedRun::link`, used for hit testing.
- Link and NoteRef are removed from the flags of drawn hyphens (§4.6.8).
- Code and Strike have no effect on layout.

All flags are still carried in `PlacedRun::flags` for drawing (spec 08/09).

### 4.3 Document, parameters, invalidation

**`setDocument(doc)`**: `doc_ = doc; invalidate();`.

**`invalidate()`**: drops everything that depends on the document or the parameters:
```cpp
full_.clear();
metrics_.clear();
metrics_.resize(static_cast<size_t>(blockCount()));   // one null slot per block
pageStarts_.clear();
countPos_ = LinePos{};
countDone_ = false;
countStarted_ = false;
otherHeight_ = Pagination{};                          // pageHeight -1: no other height remembered
```
`keepFull_` is left unchanged. `PlacedRun::run` points into the Shaper's cache, so the app calls `invalidate()` (or
`setDocument`) whenever that cache has been cleared.

**`setParams(p)`**:
1. If `p == params_` (the defaulted member-wise `==`, exact float comparison), return.
2. Copy both parameter sets, set `pageHeight = 0` in both copies and compare. If they are equal (only the page height
   differs) **and** `doc_` is non-null, take the page-height path:
   - Save the current count as `Pagination current{params_.pageHeight, std::move(pageStarts_), countPos_, countDone_,
     countStarted_}`, then set `params_ = p`.
   - For each `i < min(doc_->blocks.size(), metrics_.size())` whose block type is `Image`: `full_.erase(i)` and
     `metrics_[i].reset()`. Pictures are scaled to the page height; text lines do not depend on it and are kept.
   - If `otherHeight_.pageHeight == p.pageHeight`, restore the count of that height: move `starts` into
     `pageStarts_` and copy `pos`, `done` and `started` into `countPos_`, `countDone_` and `countStarted_`.
     Otherwise reset the count: `pageStarts_.clear()`, `countPos_ = {}`, `countDone_ = false`,
     `countStarted_ = false`.
   - `otherHeight_ = std::move(current);`, then return.
3. Otherwise `params_ = p; invalidate();`. Any change other than the page height is a full invalidate, and so is
   any change while no document is set. A full invalidate also forgets the other height.

Only one other height is remembered. Toggling between two heights (menu bars shown or hidden) restores the finished
count at once. A third height starts a fresh count.

### 4.4 Block styles: `styleFor(b)`

Start from the `BlockStyle` defaults; `body` is `params_.justify ? Justify : Left`.
- The block's font size is `scale × params_.fontSize`.
- `indent` and `hang` are em of the block's font size.
- `marginLeft`, `marginRight`, `before` and `after` are em of the base size `params_.fontSize`.
- `marginLeftFrac` is a fraction of the column width.

After the switch, two global rules apply: `if (!params_.hyphenate) s.hyphenate = false;` and
`if (b.notes) s.scale *= 0.92f;`. EmptyLine and Image blocks never reach `styleFor` (§4.5); they would get the
defaults. A Separator block (its text is e.g. "* * *") is laid out as ordinary centred text; nothing is drawn
specially for it. A TableRow is laid out as ordinary left-aligned text that may wrap; the layout knows nothing
of table cells.

| BlockType | scale | flags | align | indent | hang | marginLeft | marginRight | marginLeftFrac | before | after | hyphenate | keepWithNext | maxLineSpacing |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Paragraph | 1 | – | body | paragraphIndent | 0 | 0 | 0 | 0 | paragraphSpacing | 0 | yes | no | 0 |
| Title | kScale[min(level,6)] | Bold | Center | 0 | 0 | 0 | 0 | 0 | level 0: 1.6, else 1.3 | 0.9 | no | yes | 1.25 |
| Subtitle | 1.05 | Bold | Center | 0 | 0 | 0 | 0 | 0 | 0.9 | 0.6 | no | yes | 0 |
| Epigraph | 0.95 | Italic | body | 0 | 0 | 0 | 0 | 0.33 | 0.2 | 0 | yes | no | 0 |
| EpigraphAuthor | 0.95 | Bold+Italic | Right | 0 | 0 | 0 | 0 | 0.33 | 0.2 | 1.0 | no | no | 0 |
| PoemTitle | 1 | Bold | Left | 0 | 0 | 2.0 | 0 | 0 | 0.9 | 0.4 | no | yes | 0 |
| Verse | 1 | – | Left | 0 | 1.5 | 2.0 | 0 | 0 | stanzaStart ? 0.8 : 0 | 0 | no | no | 0 |
| Cite | 0.95 | – | body | paragraphIndent | 0 | 2.0 | 1.0 | 0 | 0 | 0 | yes | no | 0 |
| CiteAuthor | 0.95 | Italic | Right | 0 | 0 | 2.0 | 0 | 0 | 0 | 0.6 | no | no | 0 |
| TextAuthor | 1 | Italic | Right | 0 | 0 | 0 | 0 | 0 | 0.3 | 0.6 | no | no | 0 |
| Annotation | 1 | Italic | body | paragraphIndent | 0 | 0 | 0 | 0 | 0 | 0 | yes | no | 0 |
| Separator | 1 | – | Center | 0 | 0 | 0 | 0 | 0 | 0.8 | 0.8 | no | no | 0 |
| TableRow | 0.95 | – | Left | 0 | 0 | 0 | 0 | 0 | 0.2 | 0 | yes | no | 0 |

The table in the source (verbatim):

```cpp
BookLayout::BlockStyle BookLayout::styleFor(const Block& b) const {
  BlockStyle s;
  const BlockStyle::Align body = params_.justify ? BlockStyle::Justify : BlockStyle::Left;
  switch (b.type) {
    case BlockType::Paragraph:
      s.align = body;
      s.indent = params_.paragraphIndent;
      s.before = params_.paragraphSpacing;
      break;
    case BlockType::Title: {
      static const float kScale[] = {1.6f, 1.4f, 1.25f, 1.15f, 1.1f, 1.05f, 1.0f};
      s.scale = kScale[std::min<int>(b.level, 6)];
      s.flags = kSpanBold;
      s.align = BlockStyle::Center;
      s.before = b.level == 0 ? 1.6f : 1.3f;
      s.after = 0.9f;
      s.hyphenate = false;
      s.keepWithNext = true;
      s.maxLineSpacing = 1.25f;
      break;
    }
    case BlockType::Subtitle:
      s.scale = 1.05f;
      s.flags = kSpanBold;
      s.align = BlockStyle::Center;
      s.before = 0.9f;
      s.after = 0.6f;
      s.hyphenate = false;
      s.keepWithNext = true;
      break;
    case BlockType::Epigraph:
      s.scale = 0.95f;
      s.flags = kSpanItalic;
      s.align = body;
      s.marginLeftFrac = 0.33f;
      s.before = 0.2f;
      break;
    case BlockType::EpigraphAuthor:
      s.scale = 0.95f;
      s.flags = kSpanBold | kSpanItalic;
      s.align = BlockStyle::Right;
      s.marginLeftFrac = 0.33f;
      s.before = 0.2f;
      s.after = 1.0f;
      s.hyphenate = false;
      break;
    case BlockType::PoemTitle:
      s.flags = kSpanBold;
      s.align = BlockStyle::Left;
      s.marginLeft = 2.0f;
      s.before = 0.9f;
      s.after = 0.4f;
      s.hyphenate = false;
      s.keepWithNext = true;
      break;
    case BlockType::Verse:
      s.align = BlockStyle::Left;
      s.marginLeft = 2.0f;
      s.hang = 1.5f;
      s.before = b.stanzaStart ? 0.8f : 0.f;
      s.hyphenate = false;
      break;
    case BlockType::Cite:
      s.scale = 0.95f;
      s.align = body;
      s.marginLeft = 2.0f;
      s.marginRight = 1.0f;
      s.indent = params_.paragraphIndent;
      break;
    case BlockType::CiteAuthor:
      s.scale = 0.95f;
      s.flags = kSpanItalic;
      s.align = BlockStyle::Right;
      s.marginLeft = 2.0f;
      s.after = 0.6f;
      s.hyphenate = false;
      break;
    case BlockType::TextAuthor:
      s.flags = kSpanItalic;
      s.align = BlockStyle::Right;
      s.before = 0.3f;
      s.after = 0.6f;
      s.hyphenate = false;
      break;
    case BlockType::Annotation:
      s.flags = kSpanItalic;
      s.align = body;
      s.indent = params_.paragraphIndent;
      break;
    case BlockType::Separator:
      s.align = BlockStyle::Center;
      s.before = 0.8f;
      s.after = 0.8f;
      s.hyphenate = false;
      break;
    case BlockType::TableRow:
      s.scale = 0.95f;
      s.align = BlockStyle::Left;
      s.before = 0.2f;
      break;
    default:
      break;
  }
  if (!params_.hyphenate) s.hyphenate = false;
  if (b.notes) s.scale *= 0.92f;
  return s;
}
```

### 4.5 `layoutBlock(index)`

Returns a new `BlockLayout` for `doc_->blocks[index]`. `out.pageBreakBefore = b.pageBreakBefore` for every type, and
`base = params_.fontSize`.

- **EmptyLine**: one line with `height = std::round(base * params_.lineSpacing)`, no runs, `start = end = 0`. Spacing
  is 0, `keepWithNext` is false, and `notes` makes no difference.
- **Image**: one line, initially height 0 with no runs. If `0 <= b.image < doc_->images.size()` and that image's
  `width > 0`:
  ```cpp
  const ImageData& img = doc_->images[static_cast<size_t>(b.image)];
  const bool cover = b.image == doc_->coverImage && index == 0;
  const float w = static_cast<float>(img.width), h = static_cast<float>(img.height);
  const float maxH = params_.pageHeight * (cover ? 1.0f : 0.92f);
  float scale = std::min(params_.pageWidth / w, maxH / h);
  if (!cover) scale = std::min(scale, std::max(1.0f, base / 16.0f));
  out.image = b.image;
  out.imageW = std::floor(w * scale);
  out.imageH = std::floor(h * scale);
  out.imageX = std::floor((params_.pageWidth - out.imageW) * 0.5f);
  if (cover) {
    l.height = std::floor(params_.pageHeight);
    out.imageY = std::floor((l.height - out.imageH) * 0.5f);
  } else {
    l.height = out.imageH;
    out.spaceBefore = 0.6f * base;
    out.spaceAfter = 0.6f * base;
  }
  ```
  - The cover is the document's cover image, and only when it is block 0. It fills the page: its line is the whole
    page height, it may be scaled up without limit, it is centred both ways, and it has no spacing.
  - Any other picture fits the column width and 92 % of the page height. It is scaled up by at most `base / 16`
    (never above 1:1 for fonts up to 16 px), centred horizontally at `imageY = 0`, its line as tall as the picture,
    with 0.6 em of base spacing above and below.
  - An invalid or unknown image gives a zero-height line with `image = -1`. The block's text is ignored, `styleFor`
    is not used, and `keepWithNext` is false.
- **Every other type**: `st = styleFor(b)`, `out.spaceBefore = st.before * base`, `out.spaceAfter = st.after * base`,
  `out.keepWithNext = st.keepWithNext`, then `layoutText(b, st, out)`. If no lines resulted (which does not happen,
  because the breakers always return at least one line), add one empty line of height
  `std::round(base * st.scale * params_.lineSpacing)`.

Worked examples (W 420, H 600, base 20): a 200×100 picture gives scale min(2.1, 5.52, 1.25) = 1.25, so 250×125 at
x 85, line height 125, spacing 12 + 12. A 400×800 cover gives scale min(1.05, 0.75) = 0.75, so 300×600 at x 60,
y 0, line height 600.

### 4.6 `layoutText(b, st, out)`

Turns the block's text into lines and appends them to `out.lines`.

#### 4.6.1 Geometry

```cpp
const float base = params_.fontSize;
const float size = base * st.scale;                       // the block's font size, px
float ls = params_.lineSpacing;
if (st.maxLineSpacing > 0) ls = std::min(ls, st.maxLineSpacing);
const float lineH = std::max(1.0f, std::round(size * ls)); // every line of the block has this height
const float W = params_.pageWidth;
float left = st.marginLeft * base + std::min(st.marginLeftFrac * W, 12.0f * base);
float right = st.marginRight * base;
float avail = W - left - right;
if (avail < base * 8) {  // very narrow column: drop decorative margins
  left = right = 0;
  avail = W;
}
const float indent = st.indent * size;
const float hang = std::min(st.hang * size, avail * 0.3f);
std::vector<float> widths{avail};
if (hang > 0) widths.push_back(avail - hang);              // line 0, then every later line

const FontFace& pf = shaper_.primary(styleIndex(st.flags));
const float baseline = std::round((lineH - (pf.ascender + pf.descender) * size) * 0.5f + pf.ascender * size);
```
- The ascender + descender box of the block style's primary face is centred in the line, and the baseline is rounded
  to a whole pixel.
- Line height and baseline are the same for every line of the block, whatever the runs contain. Spans in other
  styles, sup/sub and fallback fonts never change a line's height or baseline, so mixed sizes have no effect on
  leading.
- Examples at base 20, lineSpacing 1.35:
  - Paragraph: size 20, lineH 27, indent 30 px.
  - Title level 1: size 28, ls 1.25, lineH 35. Level 0: size 32, lineH 40.
  - Epigraph at W 420: size 19, lineH round(25.65) = 26, left = min(138.6, 240) = 138.6, avail 281.4.
  - Verse: left 40, avail 380, hang 30, widths {380, 350}.
  - Notes paragraph: size 18.4, lineH round(24.84) = 25.
  - Baseline with illustrative metrics ascender 1.0 and descender 0.25 em at size 20, lineH 27:
    round(1.0 + 20) = 21.

#### 4.6.2 Fragments, items and their builders

```cpp
struct Frag {
  uint32_t start, end;
  uint8_t flags;
  int32_t link;
  const ShapedRun* run;
  float size;
  float width;
};
```
`frags` (`std::vector<Frag>`) and `items` (`std::vector<LbItem>`) are reserved at `text.size() / 5 + 4` and
`text.size() / 3 + 8`, which affects performance only. A box's `tag` is the index of its fragment in `frags`, or -1
for a box that draws nothing.

- `addBox(w, tag)`: a Box with `width = w`.
- `addGlue(w)`: a Glue with `width = w`, `stretch = w * 0.5f`, `shrink = w * 0.33f` (tag -1).
- `addPenalty(w, pen, flagged, tag)`: a Penalty with those fields.

**First-line indent.** Before any word:
`if (indent > 0 && (st.align == BlockStyle::Justify || st.align == BlockStyle::Left)) addBox(indent, -1);`.
Centred and right-aligned blocks get no indent.

**`makePiece(a, c)`** shapes the bytes `[a, c)` and returns the new fragment index, or -1:
```cpp
pieceText.clear();
for (size_t k = a; k < c;) {
  const size_t s0 = k;
  const char32_t cp = utf8Decode(text, k);
  if (cp == kSoftHyphen || cp == 0x200B || cp == 0xFEFF) continue;
  pieceText.append(text, s0, k - s0);
}
if (pieceText.empty()) return -1;
int32_t link = -1;
const uint8_t f = static_cast<uint8_t>(spanFlagsAt(b, a, &link) | st.flags);
const float sz = size * runScale(f);
const ShapedRun& run = shaper_.shape(pieceText, styleIndex(f));
frags.push_back(Frag{a, c, f, link, &run, sz, run.advance * sz});
return static_cast<int>(frags.size()) - 1;
```
- U+00AD SOFT HYPHEN, U+200B ZERO WIDTH SPACE and U+FEFF ZERO WIDTH NO-BREAK SPACE are never shaped, but the
  fragment's byte range still covers them.
- Flags are the span flags at the piece start OR the block style's flags. A Title's runs therefore carry kSpanBold.
- The link is the span's link at the piece start.
- A sup/sub piece is shaped in the same style and drawn at 0.68 of the block size.
- `pieceText` is a scratch `std::string` reused across calls.

**`addWidePiece(a, c)`** splits a piece that is too wide for the column at code point boundaries (URLs, very long
compounds):
```cpp
uint32_t segStart = a;
float acc = 0;
const float limit = avail * 0.95f;
for (size_t k = a; k < c;) {
  const size_t s0 = k;
  utf8Decode(text, k);
  const int fi = makePiece(static_cast<uint32_t>(s0), static_cast<uint32_t>(k));
  const float cw = fi >= 0 ? frags[static_cast<size_t>(fi)].width : 0.f;
  if (fi >= 0) frags.pop_back();
  if (acc + cw > limit && s0 > segStart) {
    const int pi = makePiece(segStart, static_cast<uint32_t>(s0));
    if (pi >= 0) addBox(frags[static_cast<size_t>(pi)].width, pi);
    addPenalty(0, 100.f, false, -1);
    segStart = static_cast<uint32_t>(s0);
    acc = 0;
  }
  acc += cw;
}
const int pi = makePiece(segStart, c);
if (pi >= 0) addBox(frags[static_cast<size_t>(pi)].width, pi);
```
- Each code point is shaped alone (and cached in the Shaper) to estimate its width. A segment ends before the code
  point that would take the estimate past 95 % of `avail`.
- Each segment is then shaped as a whole and becomes a box. Between segments there is an unflagged penalty of 100
  with width 0, so no hyphen is drawn there.
- A split can fall between a base letter and its combining mark.

#### 4.6.3 Words and inter-word glue

```
n = text.size(); i = 0; firstWord = true; noBreakNext = false
while i < n:
  if text[i] == ' ': ++i; continue                          // only U+0020 separates words
  ws = i; while i < n and text[i] != ' ': ++i; we = i       // word = text[ws, we)
  dashWord = isDashWord(word)
  if not firstWord:
    f  = spanFlagsAt(b, ws - 1) | st.flags                  // the style of the space just before the word
    sw = shaper_.spaceWidth(styleIndex(f)) * size
    // Russian typography: a dash never starts a line; a dialogue dash keeps its first word.
    if dashWord or noBreakNext: addPenalty(0, kLbInfPenalty, false, -1)
    addGlue(sw)
  noBreakNext = firstWord and dashWord
  firstWord = false
  ... break opportunities (4.6.4) and pieces (4.6.5) of this word ...
```
- **Word boundaries.** Only the ASCII space separates words. Runs of spaces give one glue, and leading and trailing spaces
  give nothing. NBSP (U+00A0), tabs and other space characters belong to the word. They are shaped (NBSP always with
  the primary face, §3.3), never break a line and never stretch.
- **Glue.** Each glue is the primary face's space advance for the style in force at the byte before the word, times
  the block size. Sup/sub do not scale it. Stretch is 0.5 and shrink 0.33 of the width. There is no extra sentence
  spacing.
- **Dash never starts a line.** Before the glue that precedes a dash word comes a penalty of `kLbInfPenalty`. A glue
  is a legal break only right after a box (spec 05), so neither the glue nor the penalty can break, and the dash
  stays at the end of the previous line.
- **Dialogue dash.** If the block's first word is a dash word, the glue after it gets the same no-break penalty, so
  "— Word" never splits. This applies only to the first word of the block, in any block type and any language.
- **Opening punctuation.** There is no special rule. Quotes and brackets are part of the word they touch, because
  only spaces split words. `isOpeningPunctCp` and `isDashCp` are not used by the layout.

#### 4.6.4 Break opportunities inside a word ("cuts")

```cpp
enum : uint8_t { kHyph = 1, kExplicit = 2, kSoft = 3, kZero = 4 };
std::vector<std::pair<uint32_t, uint8_t>> cuts;   // (byte offset, kind)
```
A cut at offset `o` means the piece before ends at `o` and the next piece starts at `o`. For each word, `cuts` is
cleared and `hasSoftHyphen = false`. Cuts are collected in this order:

1. **Web word.** Web addresses are never hyphenated, because a hyphen would read as part of the address. They may
   break, with nothing added, after a slash or before a dot.
   ```cpp
   auto isWeb = [&](int32_t lk) {
     return lk >= 0 && doc_ && lk < static_cast<int32_t>(doc_->links.size()) &&
            isWebLink(doc_->links[static_cast<size_t>(lk)]);
   };
   int32_t lk = -1;
   webWord = (spanFlagsAt(b, ws, &lk) & kSpanLink) && isWeb(lk);
   for (const Span& sp : b.spans) {
     if (!webWord && sp.begin > ws && sp.begin < we && (sp.flags & kSpanLink)) webWord = isWeb(sp.link);
   }
   if (webWord) {
     for (uint32_t k = ws + 1; k + 1 < we; ++k) {
       if (text[k] == '/' && text[k + 1] != '/' && text[k - 1] != '/') cuts.emplace_back(k + 1, kZero);
       else if (text[k] == '.' && text[k - 1] != '.') cuts.emplace_back(k, kZero);
     }
   }
   ```
   - A word is a web word if the link span at its first byte, or any link span that begins strictly inside it,
     targets a web link (`http://`, `https://`, `ftp://`, `mailto:`; spec 03). Addresses written as plain text became
     such links in `Document::finalize`.
   - Web cuts work on ASCII bytes from `ws + 1` to `we - 2`. There is a cut after a `/` that is not part of `//`, and
     a cut before a `.` that does not follow another `.`.
   - Example: `https://example.com/a/b.html` gives the pieces `https://example`, `.com/`, `a/`, `b`, `.html`.
2. **Character scan** (all words, web words included):
   ```cpp
   size_t k = ws;
   char32_t prevCp = 0;
   while (k < we) {
     const size_t s0 = k;
     const char32_t cp = utf8Decode(text, k);
     if (cp == kSoftHyphen) {
       hasSoftHyphen = true;
       if (s0 > ws && k < we) cuts.emplace_back(static_cast<uint32_t>(k), kSoft);
     } else if (cp == 0x200B) {
       if (s0 > ws && k < we) cuts.emplace_back(static_cast<uint32_t>(k), kZero);
     } else if ((cp == U'-' || cp == 0x2010) && s0 > ws && k < we) {
       size_t kk = k;
       const char32_t nextCp = utf8Decode(text, kk);
       if ((isLetterCp(prevCp) || isDigitCp(prevCp)) && isLetterCp(nextCp))
         cuts.emplace_back(static_cast<uint32_t>(k), kExplicit);
     } else if ((cp == 0x2014 || cp == 0x2013) && s0 > ws && k < we) {
       size_t kk = k;
       const char32_t nextCp = utf8Decode(text, kk);
       if (isLetterCp(nextCp) || isDigitCp(nextCp)) cuts.emplace_back(static_cast<uint32_t>(k), kExplicit);
     }
     if (!isCombiningMarkCp(cp)) prevCp = cp;
   }
   ```
   Every cut here falls *after* the character, and only when the character is neither the first nor the last of the
   word.
   - Soft hyphen (U+00AD): a `kSoft` cut. Any soft hyphen anywhere in the word, even at its edges, sets
     `hasSoftHyphen`.
   - ZERO WIDTH SPACE (U+200B): a `kZero` cut.
   - HYPHEN-MINUS (U+002D) or HYPHEN (U+2010) between a letter or digit (the previous non-combining code point) and a
     letter (the next code point): a `kExplicit` cut, e.g. "по-|своему", "2-|й". There is none for "1-2".
   - EM DASH (U+2014) or EN DASH (U+2013) followed by a letter or digit: a `kExplicit` cut, e.g. "1941–|1945". The
     previous character is not checked. U+2015 and U+2011 never cut.
3. **Pattern hyphenation**, only if `st.hyphenate && hyph_ && !hasSoftHyphen && !webWord && we - ws >= 5` (the word
   is at least 5 *bytes* long):
   ```cpp
   letters.clear();
   letterOffs.clear();
   auto flushRun = [&] {
     if (letters.size() >= 5) {
       hyphBreaks_.clear();
       hyph_->hyphenate(letters, hyphBreaks_);
       for (int p : hyphBreaks_) cuts.emplace_back(letterOffs[static_cast<size_t>(p)], kHyph);
     }
     letters.clear();
     letterOffs.clear();
   };
   size_t k = ws;
   while (k < we) {
     const size_t s0 = k;
     const char32_t cp = utf8Decode(text, k);
     if (isLetterCp(cp)) {
       letters.push_back(cp);
       letterOffs.push_back(static_cast<uint32_t>(s0));
     } else if (isCombiningMarkCp(cp) && !letters.empty()) {
       // stress marks stay attached to their letter
     } else {
       flushRun();
     }
   }
   flushRun();
   ```
   - The word is split into maximal runs of letters. A combining mark after a letter is skipped without ending the
     run; any other character ends it.
   - Runs of at least 5 letters are passed, in their original case, to `HyphenationService::hyphenate` (spec 05). It
     handles only all-Cyrillic or all-Latin runs and applies the leftMin/rightMin of the patterns.
   - Each returned position p ("between letters[p-1] and letters[p]") becomes a `kHyph` cut at the byte offset of
     letter p, so it falls after any marks of letter p-1.
   - `letters` (`std::u32string`), `letterOffs` and `hyphBreaks_` are scratch storage.
4. **Merge**:
   ```cpp
   std::sort(cuts.begin(), cuts.end());
   cuts.erase(std::unique(cuts.begin(), cuts.end(),
                          [](const auto& x, const auto& y) { return x.first == y.first; }),
              cuts.end());
   ```
   Sort by (offset, kind) and keep one cut per offset: the one with the smallest kind value
   (kHyph < kExplicit < kSoft < kZero).

#### 4.6.5 Pieces, boxes and in-word penalties

`bounds` holds `ws`, every cut offset, every `Span::begin` with `ws < begin < we`, and `we`, sorted and with
duplicates removed. Then, for each consecutive pair `(a, c)` (verbatim):
```cpp
size_t ci = 0;
for (size_t k = 0; k + 1 < bounds.size(); ++k) {
  const uint32_t a = bounds[k], c = bounds[k + 1];
  const int fi = makePiece(a, c);
  if (fi >= 0) {
    if (frags[static_cast<size_t>(fi)].width > avail * 0.98f) {
      frags.pop_back();
      addWidePiece(a, c);
    } else {
      addBox(frags[static_cast<size_t>(fi)].width, fi);
    }
  }
  while (ci < cuts.size() && cuts[ci].first < c) ++ci;
  if (ci < cuts.size() && cuts[ci].first == c && c < we) {
    const uint8_t kind = cuts[ci].second;
    if (kind == kHyph || kind == kSoft) {
      int32_t lk = -1;
      const uint8_t f = static_cast<uint8_t>(spanFlagsAt(b, a, &lk) | st.flags);
      const float hw = shaper_.hyphenWidth(styleIndex(f)) * size * runScale(f);
      // Screen columns are narrow, so hyphens cost more than TeX's default of 50.
      addPenalty(hw, kind == kSoft ? 50.f : 120.f, true, fi >= 0 ? static_cast<int>(frags.size()) - 1 : -1);
    } else if (kind == kExplicit) {
      addPenalty(0, 50.f, true, -1);
    } else {
      addPenalty(0, 0, false, -1);
    }
  }
}
```
- Every piece is shaped separately. Kerning and ligatures do not act across hyphenation points, explicit cuts, web
  cuts or style changes, and the word's width is the sum of its pieces' widths.
- A piece wider than 98 % of `avail` is replaced by `addWidePiece`. Its fragment is popped first, so its index is
  reused.
- A piece end that is only a span start gets no penalty, so a style change inside a word is never a break.
- A pattern or soft hyphenation penalty has the width of a hyphen: the primary face's `hyphenAdvance` for the
  piece's style, times the block size, times 0.68 for sup/sub. Its tag is the last fragment created, which is the
  last segment for a wide piece, or -1 if the piece was empty. Line building uses that fragment's flags and size for
  the drawn hyphen.

#### 4.6.6 End of the paragraph, and the item model

After the last word come a fill glue (`type = Glue`, width 0, `stretch = kLbFillStretch`, shrink 0, tag -1) and a
forced break: `addPenalty(0, -kLbInfPenalty, true, -1)`. Note that the final forced penalty is **flagged**. The
breaker's flagged demerits (6000) therefore also apply to the last line when the line before it ends at a flagged
break: a pattern hyphen, a soft hyphen, or an explicit hyphen or dash (spec 05).

| Item | Placed | width | stretch / shrink | penalty | flagged | tag |
|---|---|---|---|---|---|---|
| indent box | first item, Justify/Left blocks with indent > 0 | indent | – | – | – | -1 |
| piece box | each non-empty piece (or wide-piece segment) | fragment width | – | – | – | fragment index |
| no-break penalty | before the glue in front of a dash word, and before the glue after a block-initial dash word | 0 | – | 10000 | no | -1 |
| inter-word glue | between words | sw | 0.5 sw / 0.33 sw | – | – | -1 |
| pattern hyphen | at a `kHyph` cut | hw | – | 120 | yes | last fragment or -1 |
| soft hyphen | at a `kSoft` cut | hw | – | 50 | yes | last fragment or -1 |
| explicit hyphen or dash | at a `kExplicit` cut | 0 | – | 50 | yes | -1 |
| zero-width break | at a `kZero` cut (ZWSP, web cut) | 0 | – | 0 | no | -1 |
| emergency split | between the segments of a wide piece | 0 | – | 100 | no | -1 |
| fill glue | end | 0 | 100000 / 0 | – | – | -1 |
| forced break | last item | 0 | – | -10000 | yes | -1 |

An empty or all-space text still produces the fill glue and the forced break (plus the indent box when one applies),
which gives one line with no runs.

#### 4.6.7 Line breaking

```cpp
std::vector<LbBreak> brks;
bool ok = false;
if (st.align == BlockStyle::Justify) {
  LbParams lp;
  lp.tolerance = 2.0f;
  ok = breakLinesOptimal(items, widths, lp, brks);
  if (!ok) {
    lp.tolerance = 6.0f;
    ok = breakLinesOptimal(items, widths, lp, brks);
  }
}
if (!ok) breakLinesGreedy(items, widths, brks);
```
- Justified blocks try Knuth–Plass with tolerance 2, then with tolerance 6, then first fit. The other `LbParams`
  fields keep their header defaults: linePenalty 10, flaggedDemerits 6000, fitnessDemerits 200.
- Left, centred and right-aligned blocks use first fit directly.
- `widths` holds the first line's width, then the width of every later line (`lbLineWidth` repeats the last entry).

#### 4.6.8 Building the lines

`itemStart = 0` and `lastEnd = 0`. For each break `k` (with `br = brks[k]` and `lastLine = k + 1 == brks.size()`),
build a `LayoutLine` with `height = lineH`:

1. Skip forward from `itemStart` over the items before `br.item` that are not boxes. Discardable glue and penalties
   at the start of a line vanish.
2. Adjustment ratio:
   ```cpp
   // Justified lines stretch or shrink; any other line may still need to shrink to fit (never overflow).
   float r = (st.align == BlockStyle::Justify && !lastLine) ? br.ratio : std::min(0.0f, br.ratio);
   r = std::max(-1.0f, r);
   const float lineX0 = k > 0 ? hang : 0.0f;
   const float lineW = lbLineWidth(widths, static_cast<int>(k));
   ```
   The non-last lines of a justified block use the breaker's ratio, with no upper limit (a greedy fallback line can
   be very loose). The last line of a justified block, and every line of the other alignments, never stretch but do
   shrink when the line is overfull. Shrinking never goes below -1.
3. Walk the items from there up to, but **not including**, `br.item`. `x` starts at 0:
   - **Box**: if `tag >= 0`, emit a `PlacedRun` from `frags[tag]` with `run`, `size`, `width`, `flags`, `link`,
     `start`, `end` copied, `x` set to the current x, and
     `baseline = baseline + ((fr.flags & kSpanSup) ? -0.36f * size : ((fr.flags & kSpanSub) ? 0.2f * size : 0.f))`.
     The superscript and subscript offsets use the block size, not the run size, and Sup wins when both bits are
     set. The first emitted run sets `line.start = fr.start` (`haveStart = true`), and every emitted run sets
     `line.end = fr.end`. Then `x += it.width` for every box, including the indent box.
   - **Glue**: `gw = it.width; if (r > 0) gw += r * it.stretch; else if (r < 0) gw += r * it.shrink; x += gw;`.
   - **Penalty**: ignored.
4. **Drawn hyphen.** If the break item is a hyphenation penalty, add the hyphen run:
   ```cpp
   const LbItem& bi = items[static_cast<size_t>(br.item)];
   if (bi.type == LbItem::Penalty && bi.width > 0 && bi.penalty > -kLbInfPenalty) {
     uint8_t f = st.flags;
     float sz = size;
     if (bi.tag >= 0) {
       f = frags[static_cast<size_t>(bi.tag)].flags;
       sz = frags[static_cast<size_t>(bi.tag)].size;
     }
     const ShapedRun& hr = shaper_.shape("-", styleIndex(f));
     PlacedRun pr;
     pr.run = &hr;
     pr.x = x;
     pr.size = sz;
     pr.width = hr.advance * sz;
     pr.flags = static_cast<uint8_t>(f & ~(kSpanLink | kSpanNoteRef));
     pr.baseline = baseline + ((f & kSpanSup) ? -0.36f * size : ((f & kSpanSub) ? 0.2f * size : 0.f));
     pr.start = pr.end = line.end;
     line.runs.push_back(pr);
     x += pr.width;
   }
   ```
   - This happens only when the break is at a pattern or soft hyphen, the penalties with a positive width. Explicit
     hyphens and dashes, web cuts, ZWSP and emergency splits add nothing.
   - The drawn hyphen is the ASCII hyphen-minus `"-"` (U+002D), shaped through the cache. In regular style its run is
     exactly `&shaper.shape("-", 0)`.
   - It is an empty byte range at the line end, has no link (`link` stays -1) and is drawn without link or note
     colouring.
   - Its width is the shaped advance times the fragment's size. That equals the penalty width the breaker used
     whenever the primary face has U+002D (so `pickFace` keeps the primary face and the shaped advance equals
     `hyphenAdvance`) and the piece before the cut was non-empty. Justified hyphenated lines therefore end exactly
     at the right edge.
5. **Offsets.** `if (!haveStart) { line.start = lastEnd; line.end = lastEnd; }`, then `if (k == 0) line.start = 0;`,
   then `lastEnd = line.end`.
   - The first line always starts at offset 0, even when the text starts with spaces.
   - A later line starts at its first piece, which may be inside a word after a hyphenation, explicit, web or
     emergency break.
   - A line without pieces is empty at the previous line's end.
6. **Alignment.**
   ```cpp
   float off = 0;
   if (st.align == BlockStyle::Center) off = (lineW - x) * 0.5f;
   else if (st.align == BlockStyle::Right) off = lineW - x;
   if (off < 0) off = 0;
   for (PlacedRun& pr : line.runs) pr.x += left + lineX0 + off;
   ```
   `x` includes the drawn hyphen. The offset is not rounded. Continuation lines (k > 0) are shifted by `hang` in
   every alignment.
7. Push the line, then set `itemStart = br.item + 1`.

There is no merging of runs. Each piece is its own `PlacedRun`, and inter-word spaces belong to no run (they are glue
gaps).

### 4.7 Full layouts, metrics and the caches

`full_` (`unordered_map<int, BlockLayout>`) holds full layouts. `metrics_` holds one optional `BlockMetrics` per block,
sized by `invalidate`. Both are only ever filled from `layoutBlock`, which is deterministic, so a block's metrics
always match its full layout.

- **`block(index)`**: if `full_` has the index, return it. Otherwise `bl = layoutBlock(index)`; if `metrics_[index]`
  is null, fill it from `extractMetrics(bl)`; then move `bl` into `full_` and return the stored value. It always
  keeps the full layout. The reference stays valid until that entry is erased by `trimCache`, a page-height change
  for an image, `invalidate`, `setParams` or `setDocument`.
- **`metricsImpl(index, keepFull)`**: if `metrics_[index]` exists, return it. If `full_` has the block, extract its
  metrics into `metrics_[index]` and return them. Otherwise `bl = layoutBlock(index)` and store
  `extractMetrics(bl)`; then, only if `keepFull`, move `bl` into `full_`. Return the stored metrics.
- **`metrics(index)`** = `metricsImpl(index, keepFull_)`. `keepFull_` is true except inside `countStep`, so background
  pagination of the whole book keeps only metrics, not full layouts.
- The `lineHeight(p)` helper in the header reads `metrics(p.block).lineHeights[p.line]`.

Every block has at least one line: text blocks get at least one from the breaker, and EmptyLine and Image blocks get
exactly one.

### 4.8 Positions: `normalize`, `next`, `prev`

- **`normalize(p)`**: if `p.block < 0`, `p = {0, 0}`; if `p.line < 0`, `p.line = 0`. While `p.block < blockCount()`,
  return `p` if `p.line` is below the block's line count, else move to `{p.block + 1, 0}`. Past the last block,
  return `endPos()`.
- **`next(p)`**: `p = normalize(p)`. At the end, return `p`. If the block has a line after `p.line`, return
  `{p.block, p.line + 1}`; otherwise return `normalize({p.block + 1, 0})`.
- **`prev(p)`**:
  ```cpp
  if (p.block >= blockCount()) {
    p = LinePos{blockCount(), 0};
  } else if (p.line > 0) {
    return LinePos{p.block, p.line - 1};
  }
  for (int b = p.block - 1; b >= 0; --b) {
    const BlockMetrics& m = metrics(b);
    if (!m.lineHeights.empty()) return LinePos{b, static_cast<int>(m.lineHeights.size()) - 1};
  }
  return normalize(LinePos{0, 0});
  ```
  `p.line - 1` is not checked against the block's line count. `prev` of the first line returns the first line.

### 4.9 `pageFrom(start)`

Fills a page from `normalize(start)` down to the page height `H = params_.pageHeight`:
```
page.start = p = normalize(start); y = 0; pendingSpace = 0
while not isEnd(p):
  m = metrics(p.block)
  if p.line == 0 and page.lines not empty:                  // a new block, not at the page top
    if m.pageBreakBefore: break
    gap = max(pendingSpace, m.spaceBefore)                  // collapsing margins
    own = m.keepWithNext ? sum of m.lineHeights : 0
    (keep-with-next test, below)
    y += gap
  h = m.lineHeights[p.line]
  if page.lines not empty and y + h > H + 0.01: break
  page.lines.push_back({p, y}); y += h
  if p.line + 1 < line count: ++p.line
  else: pendingSpace = m.spaceAfter; p = normalize({p.block + 1, 0})
page.end = p
```
The keep-with-next test (verbatim):
```cpp
// A heading needs room for itself and the first two lines that follow it. One taller than a whole page
// (seen in broken FB2 files whose title holds the entire table of contents) cannot be kept together:
// moving it would only leave this page empty.
if (m.keepWithNext && own <= H) {
  float need = gap + own;
  int added = 0;
  float sp = m.spaceAfter;
  for (int q = p.block + 1; q < blockCount() && added < 2; ++q) {
    const BlockMetrics& nm = metrics(q);
    if (nm.pageBreakBefore) break;
    need += std::max(sp, nm.spaceBefore);
    for (float h : nm.lineHeights) {
      need += h;
      if (++added >= 2) break;
    }
    if (!nm.keepWithNext) break;
    sp = nm.spaceAfter;
  }
  if (y + need > H + 0.01f) break;
}
```
Rules that follow:
- **First line.** A page always takes its first line, even one taller than the page. It is empty only at the end of
  the book (then `start == end == endPos()`). Each later line must fit: `y + h ≤ H + 0.01`.
- **Page top.** Spacing is never added at the top of a page. Neither the block's `spaceBefore` nor the previous
  block's `spaceAfter` counts there, and `pageBreakBefore` is ignored for the first line. Spacing goes only before
  line 0 of a block that follows something on the same page.
- **Page breaks.** A `pageBreakBefore` block (a chapter start) always begins a new page.
- **Spacing between blocks.** The gap is the larger of the previous block's `spaceAfter` and this block's
  `spaceBefore`. Neither is rounded.
- **Keep with next.** A keep-with-next block (Title, Subtitle, PoemTitle) that is not at the page top must fit
  together with up to two following lines. Those are counted across the following blocks as long as each of them is
  itself keep-with-next, stopping at a `pageBreakBefore` block, with their gaps included. If they do not fit, the
  page ends before the heading, so a heading never ends a page.
- **Tall headings.** A heading taller than the page (`own > H`) is exempt and starts right where it is.
- **Successive headings.** Each keep-with-next block runs its own test when it is reached. A heading followed by a
  subheading checks the subheading plus one more line, and the subheading then checks its own two lines.
- **Long blocks.** A block taller than the page continues on the next page line by line; nothing else is kept
  together. A line taller than the page can only be placed as the first line of a page.
- **No widow/orphan control** beyond this rule.

### 4.10 `pageStartBefore(target)`

Returns the start of the page that ends at `target`, i.e. the previous page.
1. `target = normalize(target)`, `first = normalize({0, 0})`. If `target <= first`, return `first`. (With no document
   both are `{0, 0}`, so `doc_` is never dereferenced.) `H = params_.pageHeight`.
2. **Chapter start or end of book: paginate forwards.** If `target.line == 0` and either `isEnd(target)` or
   `blocks[target.block].pageBreakBefore`:
   - `sectionStart = min(target.block, blockCount()) - 1`, `scanned = 0`.
   - `while (sectionStart > 0 && !blocks[sectionStart].pageBreakBefore && scanned < 3000) { --sectionStart;
     ++scanned; }`.
   - If `sectionStart <= 0 || blocks[sectionStart].pageBreakBefore` (the previous chapter's start, or the book start,
     was found within 3000 blocks):
     `s = normalize({max(sectionStart, 0), 0})`. Then, for at most 2000 pages while `s < target`: `pg = pageFrom(s)`;
     if `pg.end >= target` or `pg.empty()`, return `s`; otherwise `s = pg.end`.

   The pages seen while going back over a chapter boundary are therefore exactly the pages seen while reading
   forwards from that chapter's start. If the scan or the page loop runs out, continue with step 3.
3. **Estimate.** `s = prev(target)`, `h = lineHeight(s)`. While `s > first`: stop if `s.line == 0` and
   `blocks[s.block].pageBreakBefore` (never go above a chapter start); `q = prev(s)`; stop if
   `h + lineHeight(q) > H`; otherwise `h += lineHeight(q)` and `s = q`. Spacing is ignored.
4. **Reach the target.** `guard = 0; while (s < target && pageFrom(s).end < target && guard++ < 500) s = next(s);`.
5. **Start as early as possible.** `guard = 0; while (s > first && guard++ < 500)`: stop if `s.line == 0` and
   `blocks[s.block].pageBreakBefore`; `q = prev(s)`; if `pageFrom(q).end >= target` then `s = q`, else stop.
6. Return `s`.

### 4.11 `posForOffset(block, byteOffset)` and `offsetOf(p)`

- **`posForOffset`**: with no blocks, return `endPos()`. Otherwise:
  - `block = clamp(block, 0, blockCount() - 1)` and `m = metrics(block)`.
  - If `m.lineStarts` is empty, return `normalize({block, 0})`. This never happens, because every block has a line.
  - Otherwise `line = (upper_bound(lineStarts, byteOffset) - begin) - 1`, clamped to ≥ 0, and return
    `{block, line}`.

  The result is the last line that starts at or before the offset. `lineStarts[0]` is always 0, so every offset
  falls in some line. The app keeps the reading position through zoom and resizing this way.
- **`offsetOf(p)`**: `p = normalize(p)`; at the end return 0; otherwise return `metrics(p.block).lineStarts[p.line]`.

### 4.12 `hitTest(page, x, y, out, linkSlop)`

`x` and `y` are relative to the column's left edge and the page top. The default `linkSlop` is 8 px (header).
1. **Nearest link.** Footnote markers are tiny and fingers are not. `best = 1e30f`. For each `PageLine` in order:
   - Take `bl = block(pl.pos.block)` (a full layout, created if needed). Skip the line if `pl.pos.line` is out of
     range, or if `y < pl.y - linkSlop || y > pl.y + L.height + linkSlop`.
   - `dy` is the distance from y to `[pl.y, pl.y + L.height]` (0 inside).
   - For each run with `r.link >= 0`, `dx` is the distance from x to `[r.x, r.x + r.width]`. Skip the run if
     `dx > linkSlop || dy > linkSlop`.
   - With `d = dx*dx + dy*dy`, if `d < best` (strictly less, so the first run wins ties), set `best = d` and
     `out = {pl.pos.block, r.start, r.link, r.flags}`.

   After all lines, `if (out.link >= 0) return true;`. `out` is not reset on entry, so callers pass a fresh
   `HitResult` (link -1).
2. **Line and word.** For each `PageLine` in order, skipping out-of-range lines: if `pl.y <= y < pl.y + L.height`,
   set `out.block = pl.pos.block` and `out.offset = L.start`. Then find the first run with
   `r.x <= x <= r.x + r.width` and set `out.offset = r.start` and `out.flags = r.flags` from it. Return true. Picture
   lines have no runs, so they give their line start.
3. Return false when y is in no line.

### 4.13 Background page count

**`countStep(budgetMs)`**:
```cpp
if (countDone_ || !doc_) return;
const auto t0 = std::chrono::steady_clock::now();
keepFull_ = false;
if (!countStarted_) {
  countStarted_ = true;
  pageStarts_.clear();
  countPos_ = normalize(LinePos{0, 0});
}
for (;;) {
  if (isEnd(countPos_)) {
    countDone_ = true;
    break;
  }
  pageStarts_.push_back(countPos_);
  const Page pg = pageFrom(countPos_);
  countPos_ = pg.end > countPos_ ? pg.end : next(countPos_);
  const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
  if (ms >= budgetMs) break;
}
keepFull_ = true;
```
Each call paginates at least one page (unless counting is done). The elapsed time since the call began is checked
after each page, and the call returns once it is ≥ `budgetMs`; the end of the book can also be reached within the
call. `pageStarts_` is therefore the sequence of forward page starts from the first line, the same pages as calling
`pageFrom` repeatedly from `normalize({0, 0})`. The safety step `next(countPos_)` is used only if a page did not
advance. `keepFull_` is false for the duration of the call, so the pagination caches only metrics.

- **`countProgress()`**: 1.0 when done; otherwise `countPos_.block / blockCount()` as floats (0 without blocks). It
  measures blocks, not lines.
- **`pageIndexOf(p)`**: 0 when no starts exist; otherwise `max((upper_bound(pageStarts_, p) - begin) - 1, 0)`, the
  index of the last page start at or before `p` (LinePos order: block, then line). This works on a partial count too.
- `pageCount()`, `pageStart(index)` and `countDone()` are inline in the header.

### 4.14 `trimCache(centerBlock)`

If `full_.size() <= 500`, do nothing. Otherwise erase every full layout whose block index differs from `centerBlock`
by more than 160 (`std::abs(index - centerBlock) > 160`). Metrics are never trimmed.

### 4.15 Contract with the application (spec 09)

- **Ownership.** The app owns one `FontLibrary`, a book `Shaper` and a UI `Shaper` sharing it (same fallback faces),
  and one `BookLayout(*bookShaper_, &hyph_)`.
- **Typeface change.** Changing the typeface calls `bookShaper_->setFamily` (which clears the cache) and bumps
  `fontGeneration`, then calls `layout_->invalidate()`.
- **Opening a book.** The app clears the book shaper when it holds more than 150000 entries, then calls
  `setDocument`.
- **Parameters.** `updateGeometry` builds the `LayoutParams` and calls `setParams` only when they differ:
  - `fontSize` is the font px quantised to 1/4 px.
  - `pageWidth` is the whole-pixel column width.
  - `pageHeight = max(3 × fontSize, floor(free height))`.
  - `lineSpacing`, `paragraphIndent`, `paragraphSpacing`, `justify` and `hyphenate` come from the settings, plus the
    `fontGeneration`.

  Showing or hiding the bars changes only `pageHeight`, which takes the cheap path of §4.3.
- **Views.** A view is `pageFrom(start)`, and in two-page mode also `pageFrom(first.end)`. Going back uses
  `pageStartBefore(viewStart)`, applied twice in two-page mode while above the first line. The end of the book is
  `pageStartBefore(endPos())`. The reading anchor is `(block, offsetOf(viewStart))`, restored with `posForOffset`.
  `trimCache(viewStart.block)` runs after each view rebuild.
- **Drawing.** For each `PageLine` the app fetches `block(pl.pos.block).lines[pl.pos.line]`. A picture block is drawn
  at `(columnX + imageX, top + pl.y + imageY)` with size `imageW × imageH`. Otherwise each `PlacedRun` is drawn at
  `(columnX + r.x, top + pl.y + r.baseline)` at `r.size` px, with glyph pens at `x + g.x·size` and
  `baseline − g.y·size` (spec 08). Strike and web-link underlines use `r.flags`, `r.link`, `r.x`, `r.width` and
  `r.size`. Search highlighting uses `r.start` and `r.end`.
- **Taps.** `hitTest` is called with column-relative coordinates and a slop of 8 px for the mouse or 18 × display
  scale for touch. A result with `link >= 0` follows the link.
- **Page count.** While the status bar is shown, the app calls `countStep(4.0)` once per frame (1000 ms in
  screenshot mode). `pageCount`, `pageIndexOf(view start) + 1`, `pageStart(n - 1)` and `countProgress` drive the
  status bar and "Go to page".

---

## 5. What the unit tests pin down

`testTextLayout` in `tests/core_tests.cpp` (compiled with `LL_TESTS_WITH_TEXT`, verbatim in ai/files/04-tests.md) must
pass unchanged. It loads the four bundled PT Serif files and uses the defaults of `LayoutParams` except where noted.

| Check | Constrains |
|---|---|
| `lib.ok()`; the four `addFromFile` calls return ≥ 0 | §2.3–§2.5 |
| `shape("Привет, мир!", 0)` has 12 glyphs and an advance between 4 and 8 em | §3.4–§3.5: one glyph per code point (no ligatures there), the space shaped as a glyph, em units |
| the same text and style return the same object; style 1 returns another | §3.4 cache key with the style digit |
| advance of "AV" ≤ "A" + "V" | default HarfBuzz features (kerning), §3.5 |
| 44 blocks (four level-1 Titles with `pageBreakBefore` from the second on, long Russian and English paragraphs), font 20, W 420, H 600: no line's last run ends right of W + 0.75 | §4.6.5 wide pieces, §4.6.8 shrink and the -1 clamp |
| every non-last line of a Paragraph ends within 0.75 px of W | §4.6.8 justification with the breaker's ratio, indent box counted, drawn hyphen width = penalty width |
| some line ends in `&shaper.shape("-", 0)` with `start == end` | §4.6.4 pattern hyphenation, §4.6.8 drawn hyphen |
| pages from `pageFrom` are never empty, start at the requested line, end ≤ H + 0.01, and together cover every line exactly once | §4.9 |
| `pageStartBefore(starts[k]) == starts[k-1]` for all but at most 2 pages | §4.10, in particular the forward pass at chapter starts |
| line 0 of a `pageBreakBefore` block is only ever the first line of a page | §4.9 |
| `countStep(5.0)` until done gives the same page count; `pageIndexOf(starts[3]) == 3` | §4.13 |
| page height 600 → 480: not done; counting matches a fresh layout start for start and has more pages; back to 600: done at once with the old count; to 480 again: done at once | §4.3 page-height path, image-only invalidation, `otherHeight_` swap |
| after a zoom to 28 px, `posForOffset(5, off)` is the line with `lineStarts[line] ≤ off < lineStarts[line+1]` | §4.11, §4.8 |
| a level-1 Title taller than the page still starts on the first page, right after the first heading | §4.9 `own <= H` exemption |
| 30 level-2 Titles each followed by a paragraph: no page except the last ends with a Title line | §4.9 keep-with-next look-ahead |
| "See https://example.com/a/very/long/path/that/cannot/be/hyphenated/at/all/index.html for details." at 18 px in a 160 px column: ≥ 4 lines, no last run ends beyond 161 px, no line ends in a drawn hyphen, ≥ 2 lines end right after a `/` | §4.6.4 web words (no hyphenation, cuts after `/` and before `.`), §4.6.2 emergency splitting |

---

## Checklist

FontLibrary
- [ ] When `FT_Init_FreeType` fails: `ok()` is false and `addFromMemory`/`addFromFile` return -1.
- [ ] Empty data, unreadable bytes or a bitmap-only font return -1, and the next successful face still gets the next
      dense id.
- [ ] `addFromFile("…/fonts/PTSerif-Regular.ttf")` names the face `PTSerif-Regular.ttf`.
- [ ] `upem` comes from `hb_face_get_upem` (fallback `units_per_EM`, then 1000), and the HarfBuzz font scale is
      `(upem, upem)`.
- [ ] Ascender/descender come from FT_Face; OS/2 typo values replace them only when fsSelection bit 7 is set;
      non-positive values keep 0.8/0.2.
- [ ] xHeight/capHeight come from OS/2 version ≥ 2 when positive, else 0.5/0.7.
- [ ] spaceAdvance/hyphenAdvance are the nominal-glyph advances of U+0020/U+002D ÷ upem, or 0.25/0.33 when the
      character is missing.
- [ ] `setPixelSize(id, 20.25f)` sets 1296 (26.6) at 72×72 dpi once; repeating the same size makes no FreeType call.
- [ ] `hasChar` is false for a face without `ft` or without the code point in its Unicode charmap.

Shaper
- [ ] The key is `'0' + (style & 3)` followed by the text; a repeated call returns the same object; another style
      gives another object.
- [ ] Space and NBSP always use the primary face; a character missing from the primary face uses the first fallback
      that has it, else the primary face.
- [ ] Combining marks, U+200D, U+FE0E and U+FE0F stay in the current segment's face.
- [ ] Each segment is shaped with the full text as context, the script guessed, the direction forced LTR and no
      features passed.
- [ ] Glyph x accumulates across segments; `x = pen + x_offset/upem`, `y = y_offset/upem`; the advance is the sum
      of the x advances.
- [ ] `setFamily` clears the cache and `setFallbacks` does not; `spaceWidth`/`hyphenWidth` use only the primary
      face.

Block styles and geometry
- [ ] Every BlockType gets exactly the scale/flags/align/indent/hang/margins/spacing/hyphenate/keepWithNext/
      maxLineSpacing of the table in §4.4; Title level ≥ 6 uses 1.0 and level 0 has 1.6 em before.
- [ ] `notes` multiplies the scale by 0.92; `params.hyphenate == false` disables hyphenation everywhere.
- [ ] `lineH = max(1, round(size × min(lineSpacing, maxLineSpacing if > 0)))` for every line of a text block.
- [ ] `baseline = round((lineH − (asc + desc)·size)/2 + asc·size)` from the block style's primary face, the same on
      every line.
- [ ] `left = marginLeft·base + min(marginLeftFrac·W, 12·base)`; margins are dropped when `avail < 8·base`.
- [ ] The indent box (`indent·size`) appears only for Justify/Left blocks with indent > 0.
- [ ] Verse continuation lines are broken to `avail − hang` and shifted right by `hang = min(1.5·size, 0.3·avail)`.
- [ ] An EmptyLine is one empty line of height `round(base × lineSpacing)`.
- [ ] Images: a non-cover picture is ≤ column, ≤ 0.92·H, ≤ max(1, base/16) scale, centred, with 0.6·base spacing;
      the cover (block 0 only) fills `floor(H)`, is centred both ways and has no spacing; an invalid image gives a
      zero-height line.

Items and line breaking
- [ ] Only U+0020 separates words; one glue per gap, of width spaceAdvance(style at `ws−1`) × size, stretch 0.5,
      shrink 0.33.
- [ ] A dash word (— – ― followed only by non-letters/non-digits) never starts a line; a block-initial dash word is
      never separated from the next word.
- [ ] A soft hyphen allows a break after it with a drawn hyphen (penalty 50); a word containing one gets no pattern
      hyphenation.
- [ ] SHY, ZWSP and U+FEFF are never shaped; ZWSP gives a free break with no hyphen.
- [ ] `-`/U+2010 between a letter or digit and a letter, and `—`/`–` before a letter or digit, allow a break after
      the character with no added hyphen (penalty 50, flagged).
- [ ] Pattern hyphenation runs only for words ≥ 5 bytes, letter runs ≥ 5 letters, hyphenating blocks and non-web
      words; penalty 120, flagged, width of the hyphen (×0.68 for sup/sub).
- [ ] Web-link words break only after a single `/` or before a `.` not preceded by `.`, and never get a drawn hyphen.
- [ ] A piece wider than 0.98·avail is split at code points into segments of at most about 0.95·avail, with
      unflagged penalties of 100 between them.
- [ ] Equal-offset cuts keep the smallest kind; style-span starts inside a word split pieces but are not breaks.
- [ ] Every paragraph ends with a fill glue (stretch 100000) and a flagged forced break.
- [ ] Justified blocks: optimal at tolerance 2, then at 6, then greedy; other alignments: greedy only.
- [ ] Non-last justified lines end at the column edge; last lines and other alignments never stretch; the shrink
      ratio is never below −1.
- [ ] A break at a pattern or soft hyphen appends the run `shape("-", style)` with `start == end == line.end`,
      `link == -1`, and flags without Link/NoteRef.
- [ ] Center offset is `(lineW − x)/2`, Right offset is `lineW − x`; negative offsets become 0; the left margin is
      added to every run.
- [ ] `lines[0].start == 0`; a later line starts at its first piece; `line.end` is the end of its last piece; a line
      without pieces is empty at the previous end.
- [ ] Sup/sub runs are 0.68 × size, with baselines at −0.36·size / +0.2·size (block size).

Caches and positions
- [ ] `block()` always caches the full layout and fills missing metrics; `metrics()` inside `countStep` does not
      cache full layouts.
- [ ] A page-height-only change keeps text layouts, re-lays out image blocks, and swaps in the remembered count of
      the other height (only one is remembered).
- [ ] Any other parameter change, `setDocument` or `invalidate` drops everything, including the remembered height.
- [ ] `trimCache` acts only above 500 cached layouts and keeps those within 160 blocks of the centre.
- [ ] `normalize` clamps negatives and skips past the ends of blocks; `next`/`prev` step by line across blocks;
      `prev(first) == first`.
- [ ] `posForOffset` gives the last line starting at or before the offset (block clamped; endPos without blocks);
      `offsetOf` gives the line start (0 at the end).

Pagination, counting, hit testing
- [ ] The first line of a page is always placed; later lines need `y + h ≤ H + 0.01`.
- [ ] The gap between blocks is `max(spaceAfter, spaceBefore)`, and no gap is added at the page top.
- [ ] A `pageBreakBefore` block always starts a new page.
- [ ] A keep-with-next block not at the page top needs room for itself plus two following lines (with gaps), unless
      it is taller than the page.
- [ ] `pageStartBefore` at a chapter start or at `endPos()` returns the forward page start of the chapter (scan
      ≤ 3000 blocks, ≤ 2000 pages); elsewhere it estimates, moves forward until the page reaches the target, then
      back while it still does, never crossing a chapter start; at or before the first line it returns the first
      line.
- [ ] `countStep` does at least one page per call, records each start before paginating it, sets done at the end,
      and matches manual forward pagination.
- [ ] `countProgress` is `countPos.block / blockCount` (1 when done); `pageIndexOf` is the last start ≤ p (0 when
      there are none).
- [ ] `hitTest` first returns the nearest run with `link ≥ 0` within `linkSlop` (squared distance, first wins ties);
      otherwise the first line containing y, with offset = run start under x or the line start; false outside all
      lines.
- [ ] All checks of `testTextLayout` pass (§5).
