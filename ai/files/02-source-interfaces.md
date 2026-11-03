# Source: every header, the entry point and the platform, theme and settings code

Every header of the code base (the interfaces the specifications in ai/spec implement), the entry point, and the three .cpp files that are data or operating-system glue rather than algorithms: the colour themes, the settings file format and the platform layer. The other .cpp files are specified in ai/spec/03-10.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `src/main.cpp` | 787 | `9b754c32cd307803…` |
| `src/core/Unicode.h` | 2735 | `88d547b7f38687f0…` |
| `src/core/Encoding.h` | 1173 | `4ce1993fcd40a5fd…` |
| `src/core/XmlReader.h` | 1579 | `e9a9a6016aa311af…` |
| `src/core/Document.h` | 3663 | `06027bbe2005651d…` |
| `src/core/FileUtil.h` | 468 | `9b03450f023c2ac2…` |
| `src/core/ImageCodec.h` | 723 | `696311857145df0f…` |
| `src/core/Fb2Parser.h` | 900 | `0c5d076f08796f96…` |
| `src/core/TxtParser.h` | 993 | `ccc84b8cf29eceda…` |
| `src/core/BookLoader.h` | 1698 | `b5b56f11191f5073…` |
| `src/core/Hyphenator.h` | 1635 | `d066f3b9fff55496…` |
| `src/core/LineBreaker.h` | 1934 | `ce054f2e0656385b…` |
| `src/core/LibrarySearch.h` | 5046 | `f9f3bb4f380acffe…` |
| `src/text/FontLibrary.h` | 2312 | `7d67b5caea1978b0…` |
| `src/text/Shaper.h` | 1801 | `94461a78d653134d…` |
| `src/text/BookLayout.h` | 5623 | `8c8feaf16119dfbe…` |
| `src/render/Gl.h` | 343 | `ad1f61dd579aeb4f…` |
| `src/render/GlCommon.h` | 1984 | `162194be9b27332e…` |
| `src/render/GlyphAtlas.h` | 1671 | `02371af1da7c963c…` |
| `src/render/Renderer2D.h` | 2181 | `de256647dac0c306…` |
| `src/render/PageTurn.h` | 1709 | `f9429e0bf1ad6e6a…` |
| `src/platform/Platform.h` | 2270 | `615d3c491c1fd49e…` |
| `src/platform/Platform.cpp` | 9811 | `887ec12d796cd747…` |
| `src/app/Themes.h` | 826 | `0c7f9ee0736eda95…` |
| `src/app/Themes.cpp` | 1834 | `1256c9440d0e3626…` |
| `src/app/Settings.h` | 2768 | `bb33c67c1386daef…` |
| `src/app/Settings.cpp` | 6562 | `37b747da2ae517d3…` |
| `src/app/UiHelpers.h` | 5619 | `9f327b9361356cd5…` |
| `src/app/App.h` | 14266 | `32e6bd01fd10f9ae…` |

## `src/main.cpp`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - entry point. SDL3 main callbacks give the same app model on Windows, Android, iOS and the web.
#define SDL_MAIN_USE_CALLBACKS 1
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>

#include "app/App.h"

SDL_AppResult SDL_AppInit(void** appstate, int argc, char** argv) {
  auto* app = new ll::App();
  *appstate = app;
  return app->init(argc, argv) ? SDL_APP_CONTINUE : SDL_APP_FAILURE;
}

SDL_AppResult SDL_AppIterate(void* appstate) { return static_cast<ll::App*>(appstate)->iterate(); }

SDL_AppResult SDL_AppEvent(void* appstate, SDL_Event* event) {
  return static_cast<ll::App*>(appstate)->handleEvent(*event);
}

void SDL_AppQuit(void* appstate, SDL_AppResult) {
  auto* app = static_cast<ll::App*>(appstate);
  if (!app) return;
  app->shutdown();
  delete app;
}
```

## `src/core/Unicode.h`

UTF-8 without BOM, LF line endings, ends with a newline.

```cpp
// Lanternleaf - UTF-8 / Unicode helpers (portable, no dependencies).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace ll {

constexpr char32_t kReplacementChar = 0xFFFD;
constexpr char32_t kNbsp = 0x00A0;
constexpr char32_t kSoftHyphen = 0x00AD;

// Decodes the code point that starts at s[i] and advances i past it.
// Malformed input yields U+FFFD and consumes exactly one byte, so decoding never stalls.
char32_t utf8Decode(std::string_view s, size_t& i);

// Appends `cp` encoded as UTF-8.
void utf8Append(std::string& out, char32_t cp);

std::u32string utf8ToU32(std::string_view s);
std::string u32ToUtf8(std::u32string_view s);

// Validates UTF-8. Optionally reports the number of multi-byte sequences and of errors found.
bool utf8Validate(std::string_view s, size_t* multiByteSeqs = nullptr, size_t* errors = nullptr);

// Number of code points.
size_t utf8Length(std::string_view s);

// Moves `pos` back to the start of the code point that contains it.
size_t utf8AlignBack(std::string_view s, size_t pos);

// Byte offset of the code point that follows the one starting at `pos`.
size_t utf8NextPos(std::string_view s, size_t pos);
// Byte offset of the code point that precedes `pos` (0 if at start).
size_t utf8PrevPos(std::string_view s, size_t pos);

// Simple (1:1) case mapping covering Latin, Latin-1, Latin Extended-A, Greek and Cyrillic.
char32_t toLowerCp(char32_t c);
char32_t toUpperCp(char32_t c);

bool isSpaceCp(char32_t c);        // breaking white space (NBSP is *not* included)
bool isLetterCp(char32_t c);       // letters of the scripts we care about (+ generic fallback)
bool isDigitCp(char32_t c);
bool isCyrillicCp(char32_t c);
bool isLatinLetterCp(char32_t c);
bool isCombiningMarkCp(char32_t c);
bool isDashCp(char32_t c);         // hyphen-minus, hyphen, en dash, em dash ...
bool isOpeningPunctCp(char32_t c); // quotes / brackets that "stick" to the following word

// Search normalisation: lowercase, 'ё'->'е', typographic quotes/dashes folded to ASCII.
// Always maps one code point to exactly one code point (keeps code point indices stable).
char32_t foldForSearchCp(char32_t c);
std::string foldForSearch(std::string_view utf8);

std::string toLowerUtf8(std::string_view s);

std::string_view trimView(std::string_view s);
std::string trimCopy(std::string_view s);

// Collapses runs of white space into single spaces and trims.
std::string collapseSpaces(std::string_view s);

// Case-insensitive ASCII comparison helpers.
bool iequalsAscii(std::string_view a, std::string_view b);
bool endsWithNoCase(std::string_view s, std::string_view suffix);
bool startsWith(std::string_view s, std::string_view prefix);

}  // namespace ll
```

## `src/core/Encoding.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - character set detection and conversion to UTF-8.
// Books in the wild (especially Russian FB2/TXT) come in UTF-8, UTF-16, Windows-1251, KOI8-R, CP866 ...
#pragma once

#include <string>
#include <string_view>

namespace ll {

enum class Charset { Unknown, Utf8, Utf16LE, Utf16BE, Cp1251, Koi8R, Cp866, Iso8859_5, Cp1252 };

const char* charsetName(Charset cs);
Charset charsetFromName(std::string_view name);

// Detects a byte order mark. Returns the charset and the BOM length (0 when there is no BOM).
Charset detectBom(std::string_view bytes, size_t& bomLen);

// Heuristic detection for data without a BOM: UTF-16 (zero-byte pattern), UTF-8 (validity),
// then Russian single-byte charsets (letter-frequency scoring) and finally Windows-1252.
Charset detectCharset(std::string_view bytes);

// Converts `bytes` in charset `cs` to UTF-8 (BOM must already be stripped).
std::string decodeToUtf8(std::string_view bytes, Charset cs);

// Full pipeline: strips the BOM, uses `hint` when given (and plausible), otherwise detects.
std::string bytesToUtf8(std::string_view bytes, Charset hint = Charset::Unknown, Charset* used = nullptr);

}  // namespace ll
```

## `src/core/XmlReader.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - small, forgiving XML pull parser.
// FB2 files found on the internet are frequently malformed (bad entities, stray '<', unclosed tags),
// so this reader never fails: it reports what it can and treats garbage as text.
#pragma once

#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace ll {

class XmlReader {
 public:
  enum class Token { StartTag, EndTag, Text, End };

  explicit XmlReader(std::string_view utf8) : s_(utf8) {}

  Token next();

  // Local name of the current start/end tag (namespace prefix removed), e.g. "p", "section".
  std::string_view name() const { return name_; }
  bool selfClosing() const { return selfClosing_; }
  // Attribute value by local name ("href" matches "l:href" and "xlink:href"). Empty if missing.
  std::string_view attr(std::string_view localName) const;
  bool hasAttr(std::string_view localName) const;
  // Entity-decoded text of the current Text token.
  const std::string& text() const { return text_; }
  // Current byte position (for progress reporting / early exit).
  size_t position() const { return pos_; }

 private:
  void parseTag();
  void readText();

  std::string_view s_;
  size_t pos_ = 0;
  std::string_view name_;
  bool selfClosing_ = false;
  bool pendingEnd_ = false;  // a self-closing tag produces Start then End
  std::string text_;
  std::vector<std::pair<std::string_view, std::string>> attrs_;
};

// Decodes XML/HTML entities in `in` and appends the result to `out`.
void xmlDecodeEntities(std::string_view in, std::string& out);

}  // namespace ll
```

## `src/core/Document.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - in-memory book model shared by the FB2 and TXT parsers, layout and search.
#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace ll {

// Inline style flags of a text span.
enum SpanFlag : uint8_t {
  kSpanItalic = 1,
  kSpanBold = 2,
  kSpanSup = 4,
  kSpanSub = 8,
  kSpanLink = 16,
  kSpanCode = 32,
  kSpanStrike = 64,
  kSpanNoteRef = 128,
};

// A style run: applies from `begin` (byte offset in Block::text) up to the next span's begin.
struct Span {
  uint32_t begin = 0;
  uint8_t flags = 0;
  int32_t link = -1;  // index into Document::links when flags has kSpanLink
};

enum class BlockType : uint8_t {
  Paragraph,
  Title,           // level: 0 = book/body title, 1.. = section depth
  Subtitle,
  Epigraph,
  EpigraphAuthor,
  PoemTitle,
  Verse,
  Cite,
  CiteAuthor,
  TextAuthor,
  Annotation,
  EmptyLine,
  Separator,       // centred "* * *" and similar
  TableRow,
  Image,
};

struct Block {
  BlockType type = BlockType::Paragraph;
  uint8_t level = 0;
  bool pageBreakBefore = false;
  bool stanzaStart = false;   // first verse of a stanza: a little extra space above
  bool notes = false;         // block belongs to a notes/comments body
  int image = -1;             // index into Document::images for BlockType::Image
  std::string text;           // UTF-8, white space already normalised
  std::vector<Span> spans;    // sorted by begin; empty means "all regular"
  uint64_t charStart = 0;     // code points preceding this block (progress / percent)
};

struct ImageData {
  std::string id;
  std::string mime;
  std::vector<unsigned char> bytes;  // encoded (JPEG / PNG / GIF ...)
  int width = 0;                     // probed without decoding; 0 when unknown/unsupported
  int height = 0;
};

struct TocEntry {
  std::string title;
  int block = 0;
  int level = 0;
};

struct Anchor {
  int block = 0;     // first block of the element carrying the id
  int endBlock = 0;  // one past the last block (sections), block + 1 for paragraphs
};

struct BookMeta {
  std::string title;
  std::vector<std::string> authors;
  std::string series;
  int seriesIndex = 0;
  std::string lang;
  std::vector<std::string> genres;
  std::string annotation;
  std::string format;    // "FB2", "TXT", "FB2 (zip)" ...
  std::string encoding;  // charset that was used to decode the file
  std::string authorsJoined() const;
};

struct Document {
  BookMeta meta;
  std::vector<Block> blocks;
  std::vector<TocEntry> toc;
  std::vector<ImageData> images;
  std::vector<std::string> links;  // link targets as written in the file ("#n1", "http://...")
  std::unordered_map<std::string, Anchor> anchors;
  uint64_t totalChars = 0;
  int coverImage = -1;

  // Fills Block::charStart / totalChars and turns web addresses written as plain text into links.
  // Call after the block list is final.
  void finalize();

  // Index of the TOC entry that contains `block` (-1 when before the first entry).
  int tocIndexForBlock(int block) const;

  // Plain text of the blocks in [first, last) joined by new lines (used for footnote pop-ups).
  std::string plainText(int first, int last) const;
};

// Returns the style flags in effect at byte `offset` of `b`.
uint8_t spanFlagsAt(const Block& b, uint32_t offset, int32_t* link = nullptr);

// A link that leaves the book (http, https, ftp, mailto) rather than pointing inside it ("#note1").
bool isWebLink(const std::string& target);

// Finds web addresses (http://, https://, ftp://, www.) in plain text: [begin, end) byte ranges.
std::vector<std::pair<size_t, size_t>> findWebAddresses(const std::string& text);

}  // namespace ll
```

## `src/core/FileUtil.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - small file helpers working with UTF-8 paths.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace ll {

// Writes to "<path>.tmp" and renames over `path`, so a crash never leaves a half-written file.
bool writeFileAtomic(const std::string& path, std::string_view data);
bool fileExists(const std::string& path);
bool isDirectory(const std::string& path);
uint64_t fileSize(const std::string& path);

}  // namespace ll
```

## `src/core/ImageCodec.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - image probing/decoding for pictures embedded in books (stb_image).
#pragma once

#include <cstddef>
#include <vector>

namespace ll {

// Reads only the header. Returns false for unsupported/corrupt data.
bool probeImageSize(const unsigned char* data, size_t size, int& width, int& height);

// Decodes to tightly packed RGBA8 (row 0 = top). Returns false on failure.
bool decodeImageRgba(const unsigned char* data, size_t size, std::vector<unsigned char>& rgba, int& width,
                     int& height);

// Writes RGBA8 pixels (row 0 = top) as PNG. Used by the screenshot/self-test mode.
bool writePngRgba(const char* utf8Path, const unsigned char* rgba, int width, int height);

}  // namespace ll
```

## `src/core/Fb2Parser.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - FictionBook 2 (FB2) parser.
#pragma once

#include <string>
#include <string_view>

#include "core/Document.h"
#include "core/Encoding.h"

namespace ll {

struct Fb2Options {
  bool loadImages = true;
};

// Converts raw FB2 bytes to UTF-8 honouring the BOM / XML declaration (with detection fallback).
std::string fb2ToUtf8(std::string_view raw, Charset* used = nullptr);

// Parses a complete book. Never throws; returns false only when nothing usable was found.
bool parseFb2(std::string_view raw, Document& doc, std::string* error = nullptr, const Fb2Options& opt = {});

// Parses <description> only (fast path for library search).
bool parseFb2Meta(std::string_view raw, BookMeta& meta);

// Extracts metadata and the readable text (no binaries, no markup) for full-text search.
void fb2ExtractText(std::string_view raw, std::string& text, BookMeta* meta);

}  // namespace ll
```

## `src/core/TxtParser.h`

UTF-8 without BOM, LF line endings, ends with a newline.

```cpp
// Lanternleaf - plain text (TXT) book parser.
// Detects the encoding, reconstructs paragraphs from hard-wrapped / indented / blank-line separated
// text and recognises chapter headings ("Chapter 1", "Глава 1", "* * *") for the table of contents.
#pragma once

#include <string>
#include <string_view>

#include "core/Document.h"

namespace ll {

enum class TxtParagraphMode { BlankLines, Indented, EveryLine };

// `fileStem` (file name without extension) is used for the title when the text has no obvious one.
bool parseTxt(std::string_view raw, Document& doc, std::string_view fileStem, std::string* error = nullptr);

// Decoding + light metadata guess (title/author from "Author - Title" file names).
void txtExtractText(std::string_view raw, std::string& text, BookMeta* meta, std::string_view fileStem);

// Exposed for tests.
TxtParagraphMode detectTxtParagraphMode(std::string_view utf8);
void guessMetaFromFileStem(std::string_view stem, BookMeta& meta);

}  // namespace ll
```

## `src/core/BookLoader.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - file access for books: format detection, zip unpacking, metadata and text extraction.
#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>

#include "core/Document.h"

namespace ll {

enum class BookFormat : uint8_t { Unknown, Fb2, Txt, Fb2Zip, TxtZip, Zip };

// UTF-8 <-> std::filesystem::path (Windows paths are wide; never go through the ANSI code page).
std::filesystem::path pathFromUtf8(std::string_view utf8);
std::string pathToUtf8(const std::filesystem::path& p);

BookFormat formatFromName(std::string_view fileName);
bool isSupportedBookName(std::string_view fileName);
// File name without directories and without .fb2/.txt/.zip extensions.
std::string fileStemOf(std::string_view path);
std::string fileNameOf(std::string_view path);

bool readFile(const std::string& path, std::string& out, size_t maxBytes = SIZE_MAX, std::string* err = nullptr);

// Raw (still encoded) book content. Zip archives (also mis-named ones) are unpacked: the first .fb2
// entry, otherwise the largest .txt entry. `contentFormat` is Fb2 or Txt on success.
bool readBookRaw(const std::string& path, std::string& raw, BookFormat& contentFormat, std::string* err,
                 size_t maxBytes = SIZE_MAX, bool* zipped = nullptr);

bool loadBook(const std::string& path, Document& doc, std::string* err);
bool loadBookMeta(const std::string& path, BookMeta& meta, std::string* err);
bool loadBookText(const std::string& path, std::string& text, BookMeta* meta, std::string* err);

// Identity of a book that survives renames and moves: size + hash of the first 64 KiB.
std::string bookFingerprint(const std::string& path);

}  // namespace ll
```

## `src/core/Hyphenator.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - Liang/TeX pattern hyphenation (the algorithm used by TeX, LibreOffice, FBReader, KOReader).
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace ll {

class Hyphenator {
 public:
  // `patterns`: one TeX pattern per line ("a1b2c"), `exceptions`: words with '-' at allowed breaks.
  bool load(std::string_view patterns, std::string_view exceptions, int leftMin, int rightMin);
  bool empty() const { return patternCount_ == 0; }
  size_t patternCount() const { return patternCount_; }

  // `word` must be lowercase letters only. Appends positions i (leftMin <= i <= size-rightMin) where a
  // hyphen may be inserted between word[i-1] and word[i].
  void hyphenate(std::u32string_view word, std::vector<int>& breaks) const;

 private:
  int child(int node, char32_t c) const;

  std::unordered_map<uint64_t, int32_t> edges_;
  std::vector<int32_t> values_;  // per node: index into pool_ or -1
  std::vector<std::vector<uint8_t>> pool_;
  std::unordered_map<std::u32string, std::vector<int>> exceptions_;
  int leftMin_ = 2;
  int rightMin_ = 2;
  size_t patternCount_ = 0;
};

// Chooses the language by script: Cyrillic words use Russian patterns, Latin words English ones.
class HyphenationService {
 public:
  Hyphenator& english() { return en_; }
  Hyphenator& russian() { return ru_; }
  // `letters` may be mixed case; only letters (no punctuation). Results as in Hyphenator::hyphenate.
  void hyphenate(std::u32string_view letters, std::vector<int>& breaks) const;

 private:
  Hyphenator en_;
  Hyphenator ru_;
};

}  // namespace ll
```

## `src/core/LineBreaker.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - paragraph line breaking on an abstract box/glue/penalty model.
// Optimal fit = the Knuth-Plass "total fit" algorithm used by TeX; greedy = classic first fit.
#pragma once

#include <cstdint>
#include <vector>

namespace ll {

constexpr float kLbInfPenalty = 10000.f;
constexpr float kLbFillStretch = 100000.f;  // stretch of the paragraph-final "fil" glue

struct LbItem {
  enum Type : uint8_t { Box, Glue, Penalty };
  Type type = Box;
  bool flagged = false;  // hyphenation penalties (consecutive flagged breaks are discouraged)
  float width = 0;
  float stretch = 0;
  float shrink = 0;
  float penalty = 0;  // >= kLbInfPenalty: never break, <= -kLbInfPenalty: forced break
  int tag = -1;       // caller data (index of the fragment etc.)
};

struct LbBreak {
  int item = 0;       // index of the glue/penalty item where the line ends
  float ratio = 0;    // adjustment ratio of that line (>0 stretch, <0 shrink)
};

struct LbParams {
  float tolerance = 2.0f;
  float linePenalty = 10.f;
  float flaggedDemerits = 6000.f;  // two hyphenated lines in a row
  float fitnessDemerits = 200.f;   // a tight line next to a loose one
};

float lbLineWidth(const std::vector<float>& widths, int line);

// Diagnostics: how often the optimal algorithm succeeded / needed the greedy fallback.
struct LbStats {
  uint64_t optimalOk = 0;
  uint64_t optimalFail = 0;
  uint64_t greedy = 0;
};
LbStats& lbStats();

// Items must end with a forced break. Returns false when no feasible solution exists for the tolerance.
bool breakLinesOptimal(const std::vector<LbItem>& items, const std::vector<float>& lineWidths, const LbParams& p,
                       std::vector<LbBreak>& out);

// First fit: always succeeds (a box wider than the line overflows).
void breakLinesGreedy(const std::vector<LbItem>& items, const std::vector<float>& lineWidths,
                      std::vector<LbBreak>& out);

}  // namespace ll
```

## `src/core/LibrarySearch.h`

UTF-8 without BOM, LF line endings, ends with a newline.

```cpp
// Lanternleaf - finds books on local drives by file name, metadata (title/author/series) or text inside.
// Runs on a background thread; results stream in while the scan is in progress.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <vector>

namespace ll {

// ---- query matching -------------------------------------------------------------------------

// Latin "skeleton" that makes transliterated names comparable: "Толстой" ~ "Tolstoy" ~ "Tolstoj".
std::string translitSkeleton(std::string_view folded);

class QueryMatcher {
 public:
  explicit QueryMatcher(std::string_view query);
  bool empty() const { return terms_.empty(); }
  size_t termCount() const { return terms_.size(); }
  // Marks in `termMask` (one bit per term, max 32) the terms found in `field` (raw UTF-8 text).
  uint32_t matchField(std::string_view field) const;
  uint32_t allTermsMask() const { return terms_.size() >= 32 ? 0xFFFFFFFFu : ((1u << terms_.size()) - 1u); }
  // Whole-phrase search inside a long text; returns the byte offset in `text` or npos.
  size_t findPhrase(std::string_view text) const;
  const std::string& phrase() const { return phrase_; }

 private:
  std::vector<std::string> terms_;
  std::vector<std::string> skeletons_;
  std::string phrase_;
};

// Maps a byte offset in foldForSearch(original) back to a byte offset in `original`.
size_t originalOffsetForFolded(std::string_view original, size_t foldedOffset);
// ~`radius` characters of context around byte offset `pos` (single line, ellipsised).
std::string makeSnippet(std::string_view text, size_t pos, size_t matchLen, size_t radius = 70);

// ---- metadata cache -------------------------------------------------------------------------

struct MetaRecord {
  uint64_t size = 0;
  int64_t mtime = 0;
  bool isBook = true;
  std::string title, authors, series, lang, format;
};

class MetaCache {
 public:
  bool load(const std::string& file);
  bool save(const std::string& file);
  bool get(const std::string& path, uint64_t size, int64_t mtime, MetaRecord& out) const;
  void put(const std::string& path, const MetaRecord& rec);
  size_t size() const;

 private:
  mutable std::mutex m_;
  std::unordered_map<std::string, MetaRecord> map_;
  bool dirty_ = false;
};

// ---- search ---------------------------------------------------------------------------------

enum MatchFlag : uint8_t {
  kMatchName = 1,
  kMatchTitle = 2,
  kMatchAuthor = 4,
  kMatchSeries = 8,
  kMatchText = 16,
  kMatchAny = 32,  // empty query: every book found is listed
};

struct SearchOptions {
  std::string query;
  std::vector<std::string> roots;  // UTF-8 folder paths
  bool byFileName = true;
  bool byMeta = true;
  bool byContent = false;
  bool skipSystemDirs = true;
  uint64_t minTxtBytes = 16 * 1024;  // tiny .txt files are almost never books
  bool skipNonBookTxt = true;        // LICENSE.txt, readme.txt, changelog.txt ...
  // Optional platform hook: return true to skip reading a file (e.g. cloud placeholders).
  std::function<bool(const std::string&)> skipContent;
};

struct SearchHit {
  std::string path;
  std::string title, authors, series, format;
  uint64_t size = 0;
  uint8_t matched = 0;
  std::string snippet;
};

class LibrarySearch {
 public:
  explicit LibrarySearch(MetaCache& cache) : cache_(cache) {}
  ~LibrarySearch();
  LibrarySearch(const LibrarySearch&) = delete;
  LibrarySearch& operator=(const LibrarySearch&) = delete;

  void start(SearchOptions opt);
  void cancel();
  void wait();
  bool running() const { return running_.load(); }

  struct Progress {
    uint64_t files = 0, dirs = 0, books = 0, matches = 0;
    std::string currentDir;
    double seconds = 0;
    bool finished = false;
    bool cancelled = false;
  };
  Progress progress() const;
  std::vector<SearchHit> takeHits();
  // Called from the worker thread (throttled) when something changed; use it to wake the UI.
  void setNotify(std::function<void()> fn) { notify_ = std::move(fn); }

  static bool isSkippedDirName(std::string_view name);
  static bool isNonBookTextName(std::string_view stem);

 private:
  void run(SearchOptions opt);
  void processFile(const SearchOptions& opt, const QueryMatcher& qm, const std::string& path,
                   const std::string& name, uint64_t size, int64_t mtime);
  void pushHit(SearchHit&& h);
  void maybeNotify(bool force);

  MetaCache& cache_;
  std::thread worker_;
  std::atomic<bool> running_{false};
  std::atomic<bool> cancel_{false};
  std::atomic<uint64_t> files_{0}, dirs_{0}, books_{0}, matches_{0};
  mutable std::mutex m_;
  std::vector<SearchHit> hits_;
  std::string currentDir_;
  bool finished_ = false;
  bool cancelled_ = false;
  std::chrono::steady_clock::time_point startTime_{};
  std::chrono::steady_clock::time_point endTime_{};
  std::chrono::steady_clock::time_point lastNotify_{};
  std::function<void()> notify_;
};

}  // namespace ll
```

## `src/text/FontLibrary.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - font faces (FreeType for rasterisation, HarfBuzz for shaping).
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

typedef struct FT_LibraryRec_* FT_Library;
typedef struct FT_FaceRec_* FT_Face;
typedef struct hb_face_t hb_face_t;
typedef struct hb_font_t hb_font_t;

namespace ll {

struct FontFace {
  std::string name;
  std::vector<unsigned char> data;  // the face references this memory
  FT_Face ft = nullptr;
  hb_face_t* hbFace = nullptr;
  hb_font_t* hbFont = nullptr;
  int upem = 1000;
  // Metrics in em units (font units / upem). descender is positive (distance below the baseline).
  float ascender = 0.8f;
  float descender = 0.2f;
  float xHeight = 0.5f;
  float capHeight = 0.7f;
  float spaceAdvance = 0.25f;
  float hyphenAdvance = 0.33f;
  uint32_t currentSize26_6 = 0;  // FreeType size currently selected

  bool hasChar(char32_t cp) const;
};

class FontLibrary {
 public:
  FontLibrary();
  ~FontLibrary();
  FontLibrary(const FontLibrary&) = delete;
  FontLibrary& operator=(const FontLibrary&) = delete;

  bool ok() const { return lib_ != nullptr; }
  // Returns the face id or -1. `faceIndex` selects a face inside .ttc collections.
  int addFromMemory(std::vector<unsigned char> data, const std::string& name, int faceIndex = 0);
  int addFromFile(const std::string& utf8Path, int faceIndex = 0);
  FontFace& face(int id) { return *faces_[static_cast<size_t>(id)]; }
  const FontFace& face(int id) const { return *faces_[static_cast<size_t>(id)]; }
  int count() const { return static_cast<int>(faces_.size()); }
  // Selects the pixel size for rasterisation (cached per face).
  void setPixelSize(int id, float sizePx);

 private:
  FT_Library lib_ = nullptr;
  std::vector<std::unique_ptr<FontFace>> faces_;
};

// Up to four styles of one typeface; missing styles fall back to the closest available one.
struct FontFamily {
  std::string name;
  int faces[4] = {-1, -1, -1, -1};  // index = (bold ? 2 : 0) | (italic ? 1 : 0)
  int face(int style) const {
    style &= 3;
    if (faces[style] >= 0) return faces[style];
    if (faces[style & 2] >= 0) return faces[style & 2];
    if (faces[style & 1] >= 0) return faces[style & 1];
    return faces[0];
  }
  bool valid() const { return faces[0] >= 0; }
};

}  // namespace ll
```

## `src/text/Shaper.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - text shaping with HarfBuzz (kerning, ligatures, marks) and per-character font fallback.
// Results are resolution independent (em units) and cached, so changing the font size never re-shapes.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

#include "text/FontLibrary.h"

typedef struct hb_buffer_t hb_buffer_t;

namespace ll {

struct ShapedGlyph {
  uint16_t face = 0;
  uint16_t glyph = 0;
  float x = 0;  // em, relative to the run origin
  float y = 0;  // em, positive = up
};

struct ShapedRun {
  std::vector<ShapedGlyph> glyphs;
  float advance = 0;  // em
};

class Shaper {
 public:
  explicit Shaper(FontLibrary& lib);
  ~Shaper();
  Shaper(const Shaper&) = delete;
  Shaper& operator=(const Shaper&) = delete;

  void setFamily(const FontFamily& family);
  void setFallbacks(std::vector<int> faces) { fallbacks_ = std::move(faces); }
  const FontFamily& family() const { return family_; }
  FontLibrary& library() { return lib_; }

  // `style` = (bold ? 2 : 0) | (italic ? 1 : 0). The reference stays valid until clear().
  const ShapedRun& shape(std::string_view utf8, int style);
  float spaceWidth(int style) const;   // em
  float hyphenWidth(int style) const;  // em
  const FontFace& primary(int style) const { return lib_.face(family_.face(style)); }

  void clear();
  size_t cacheSize() const { return cache_.size(); }

 private:
  int pickFace(char32_t cp, int primaryFace) const;
  void shapeSegment(std::string_view text, size_t begin, size_t end, int faceId, float& x, ShapedRun& out);

  FontLibrary& lib_;
  FontFamily family_;
  std::vector<int> fallbacks_;
  std::unordered_map<std::string, ShapedRun> cache_;
  std::string key_;
  hb_buffer_t* buf_ = nullptr;
};

}  // namespace ll
```

## `src/text/BookLayout.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - reflowable layout: paragraphs -> lines (Knuth-Plass + hyphenation) -> pages.
//
// Positions are (block, line) pairs. Pages are built on demand from any line, forwards or backwards, so
// a font-size change only lays out the paragraphs around the reading position. Page numbers come from a
// background pass (countStep) that paginates the whole book in small time slices.
#pragma once

#include <algorithm>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "core/Document.h"
#include "core/Hyphenator.h"
#include "text/Shaper.h"

namespace ll {

struct LayoutParams {
  float fontSize = 20.f;          // px, body text
  float lineSpacing = 1.35f;      // multiple of the font size
  float pageWidth = 600.f;        // px, text column
  float pageHeight = 800.f;       // px
  float paragraphIndent = 1.5f;   // em, first-line indent
  float paragraphSpacing = 0.f;   // em, extra space between paragraphs
  bool justify = true;
  bool hyphenate = true;
  int fontGeneration = 0;         // bump when the typeface changes
  bool operator==(const LayoutParams&) const = default;
};

struct PlacedRun {
  const ShapedRun* run = nullptr;
  float x = 0;         // px from the left edge of the text column
  float baseline = 0;  // px from the top of the line
  float size = 0;      // px
  float width = 0;     // px
  uint8_t flags = 0;   // SpanFlag bits (block style included)
  int32_t link = -1;
  uint32_t start = 0;  // byte range in Block::text
  uint32_t end = 0;
};

struct LayoutLine {
  float height = 0;
  uint32_t start = 0;
  uint32_t end = 0;
  std::vector<PlacedRun> runs;
};

struct BlockLayout {
  std::vector<LayoutLine> lines;
  float spaceBefore = 0;
  float spaceAfter = 0;
  bool keepWithNext = false;
  bool pageBreakBefore = false;
  int image = -1;
  float imageX = 0, imageY = 0, imageW = 0, imageH = 0;  // px, relative to the column / line top
};

struct BlockMetrics {
  std::vector<float> lineHeights;
  std::vector<uint32_t> lineStarts;
  float spaceBefore = 0;
  float spaceAfter = 0;
  bool keepWithNext = false;
  bool pageBreakBefore = false;
};

struct LinePos {
  int block = 0;
  int line = 0;
  friend bool operator==(const LinePos&, const LinePos&) = default;
  friend auto operator<=>(const LinePos&, const LinePos&) = default;
};

struct PageLine {
  LinePos pos;
  float y = 0;  // px from the top of the text area
};

struct Page {
  LinePos start;
  LinePos end;  // exclusive
  std::vector<PageLine> lines;
  bool empty() const { return lines.empty(); }
};

struct HitResult {
  int block = -1;
  uint32_t offset = 0;
  int32_t link = -1;
  uint8_t flags = 0;
};

class BookLayout {
 public:
  BookLayout(Shaper& shaper, const HyphenationService* hyph) : shaper_(shaper), hyph_(hyph) {}

  void setDocument(const Document* doc);
  // A change of the page height alone (the menu bars come or go) keeps the broken lines, and the page count of
  // the previous height, so switching back restores those page numbers at once.
  void setParams(const LayoutParams& p);
  const LayoutParams& params() const { return params_; }
  const Document* document() const { return doc_; }
  void invalidate();  // drops every cached layout (call after Shaper::clear())

  int blockCount() const { return doc_ ? static_cast<int>(doc_->blocks.size()) : 0; }
  const BlockLayout& block(int index);
  const BlockMetrics& metrics(int index);

  LinePos normalize(LinePos p);
  bool isEnd(LinePos p) const { return p.block >= blockCount(); }
  LinePos endPos() const { return LinePos{blockCount(), 0}; }
  LinePos next(LinePos p);
  LinePos prev(LinePos p);

  Page pageFrom(LinePos start);
  LinePos pageStartBefore(LinePos start);
  LinePos posForOffset(int block, uint32_t byteOffset);
  uint32_t offsetOf(LinePos p);

  // `linkSlop`: how far (px) around a link a press still counts as hitting it (fingers need more).
  bool hitTest(const Page& page, float x, float y, HitResult& out, float linkSlop = 8.0f);

  // Background pagination for page numbers.
  void countStep(double budgetMs);
  bool countDone() const { return countDone_; }
  float countProgress() const;
  int pageCount() const { return static_cast<int>(pageStarts_.size()); }
  int pageIndexOf(LinePos p) const;
  LinePos pageStart(int index) const {
    if (pageStarts_.empty()) return LinePos{};
    return pageStarts_[static_cast<size_t>(std::clamp(index, 0, pageCount() - 1))];
  }

  // Keeps the full-layout cache bounded around the reading position.
  void trimCache(int centerBlock);
  size_t cachedFullBlocks() const { return full_.size(); }

 private:
  struct BlockStyle;
  BlockStyle styleFor(const Block& b) const;
  BlockLayout layoutBlock(int index);
  void layoutText(const Block& b, const BlockStyle& st, BlockLayout& out);
  const BlockMetrics& metricsImpl(int index, bool keepFull);
  float lineHeight(LinePos p) { return metrics(p.block).lineHeights[static_cast<size_t>(p.line)]; }

  Shaper& shaper_;
  const HyphenationService* hyph_;
  const Document* doc_ = nullptr;
  LayoutParams params_;
  std::unordered_map<int, BlockLayout> full_;
  std::vector<std::unique_ptr<BlockMetrics>> metrics_;
  bool keepFull_ = true;

  std::vector<LinePos> pageStarts_;
  LinePos countPos_;
  bool countDone_ = false;
  bool countStarted_ = false;
  // The page count of the other page height (see setParams).
  struct Pagination {
    float pageHeight = -1.0f;
    std::vector<LinePos> starts;
    LinePos pos;
    bool done = false;
    bool started = false;
  } otherHeight_;

  std::vector<int> hyphBreaks_;  // scratch
};

}  // namespace ll
```

## `src/render/Gl.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - OpenGL entry point. Desktop: OpenGL 4.1 core via glad. Android: OpenGL ES 3.0.
// All shaders are written in the common subset of GLSL 4.10 core and GLSL ES 3.00.
#pragma once

#if defined(__ANDROID__) || defined(LL_USE_GLES)
#include <GLES3/gl3.h>
#ifndef LL_GLES
#define LL_GLES 1
#endif
#else
#include <glad/glad.h>
#endif
```

## `src/render/GlCommon.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - GL helpers: shader programs, textures, render targets and a tiny matrix type.
#pragma once

#include <cstdint>
#include <string>

#include "render/Gl.h"

namespace ll {

struct Color {
  float r = 0, g = 0, b = 0, a = 1;
  static Color hex(uint32_t rgb, float alpha = 1.0f) {
    return Color{((rgb >> 16) & 0xFF) / 255.0f, ((rgb >> 8) & 0xFF) / 255.0f, (rgb & 0xFF) / 255.0f, alpha};
  }
  Color withAlpha(float alpha) const { return Color{r, g, b, alpha}; }
  Color scaled(float k) const { return Color{r * k, g * k, b * k, a}; }
  static Color mix(const Color& x, const Color& y, float t) {
    return Color{x.r + (y.r - x.r) * t, x.g + (y.g - x.g) * t, x.b + (y.b - x.b) * t, x.a + (y.a - x.a) * t};
  }
  uint32_t packed() const;  // RGBA8 little endian (R in the low byte)
  float luminance() const { return 0.2126f * r + 0.7152f * g + 0.0722f * b; }
};

struct Mat4 {
  float m[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};  // column major
  static Mat4 ortho(float left, float right, float bottom, float top, float nearZ, float farZ);
  static Mat4 perspective(float fovyRadians, float aspect, float nearZ, float farZ);
  static Mat4 lookAt(float ex, float ey, float ez, float cx, float cy, float cz, float ux, float uy, float uz);
  Mat4 operator*(const Mat4& o) const;
};

namespace gl {

// Prepends the right #version line (and precision for GLES) to a shader body.
std::string shaderSource(const char* body, bool fragment);
GLuint compileProgram(const char* vertexBody, const char* fragmentBody, std::string* log = nullptr);

struct Texture {
  GLuint id = 0;
  int width = 0;
  int height = 0;
  bool createRgba(const unsigned char* rgba, int w, int h, bool mipmaps);
  void destroy();
};

struct RenderTarget {
  GLuint fbo = 0;
  GLuint color = 0;
  GLuint depth = 0;
  int width = 0;
  int height = 0;
  bool ensure(int w, int h, bool withDepth);
  void destroy();
};

const char* glVersionString();

}  // namespace gl
}  // namespace ll
```

## `src/render/GlyphAtlas.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - dynamic glyph atlas: FreeType rasterises glyphs on demand (light hinting, 4 sub-pixel
// horizontal positions) into one R8 texture. When the atlas fills up it is cleared and refilled.
#pragma once

#include <cstdint>
#include <unordered_map>
#include <vector>

#include "render/Gl.h"
#include "text/FontLibrary.h"

namespace ll {

struct GlyphEntry {
  int16_t left = 0;  // bitmap offset from the pen position (px)
  int16_t top = 0;   // bitmap top above the baseline (px)
  uint16_t w = 0;
  uint16_t h = 0;
  float u0 = 0, v0 = 0, u1 = 0, v1 = 0;
};

class GlyphAtlas {
 public:
  static constexpr int kSubpixelBins = 4;

  bool init(int size = 2048);
  void shutdown();
  void reset();

  // Returns nullptr when the atlas is full (caller should reset() and redraw).
  const GlyphEntry* get(FontLibrary& lib, int face, uint16_t glyph, float sizePx, int subpixelBin);

  GLuint texture() const { return tex_; }
  int size() const { return size_; }
  float whiteU() const { return whiteUV_; }
  float whiteV() const { return whiteUV_; }
  float fill() const { return static_cast<float>(shelfY_) / static_cast<float>(size_); }
  bool overflowed() const { return overflowed_; }
  void clearOverflow() { overflowed_ = false; }
  uint32_t generation() const { return generation_; }

 private:
  bool allocate(int w, int h, int& x, int& y);

  GLuint tex_ = 0;
  int size_ = 0;
  struct Shelf {
    int y, h, x;
  };
  std::vector<Shelf> shelves_;
  int shelfY_ = 0;
  float whiteUV_ = 0;
  bool overflowed_ = false;
  uint32_t generation_ = 0;
  std::unordered_map<uint64_t, GlyphEntry> map_;
  std::vector<unsigned char> scratch_;
};

}  // namespace ll
```

## `src/render/Renderer2D.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - batched textured quads: glyphs from the atlas, solid rectangles, gradients and images.
// Coordinates are framebuffer pixels with the origin at the top-left corner.
#pragma once

#include <string_view>
#include <vector>

#include "render/GlCommon.h"
#include "render/GlyphAtlas.h"
#include "text/Shaper.h"

namespace ll {

class Renderer2D {
 public:
  bool init(std::string* err);
  void shutdown();
  GlyphAtlas& atlas() { return atlas_; }

  void begin(int width, int height);  // into the currently bound framebuffer
  void flush();
  void setTextGamma(float g) {
    if (g != gamma_) {
      flush();
      gamma_ = g;
    }
  }

  void rect(float x, float y, float w, float h, const Color& c);
  void gradientH(float x, float y, float w, float h, const Color& left, const Color& right);
  void gradientV(float x, float y, float w, float h, const Color& top, const Color& bottom);
  // `mono`: draw the picture as luminance x tint (keeps night themes free of blue light).
  void image(GLuint tex, float x, float y, float w, float h, const Color& tint, float u0 = 0, float v0 = 0,
             float u1 = 1, float v1 = 1, bool mono = false);
  void text(FontLibrary& lib, const ShapedRun& run, float x, float baseline, float size, const Color& c);
  // Shapes (cached) and draws UTF-8 text; returns the advance in pixels.
  float drawText(Shaper& shaper, std::string_view utf8, int style, float x, float baseline, float size,
                 const Color& c);
  static float textWidth(Shaper& shaper, std::string_view utf8, int style, float size);

 private:
  struct Vertex {
    float x, y, u, v;
    uint32_t rgba;
  };
  void quad(float x, float y, float w, float h, float u0, float v0, float u1, float v1, uint32_t c);
  void quad4(float x, float y, float w, float h, float u, float v, uint32_t c00, uint32_t c10, uint32_t c11,
             uint32_t c01);
  void ensureIndices(size_t quads);

  GlyphAtlas atlas_;
  GLuint prog_ = 0, vao_ = 0, vbo_ = 0, ibo_ = 0;
  GLint uProj_ = -1, uTex_ = -1, uMode_ = -1, uGamma_ = -1;
  size_t iboQuads_ = 0;
  std::vector<Vertex> verts_;
  int width_ = 0, height_ = 0;
  float gamma_ = 1.0f;
};

}  // namespace ll
```

## `src/render/PageTurn.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - 3D page turning. The turning sheet is a grid mesh wrapped around a moving cylinder and drawn
// with a perspective camera, lighting, a printed back side and a cast shadow.
//
// Single page: the whole page peels off to the left, revealing the next page underneath.
// Two-page spread: like a real book, the right page flips over the spine; its back side carries the
// next left page and it lands flat on top of the current left page.
#pragma once

#include <string>

#include "render/GlCommon.h"

namespace ll {

class PageTurn {
 public:
  bool init(std::string* err);
  void shutdown();

  struct Params {
    GLuint sheetTex = 0;  // "from" view (render target texture, bottom-up)
    GLuint underTex = 0;  // "to" view
    int width = 0;        // viewport in pixels
    int height = 0;
    float t = 0;          // 0 = flat (not turned), 1 = turned completely
    float spineX = 0;     // 0: single page; otherwise the x of the spine of a two-page spread
    Color paper;          // page colour (back side of a single page)
    float backPrint = 0.14f;  // single page: how much print shows through the paper on the back side
    bool shadows = true;
  };
  // Draws into the currently bound framebuffer (needs a depth buffer).
  void draw(const Params& p);

 private:
  GLuint sheetProg_ = 0, underProg_ = 0;
  GLuint meshVao_ = 0, meshVbo_ = 0, meshIbo_ = 0;
  GLuint quadVao_ = 0, quadVbo_ = 0;
  int indexCount_ = 0;
  struct {
    GLint mvp, size, sheetX0, axisPoint, axisNormal, radius, front, back, paper, backPrint, shadows, spine, spread;
  } us_{};
  struct {
    GLint proj, size, axisPoint, axisNormal, radius, texA, texB, spine, shadows;
  } uu_{};
};

}  // namespace ll
```

## `src/platform/Platform.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - the few things that differ between Windows, Android and other systems.
#pragma once

#include <string>
#include <vector>

namespace ll::platform {

// Phones and tablets: no hover, a back button, gestures and finger-sized controls.
bool isTouchFirst();

std::string assetsDir();  // with trailing separator ("" on Android: SDL reads APK assets by relative path)
std::string prefDir();    // writable per-user folder, with trailing separator
std::vector<std::string> defaultSearchRoots();  // Downloads, Documents, Desktop ... (Android: Download, Books ...)
std::vector<std::string> driveRoots();          // all local drives / storage volumes

struct SystemFont {
  std::string family;
  std::string files[4];  // regular, italic, bold, bold italic (full paths; empty = missing)
  int faceIndex[4] = {0, 0, 0, 0};
};
std::vector<SystemFont> readingFonts();        // well-known reading typefaces installed on this machine
std::vector<std::string> fallbackFontFiles();  // broad-coverage fonts for characters missing in the book font

// Android: reading books anywhere on the shared storage needs "All files access" (Android 11+) or the
// storage permission (older versions). Desktop: always true / no-op.
bool hasStorageAccess();
void requestStorageAccess();

// Android: the screen brightness of the reader's own window (no permission needed; other apps keep theirs).
// Values are linear, 0 (darkest) .. 1; a negative value follows the system setting again. Desktop: no-op.
bool canSetScreenBrightness();
float systemScreenBrightness();  // the system's current brightness, 0..1 (where a swipe starts from)
void setScreenBrightness(float linear);

// True for files whose content is not available locally (OneDrive "online-only" placeholders).
bool isCloudPlaceholder(const std::string& path);
// Opens the system file manager with `path` selected (not available on Android).
bool canRevealFiles();
void revealInFileManager(const std::string& path);
// Loads a whole file from the assets directory (works with Android APK assets too).
bool loadAsset(const std::string& relativePath, std::vector<unsigned char>& out);

// "Windows x64", "Android (API 34) arm64" ... for the About panel.
std::string systemDescription();

}  // namespace ll::platform
```

## `src/platform/Platform.cpp`

ASCII, LF line endings, ends with a newline.

```cpp
#include "platform/Platform.h"

#include <SDL3/SDL.h>

#include <filesystem>

#include "core/BookLoader.h"
#include "core/FileUtil.h"

#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#ifndef FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
#define FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS 0x00400000
#endif
#ifndef FILE_ATTRIBUTE_RECALL_ON_OPEN
#define FILE_ATTRIBUTE_RECALL_ON_OPEN 0x00040000
#endif
#endif

#ifdef __ANDROID__
#include <jni.h>
#endif

namespace ll::platform {

#ifdef __ANDROID__
namespace {

// Static helpers of app.lanternleaf.reader.LanternleafActivity (see android/), called through JNI.
struct ActivityClass {
  JNIEnv* env = nullptr;
  jobject activity = nullptr;
  jclass cls = nullptr;
  ActivityClass() {
    env = static_cast<JNIEnv*>(SDL_GetAndroidJNIEnv());
    if (!env) return;
    activity = static_cast<jobject>(SDL_GetAndroidActivity());
    if (activity) cls = env->GetObjectClass(activity);
  }
  ~ActivityClass() {
    if (!env) return;
    if (cls) env->DeleteLocalRef(cls);
    if (activity) env->DeleteLocalRef(activity);
  }
  jmethodID method(const char* name, const char* signature) {
    if (!cls) return nullptr;
    jmethodID m = env->GetStaticMethodID(cls, name, signature);
    if (!m) clear();
    return m;
  }
  void clear() {
    if (env->ExceptionCheck()) {
      env->ExceptionDescribe();
      env->ExceptionClear();
    }
  }
};

bool callStaticBool(const char* name) {
  ActivityClass a;
  jmethodID m = a.method(name, "()Z");
  if (!m) return false;
  const bool r = a.env->CallStaticBooleanMethod(a.cls, m) != JNI_FALSE;
  a.clear();
  return r;
}

void callStaticVoid(const char* name) {
  ActivityClass a;
  jmethodID m = a.method(name, "()V");
  if (!m) return;
  a.env->CallStaticVoidMethod(a.cls, m);
  a.clear();
}

float callStaticFloat(const char* name, float fallback) {
  ActivityClass a;
  jmethodID m = a.method(name, "()F");
  if (!m) return fallback;
  const float r = a.env->CallStaticFloatMethod(a.cls, m);
  if (a.env->ExceptionCheck()) {
    a.clear();
    return fallback;
  }
  return r;
}

void callStaticVoidFloat(const char* name, float value) {
  ActivityClass a;
  jmethodID m = a.method(name, "(F)V");
  if (!m) return;
  a.env->CallStaticVoidMethod(a.cls, m, static_cast<jfloat>(value));
  a.clear();
}

std::string callStaticString(const char* name) {
  ActivityClass a;
  jmethodID m = a.method(name, "()Ljava/lang/String;");
  if (!m) return {};
  auto* s = static_cast<jstring>(a.env->CallStaticObjectMethod(a.cls, m));
  a.clear();
  if (!s) return {};
  const char* chars = a.env->GetStringUTFChars(s, nullptr);
  std::string out = chars ? chars : "";
  if (chars) a.env->ReleaseStringUTFChars(s, chars);
  a.env->DeleteLocalRef(s);
  return out;
}

std::vector<std::string> storageVolumes() {
  std::vector<std::string> out;
  const std::string all = callStaticString("storageRoots");
  size_t i = 0;
  while (i < all.size()) {
    size_t e = all.find('\n', i);
    if (e == std::string::npos) e = all.size();
    if (e > i) out.push_back(all.substr(i, e - i));
    i = e + 1;
  }
  if (out.empty()) out.push_back("/storage/emulated/0");
  return out;
}

}  // namespace
#endif

bool isTouchFirst() {
#if defined(__ANDROID__) || (defined(__APPLE__) && defined(TARGET_OS_IPHONE) && TARGET_OS_IPHONE)
  return true;
#else
  return false;
#endif
}

std::string assetsDir() {
#ifdef __ANDROID__
  return {};
#else
  const char* base = SDL_GetBasePath();
  return std::string(base ? base : "") + "assets/";
#endif
}

std::string prefDir() {
  char* p = SDL_GetPrefPath("", "Lanternleaf");
  std::string s = p ? p : "";
  SDL_free(p);
  return s;
}

std::vector<std::string> defaultSearchRoots() {
  std::vector<std::string> roots;
#ifdef __ANDROID__
  const std::string primary = storageVolumes().front();
  for (const char* sub : {"Download", "Documents", "Books", "Telegram",
                          "Android/media/org.telegram.messenger/Telegram/Telegram Documents"}) {
    const std::string p = primary + "/" + sub;
    if (isDirectory(p)) roots.push_back(p);
  }
  if (roots.empty()) roots.push_back(primary + "/Download");
#else
  for (SDL_Folder f : {SDL_FOLDER_DOWNLOADS, SDL_FOLDER_DOCUMENTS, SDL_FOLDER_DESKTOP}) {
    const char* p = SDL_GetUserFolder(f);
    if (!p || !*p) continue;
    std::string s = p;
    while (s.size() > 3 && (s.back() == '\\' || s.back() == '/')) s.pop_back();
    if (isDirectory(s)) roots.push_back(s);
  }
#endif
  return roots;
}

std::vector<std::string> driveRoots() {
  std::vector<std::string> roots;
#ifdef _WIN32
  const DWORD mask = GetLogicalDrives();
  for (int i = 0; i < 26; ++i) {
    if (!(mask & (1u << i))) continue;
    wchar_t root[4] = {static_cast<wchar_t>(L'A' + i), L':', L'\\', 0};
    const UINT type = GetDriveTypeW(root);
    if (type == DRIVE_FIXED || type == DRIVE_REMOVABLE || type == DRIVE_RAMDISK) {
      roots.push_back(std::string(1, static_cast<char>('A' + i)) + ":\\");
    }
  }
#elif defined(__ANDROID__)
  roots = storageVolumes();
#else
  roots.push_back("/");
#endif
  return roots;
}

std::vector<SystemFont> readingFonts() {
  std::vector<SystemFont> out;
#ifdef _WIN32
  wchar_t winDir[MAX_PATH] = {};
  GetWindowsDirectoryW(winDir, MAX_PATH);
  const std::string fonts = pathToUtf8(std::filesystem::path(winDir) / L"Fonts") + "\\";
  struct Def {
    const char* family;
    const char* files[4];
  };
  static const Def kDefs[] = {
      {"Georgia", {"georgia.ttf", "georgiai.ttf", "georgiab.ttf", "georgiaz.ttf"}},
      {"Palatino Linotype", {"pala.ttf", "palai.ttf", "palab.ttf", "palabi.ttf"}},
      {"Cambria", {"cambria.ttc", "cambriai.ttf", "cambriab.ttf", "cambriaz.ttf"}},
      {"Constantia", {"constan.ttf", "constani.ttf", "constanb.ttf", "constanz.ttf"}},
      {"Times New Roman", {"times.ttf", "timesi.ttf", "timesbd.ttf", "timesbi.ttf"}},
      {"Segoe UI", {"segoeui.ttf", "segoeuii.ttf", "segoeuib.ttf", "segoeuiz.ttf"}},
      {"Calibri", {"calibri.ttf", "calibrii.ttf", "calibrib.ttf", "calibriz.ttf"}},
      {"Verdana", {"verdana.ttf", "verdanai.ttf", "verdanab.ttf", "verdanaz.ttf"}},
  };
#elif defined(__ANDROID__)
  const std::string fonts = "/system/fonts/";
  struct Def {
    const char* family;
    const char* files[4];
  };
  static const Def kDefs[] = {
      {"Noto Serif", {"NotoSerif-Regular.ttf", "NotoSerif-Italic.ttf", "NotoSerif-Bold.ttf", "NotoSerif-BoldItalic.ttf"}},
  };
#endif
#if defined(_WIN32) || defined(__ANDROID__)
  for (const Def& d : kDefs) {
    SystemFont f;
    f.family = d.family;
    for (int s = 0; s < 4; ++s) {
      const std::string p = fonts + d.files[s];
      if (fileExists(p)) f.files[s] = p;
    }
    if (!f.files[0].empty()) out.push_back(std::move(f));
  }
#endif
  return out;
}

std::vector<std::string> fallbackFontFiles() {
  std::vector<std::string> out;
#ifdef _WIN32
  wchar_t winDir[MAX_PATH] = {};
  GetWindowsDirectoryW(winDir, MAX_PATH);
  const std::string fonts = pathToUtf8(std::filesystem::path(winDir) / L"Fonts") + "\\";
  for (const char* f : {"segoeui.ttf", "seguisym.ttf", "arial.ttf"}) {
    if (fileExists(fonts + f)) out.push_back(fonts + f);
  }
#elif defined(__ANDROID__)
  for (const char* f : {"/system/fonts/Roboto-Regular.ttf", "/system/fonts/NotoSansSymbols-Regular-Subsetted.ttf",
                        "/system/fonts/NotoSansSymbols-Regular-Subsetted2.ttf"}) {
    if (fileExists(f)) out.push_back(f);
  }
#else
  for (const char* f : {"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}) {
    if (fileExists(f)) out.push_back(f);
  }
#endif
  return out;
}

bool hasStorageAccess() {
#ifdef __ANDROID__
  return callStaticBool("hasAllFilesAccess");
#else
  return true;
#endif
}

void requestStorageAccess() {
#ifdef __ANDROID__
  callStaticVoid("requestAllFilesAccess");
#endif
}

bool canSetScreenBrightness() {
#ifdef __ANDROID__
  return true;
#else
  return false;
#endif
}

float systemScreenBrightness() {
#ifdef __ANDROID__
  return callStaticFloat("systemScreenBrightness", 0.5f);
#else
  return 1.0f;
#endif
}

void setScreenBrightness(float linear) {
#ifdef __ANDROID__
  callStaticVoidFloat("setScreenBrightness", linear);
#else
  (void)linear;
#endif
}

bool isCloudPlaceholder(const std::string& path) {
#ifdef _WIN32
  const DWORD a = GetFileAttributesW(pathFromUtf8(path).c_str());
  if (a == INVALID_FILE_ATTRIBUTES) return false;
  return (a & (FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN)) != 0;
#else
  (void)path;
  return false;
#endif
}

bool canRevealFiles() {
#ifdef __ANDROID__
  return false;
#else
  return true;
#endif
}

void revealInFileManager(const std::string& path) {
#ifdef _WIN32
  const std::wstring args = L"/select,\"" + pathFromUtf8(path).wstring() + L"\"";
  ShellExecuteW(nullptr, L"open", L"explorer.exe", args.c_str(), nullptr, SW_SHOWNORMAL);
#elif defined(__ANDROID__)
  (void)path;
#else
  const std::string dir = pathToUtf8(pathFromUtf8(path).parent_path());
  SDL_OpenURL(("file://" + dir).c_str());
#endif
}

bool loadAsset(const std::string& relativePath, std::vector<unsigned char>& out) {
  size_t size = 0;
  void* data = SDL_LoadFile((assetsDir() + relativePath).c_str(), &size);
  if (!data) return false;
  const unsigned char* p = static_cast<const unsigned char*>(data);
  out.assign(p, p + size);
  SDL_free(data);
  return true;
}

std::string systemDescription() {
#if defined(__ANDROID__)
  std::string s = "Android (API " + std::to_string(SDL_GetAndroidSDKVersion()) + ")";
#else
  std::string s = SDL_GetPlatform();
#endif
#if defined(__aarch64__) || defined(_M_ARM64)
  s += " arm64";
#elif defined(__x86_64__) || defined(_M_X64)
  s += " x64";
#elif defined(__arm__) || defined(_M_ARM)
  s += " arm";
#elif defined(__i386__) || defined(_M_IX86)
  s += " x86";
#endif
  return s;
}

}  // namespace ll::platform
```

## `src/app/Themes.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - colour schemes for day and night reading.
#pragma once

#include <string>
#include <string_view>
#include <vector>

#include "render/GlCommon.h"

namespace ll {

struct Theme {
  const char* id;
  const char* name;
  const char* note;     // one-line rationale shown in the settings
  Color background;
  Color text;
  Color secondary;      // footer, page numbers
  Color accent;         // links, footnote markers, highlights
  float gamma;          // glyph coverage exponent (<1 darkens dark-on-light text, >1 thins light-on-dark)
  bool dark;
};

const std::vector<Theme>& themes();
int themeIndex(std::string_view id);  // falls back to 0

// Applies the brightness setting: light themes dim the paper, dark themes dim the ink.
Theme adjustedTheme(const Theme& t, float brightness);

}  // namespace ll
```

## `src/app/Themes.cpp`

ASCII, LF line endings, ends with a newline.

```cpp
#include "app/Themes.h"

#include <algorithm>

namespace ll {

const std::vector<Theme>& themes() {
  static const std::vector<Theme> kThemes = {
      {"day", "Day", "Black on white: best legibility in daylight (positive polarity).", Color::hex(0xFFFFFF),
       Color::hex(0x101010), Color::hex(0x707070), Color::hex(0x1F5FBF), 0.86f, false},
      {"sepia", "Sepia", "Dark brown on warm paper: less glare and less blue than pure white.",
       Color::hex(0xF4ECD8), Color::hex(0x3B2E22), Color::hex(0x8A7860), Color::hex(0x8A4B12), 0.88f, false},
      {"dusk", "Dusk", "Warm beige on dark brown: evening reading with very little blue light.",
       Color::hex(0x1B1611), Color::hex(0xD9C29C), Color::hex(0x8C7A5E), Color::hex(0xE3A35F), 1.0f, true},
      {"night-amber", "Night amber", "Amber on black (~600 nm): minimal melatonin suppression before sleep.",
       Color::hex(0x000000), Color::hex(0xFFA826), Color::hex(0x8A5A10), Color::hex(0xFFD07A), 1.08f, true},
      {"night-red", "Night red", "Deep red on black (>610 nm): preserves dark adaptation, lowest circadian impact.",
       Color::hex(0x000000), Color::hex(0xE0200E), Color::hex(0x751005), Color::hex(0xFF5533), 1.1f, true},
  };
  return kThemes;
}

int themeIndex(std::string_view id) {
  const auto& t = themes();
  for (size_t i = 0; i < t.size(); ++i) {
    if (id == t[i].id) return static_cast<int>(i);
  }
  return 0;
}

Theme adjustedTheme(const Theme& t, float brightness) {
  Theme out = t;
  const float b = std::clamp(brightness, 0.2f, 1.0f);
  if (t.dark) {
    out.text = t.text.scaled(b);
    out.secondary = t.secondary.scaled(b);
    out.accent = t.accent.scaled(b);
  } else {
    const float k = 0.45f + 0.55f * b;  // never darker than a mid grey paper
    out.background = t.background.scaled(k);
  }
  return out;
}

}  // namespace ll
```

## `src/app/Settings.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - persistent settings and reading positions (JSON in the per-user preferences folder).
#pragma once

#include <climits>
#include <cstdint>
#include <string>
#include <vector>

namespace ll {

struct RecentBook {
  std::string path;
  std::string fingerprint;  // survives renames/moves
  std::string title;
  std::string authors;
  int block = 0;            // reading position: block index + byte offset inside it
  uint32_t offset = 0;
  int blockCount = 0;       // sanity check when the parser changes
  double percent = 0;
  int64_t lastOpened = 0;   // unix seconds
};

struct Settings {
  // window
  int winX = INT_MIN, winY = INT_MIN, winW = 1180, winH = 820;
  bool maximized = false;
#ifdef __ANDROID__
  bool fullscreen = true;       // immersive: no status/navigation bars while reading
#else
  bool fullscreen = false;
#endif
  bool keepScreenOn = true;     // while a book is open
  // Android: this app's own screen brightness as a level 0.01..1 (swipe on the left part of the page);
  // -1 = as the system sets it.
  float screenBrightness = -1.0f;

  // reading
  std::string fontFamily = "PT Serif";
#ifdef __ANDROID__
  float fontSize = 19.0f;       // dp on phones (multiplied by the display density)
#else
  float fontSize = 21.0f;       // logical pixels (multiplied by the display scale)
#endif
  float lineSpacing = 1.4f;
  float margin = 0.06f;         // horizontal margin as a fraction of the window width
  float paragraphIndent = 1.5f; // em
  float paragraphSpacing = 0.0f;
  bool justify = true;
  bool hyphenate = true;
  // First start: Day theme, one page, instant page turns.
  std::string columns = "1";    // auto | 1 | 2
  float maxLineWidth = 40.0f;   // em, single-column mode
  std::string theme = "day";
  float brightness = 1.0f;
  std::string pageTurn = "none";  // curl | slide | fade | none (instant)
  float turnSeconds = 0.5f;
  bool autoNight = false;
  int nightFrom = 21, nightTo = 7;
  std::string dayTheme = "day";
  std::string nightTheme = "night-amber";

  // library search
  std::vector<std::string> searchRoots;
  bool searchByName = true;
  bool searchByMeta = true;
  bool searchByContent = false;
  bool skipSystemDirs = true;
  bool ignoreTinyTxt = true;
  std::string lastQuery;

  // session
  std::string lastBook;
  std::vector<RecentBook> recent;
  bool storagePromptDismissed = false;  // Android: "Don't ask again" for the file access prompt

  bool load(const std::string& file);
  bool save(const std::string& file) const;

  RecentBook* findRecent(const std::string& path, const std::string& fingerprint);
  RecentBook& touchRecent(const std::string& path, const std::string& fingerprint);  // moves to front
  void removeRecent(const std::string& path);
};

}  // namespace ll
```

## `src/app/Settings.cpp`

ASCII, LF line endings, ends with a newline.

```cpp
#include "app/Settings.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <ctime>

#include "core/BookLoader.h"
#include "core/FileUtil.h"

namespace ll {

namespace {
template <typename T>
void get(const nlohmann::json& j, const char* key, T& out) {
  auto it = j.find(key);
  if (it == j.end() || it->is_null()) return;
  try {
    out = it->get<T>();
  } catch (...) {
    // keep the default on type mismatch
  }
}
}  // namespace

bool Settings::load(const std::string& file) {
  std::string data;
  if (!readFile(file, data)) return false;
  const nlohmann::json j = nlohmann::json::parse(data, nullptr, false);
  if (j.is_discarded() || !j.is_object()) return false;
  if (auto w = j.find("window"); w != j.end() && w->is_object()) {
    get(*w, "x", winX);
    get(*w, "y", winY);
    get(*w, "w", winW);
    get(*w, "h", winH);
    get(*w, "maximized", maximized);
    get(*w, "fullscreen", fullscreen);
    get(*w, "keepScreenOn", keepScreenOn);
    get(*w, "screenBrightness", screenBrightness);
  }
  if (auto r = j.find("reader"); r != j.end() && r->is_object()) {
    get(*r, "fontFamily", fontFamily);
    get(*r, "fontSize", fontSize);
    get(*r, "lineSpacing", lineSpacing);
    get(*r, "margin", margin);
    get(*r, "paragraphIndent", paragraphIndent);
    get(*r, "paragraphSpacing", paragraphSpacing);
    get(*r, "justify", justify);
    get(*r, "hyphenate", hyphenate);
    get(*r, "columns", columns);
    get(*r, "maxLineWidth", maxLineWidth);
    get(*r, "theme", theme);
    get(*r, "brightness", brightness);
    get(*r, "pageTurn", pageTurn);
    get(*r, "turnSeconds", turnSeconds);
    get(*r, "autoNight", autoNight);
    get(*r, "nightFrom", nightFrom);
    get(*r, "nightTo", nightTo);
    get(*r, "dayTheme", dayTheme);
    get(*r, "nightTheme", nightTheme);
  }
  if (auto s = j.find("search"); s != j.end() && s->is_object()) {
    get(*s, "roots", searchRoots);
    get(*s, "byName", searchByName);
    get(*s, "byMeta", searchByMeta);
    get(*s, "byContent", searchByContent);
    get(*s, "skipSystemDirs", skipSystemDirs);
    get(*s, "ignoreTinyTxt", ignoreTinyTxt);
    get(*s, "lastQuery", lastQuery);
  }
  get(j, "lastBook", lastBook);
  recent.clear();
  if (auto rs = j.find("recent"); rs != j.end() && rs->is_array()) {
    for (const auto& e : *rs) {
      if (!e.is_object()) continue;
      RecentBook b;
      get(e, "path", b.path);
      get(e, "fingerprint", b.fingerprint);
      get(e, "title", b.title);
      get(e, "authors", b.authors);
      get(e, "block", b.block);
      get(e, "offset", b.offset);
      get(e, "blockCount", b.blockCount);
      get(e, "percent", b.percent);
      get(e, "lastOpened", b.lastOpened);
      if (!b.path.empty()) recent.push_back(std::move(b));
    }
  }
  get(j, "storagePromptDismissed", storagePromptDismissed);
  fontSize = std::clamp(fontSize, 8.0f, 120.0f);
  lineSpacing = std::clamp(lineSpacing, 1.0f, 2.5f);
  margin = std::clamp(margin, 0.0f, 0.3f);
  brightness = std::clamp(brightness, 0.2f, 1.0f);
  turnSeconds = std::clamp(turnSeconds, 0.1f, 2.0f);
  maxLineWidth = std::clamp(maxLineWidth, 20.0f, 200.0f);
  screenBrightness = screenBrightness < 0 ? -1.0f : std::clamp(screenBrightness, 0.01f, 1.0f);
  return true;
}

bool Settings::save(const std::string& file) const {
  nlohmann::json j;
  j["version"] = 1;
  j["window"] = {{"x", winX}, {"y", winY}, {"w", winW}, {"h", winH}, {"maximized", maximized},
                 {"fullscreen", fullscreen}, {"keepScreenOn", keepScreenOn}, {"screenBrightness", screenBrightness}};
  j["reader"] = {{"fontFamily", fontFamily},
                 {"fontSize", fontSize},
                 {"lineSpacing", lineSpacing},
                 {"margin", margin},
                 {"paragraphIndent", paragraphIndent},
                 {"paragraphSpacing", paragraphSpacing},
                 {"justify", justify},
                 {"hyphenate", hyphenate},
                 {"columns", columns},
                 {"maxLineWidth", maxLineWidth},
                 {"theme", theme},
                 {"brightness", brightness},
                 {"pageTurn", pageTurn},
                 {"turnSeconds", turnSeconds},
                 {"autoNight", autoNight},
                 {"nightFrom", nightFrom},
                 {"nightTo", nightTo},
                 {"dayTheme", dayTheme},
                 {"nightTheme", nightTheme}};
  j["search"] = {{"roots", searchRoots},       {"byName", searchByName},
                 {"byMeta", searchByMeta},     {"byContent", searchByContent},
                 {"skipSystemDirs", skipSystemDirs}, {"ignoreTinyTxt", ignoreTinyTxt},
                 {"lastQuery", lastQuery}};
  j["lastBook"] = lastBook;
  nlohmann::json rs = nlohmann::json::array();
  for (const RecentBook& b : recent) {
    rs.push_back({{"path", b.path},
                  {"fingerprint", b.fingerprint},
                  {"title", b.title},
                  {"authors", b.authors},
                  {"block", b.block},
                  {"offset", b.offset},
                  {"blockCount", b.blockCount},
                  {"percent", b.percent},
                  {"lastOpened", b.lastOpened}});
  }
  j["recent"] = std::move(rs);
  j["storagePromptDismissed"] = storagePromptDismissed;
  return writeFileAtomic(file, j.dump(2, ' ', false, nlohmann::json::error_handler_t::replace));
}

RecentBook* Settings::findRecent(const std::string& path, const std::string& fingerprint) {
  for (RecentBook& b : recent) {
    if (b.path == path) return &b;
  }
  if (!fingerprint.empty()) {
    for (RecentBook& b : recent) {
      if (b.fingerprint == fingerprint) return &b;
    }
  }
  return nullptr;
}

RecentBook& Settings::touchRecent(const std::string& path, const std::string& fingerprint) {
  RecentBook entry;
  if (RecentBook* existing = findRecent(path, fingerprint)) {
    entry = *existing;
    const std::string oldPath = existing->path;
    recent.erase(std::remove_if(recent.begin(), recent.end(), [&](const RecentBook& b) { return b.path == oldPath; }),
                 recent.end());
  }
  entry.path = path;
  if (!fingerprint.empty()) entry.fingerprint = fingerprint;
  entry.lastOpened = static_cast<int64_t>(std::time(nullptr));
  recent.insert(recent.begin(), std::move(entry));
  if (recent.size() > 200) recent.resize(200);
  return recent.front();
}

void Settings::removeRecent(const std::string& path) {
  recent.erase(std::remove_if(recent.begin(), recent.end(), [&](const RecentBook& b) { return b.path == path; }),
               recent.end());
}

}  // namespace ll
```

## `src/app/UiHelpers.h`

ASCII, LF line endings, ends with a newline.

```cpp
// Lanternleaf - small Dear ImGui helpers for touch screens.
#pragma once

#include <imgui.h>
#include <imgui_internal.h>

#include <cmath>

namespace ll::ui {

inline bool touchInput() { return ImGui::GetIO().MouseSource == ImGuiMouseSource_TouchScreen; }

// A slider touched by a finger (see slider()): which one, and its value before the touch.
struct TouchSlider {
  ImGuiID id = 0;
  float saved = 0;    // the value before the finger came down
  float pending = 0;  // where the finger would put it (applied if it turns out to be a tap)
  bool sliding = false;
};
inline TouchSlider& touchSlider() {
  static TouchSlider t;
  return t;
}

// Dear ImGui has no finger scrolling: drag the current scrollable window (or table) with a finger. A finger that
// started on a button, check box or drop-down and then moves up or down is scrolling, so that control lets go
// (it would otherwise be clicked when the finger lifts, still over it as the list moves along).
// A list that is already at its top or bottom passes the rest of the movement on to the panel around it, so a
// list inside a scrolling panel never traps the finger. `children`: also when the finger is over a child window
// (a list); a panel that has lists of its own passes false, the lists scroll it themselves.
inline void touchScroll(float scale, bool children = true) {
  const ImGuiIO& io = ImGui::GetIO();
  if (io.MouseSource != ImGuiMouseSource_TouchScreen || !ImGui::IsMouseDown(ImGuiMouseButton_Left)) return;
  const ImGuiHoveredFlags hover =
      ImGuiHoveredFlags_AllowWhenBlockedByActiveItem | (children ? ImGuiHoveredFlags_ChildWindows : 0);
  if (!ImGui::IsWindowHovered(hover)) return;
  if (!ImGui::IsMouseDragging(ImGuiMouseButton_Left, 8.0f * scale)) return;
  const ImGuiID active = ImGui::GetActiveID();
  if (active != 0 && active == touchSlider().id && touchSlider().sliding) return;  // moving a slider, not the list
  if (active != 0 && active != touchSlider().id && !ImGui::GetInputTextState(active)) {
    const ImVec2 d = ImGui::GetMouseDragDelta(ImGuiMouseButton_Left, 0.0f);
    if (std::fabs(d.y) > std::fabs(d.x)) ImGui::ClearActiveID();
  }
  float dy = -io.MouseDelta.y;
  for (ImGuiWindow* w = ImGui::GetCurrentWindow(); w && dy != 0.0f; w = w->ParentWindow) {
    const float from = w->Scroll.y;
    const float to = std::fmin(std::fmax(from + dy, 0.0f), w->ScrollMax.y);
    if (to != from) ImGui::SetScrollY(w, to);
    dy -= to - from;
    if (!(w->Flags & ImGuiWindowFlags_ChildWindow)) break;  // the panel itself: nothing above it scrolls
  }
}

// The height for a list (table) under some controls in a panel. With room enough it fills the rest of the panel.
// In a short panel (a phone held sideways, a small window) the controls would squeeze it to nothing: there it
// takes most of the panel's height, and the panel scrolls to bring it into view.
inline float listHeight() {
  const float avail = ImGui::GetContentRegionAvail().y;
  const float row = ImGui::GetFrameHeightWithSpacing();
  if (avail >= row * 8.0f) return avail;
  const float view = ImGui::GetCurrentWindow()->InnerRect.GetHeight();
  return std::fmax(avail, std::fmax(row * 4.0f, view * 0.85f));
}

// Call right after a slider: on touch screens it follows a finger that moves sideways, while a finger that moves
// up or down scrolls the panel and leaves the value alone; a tap still sets it. `before` is the value before the
// slider was drawn; returns whether the value changed.
template <typename T>
bool touchSliderGuard(T before, T* v, bool changed, float scale) {
  if (!touchInput()) return changed;
  TouchSlider& t = touchSlider();
  const ImGuiID id = ImGui::GetItemID();
  if (ImGui::IsItemActivated()) {
    t.id = id;
    t.saved = static_cast<float>(before);
    t.sliding = false;
  }
  if (t.id != id || t.sliding) {
    if (t.id == id && !ImGui::IsItemActive()) t.id = 0;
    return changed;
  }
  if (ImGui::IsItemActive()) {
    const ImVec2 d = ImGui::GetMouseDragDelta(ImGuiMouseButton_Left, 0.0f);
    const float slop = 10.0f * scale;
    if (std::fabs(d.x) > slop && std::fabs(d.x) >= std::fabs(d.y)) {
      t.sliding = true;  // sideways: a real slide, the value is already where the finger is
      return *v != static_cast<T>(t.saved) || changed;
    }
    t.pending = static_cast<float>(*v);  // not decided yet: keep the old value for now
    *v = static_cast<T>(t.saved);
    if (std::fabs(d.y) > slop) {  // up or down: the finger scrolls the panel
      ImGui::ClearActiveID();
      t.id = 0;
    }
    return false;
  }
  // The finger lifted before moving: a tap, which sets the value where it touched.
  t.id = 0;
  if (static_cast<T>(t.pending) == *v) return false;
  *v = static_cast<T>(t.pending);
  return true;
}

inline bool slider(const char* label, float* v, float min, float max, const char* format, float scale) {
  const float before = *v;
  return touchSliderGuard(before, v, ImGui::SliderFloat(label, v, min, max, format), scale);
}

inline bool slider(const char* label, int* v, int min, int max, const char* format, float scale) {
  const int before = *v;
  return touchSliderGuard(before, v, ImGui::SliderInt(label, v, min, max, format), scale);
}

// A click that is not the end of a finger drag (scrolling must not open whatever is under the finger).
inline bool tapped(bool clicked, float scale) {
  if (!clicked) return false;
  const ImGuiIO& io = ImGui::GetIO();
  if (io.MouseSource != ImGuiMouseSource_TouchScreen) return true;
  const float limit = 10.0f * scale;
  return io.MouseDragMaxDistanceSqr[ImGuiMouseButton_Left] < limit * limit;
}

}  // namespace ll::ui
```

## `src/app/App.h`

UTF-8 without BOM, LF line endings, ends with a newline.

```cpp
// Lanternleaf - the application: window, input, navigation, rendering and UI glue.
#pragma once

#include <SDL3/SDL.h>

#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "app/Settings.h"
#include "app/Themes.h"
#include "app/Version.h"  // generated from the VERSION file
#include "core/Document.h"
#include "core/Hyphenator.h"
#include "core/LibrarySearch.h"
#include "render/GlCommon.h"
#include "render/PageTurn.h"
#include "render/Renderer2D.h"
#include "text/BookLayout.h"
#include "text/FontLibrary.h"
#include "text/Shaper.h"

struct ImFont;

namespace ll {

constexpr const char* kAppName = "Lanternleaf";
constexpr const char* kAppVersion = LL_VERSION;

class App {
 public:
  App();
  ~App();
  bool init(int argc, char** argv);
  void shutdown();
  SDL_AppResult handleEvent(SDL_Event& e);
  SDL_AppResult iterate();

 private:
  struct View {
    Page pages[2];
    int count = 1;
  };
  struct FindHit {
    int block = 0;
    uint32_t offset = 0;
    uint32_t length = 0;
    std::string snippet;
    std::string chapter;
  };
  struct ShotOptions {
    bool enabled = false;
    std::string out;
    int width = 1280, height = 820;
    int frames = 4;
    double gotoPercent = -1;
    int nextPages = 0;
    float turnT = -1;
    std::string panel;
    std::string search;
    std::vector<std::string> searchRoots;
    bool searchContent = false;
    std::string find;
    std::vector<std::pair<float, float>> clicks;  // --click x,y: left clicks in window coordinates, in order
    size_t clickPhase = 0;                         // three per click: move there, press, release
    int lastClickFrame = -100;
    int frame = 0;
  };
  void pushShotClickPhase();

  // setup
  bool parseArgs(int argc, char** argv, std::string& openPath);
  bool createWindow();
  // Desktop: the window cannot be made smaller than 10 % of its monitor, in width and in height.
  void applyMinimumWindowSize();
  bool loadFonts();
  void loadHyphenation();
  void initImGui();
  bool applyFontFamily(const std::string& family);
  std::vector<std::string> availableFamilies() const;

  // book and navigation
  bool openBook(const std::string& path);
  void updateGeometry();
  void rebuildView();
  View makeView(LinePos start);
  void setViewStart(LinePos p, bool updateAnchor);
  void goNext();
  void goPrev();
  void goHome();
  void goEnd();
  void goToBlock(int block, uint32_t offset);
  void goToPercent(double pct);
  void startTurn(bool forward, LinePos target);
  void finishTurn();
  double percentAt(LinePos p) const;
  double currentPercent() const;
  double viewPercent(const View& v) const;  // reading progress at the end of a view (footer)
  // Pages on screen: "auto" (two when the window is wide), "1", or "2" (an open book).
  void setColumns(const std::string& mode);
  // Moves the open book to a stored position (falls back to the percentage if the book was parsed differently).
  void restorePosition(int block, uint32_t offset, int blockCount, double percent);
  std::string chapterTitleAt(int block) const;
  void followLink(int32_t link, float mouseX, float mouseY);
  void saveReadingPosition();
  void saveSettingsNow();
  void scheduleSave();
  void runFind();

  // rendering
  void renderFrame(GLuint fbo, int w, int h);
  void renderView(const View& v, int w, int h);
  // Instant page turning: the next and the previous view are rendered ahead, in idle time, into textures,
  // so a turn only shows a finished picture.
  uint64_t renderSignature() const;  // changes whenever a rendered view would look different
  void fillPageCache();
  void dropPageCache();
  void drawPage(const Page& pg, float x0, float y0);
  void drawWelcome(int w, int h);
  const gl::Texture* imageTexture(int index);
  bool takeScreenshot();

  // input
  void onKeyDown(const SDL_KeyboardEvent& k);
  void onMouseDown(const SDL_MouseButtonEvent& b);
  void onWheel(const SDL_MouseWheelEvent& w);
  void onFinger(const SDL_TouchFingerEvent& f);
  void handleTap(float px, float py, bool touch);  // framebuffer pixels
  bool pointOverUi(float winX, float winY) const;  // window coordinates
  bool closeTopPanel();                            // Esc / Android back
  // A click or tap outside every menu and panel: close them all and return to the page.
  bool readingModeBlocked() const;                 // something is open that such a click should close
  void returnToReading();
  void zoomBy(float factor);
  void setFontSize(float logicalPx);
  // Android: this app's screen brightness as a level 0.01..1 (applied as level², which feels even), or -1 to
  // follow the system again.
  void setScreenBrightness(float level);
  void toggleFullscreen();
  void applyScreenSaver();  // keep the screen on while reading (setting)
  void cycleTheme(int dir);
  void setTheme(const std::string& id);
  void checkAutoNight(bool force);

  // UI (AppUi.cpp)
  enum class Panel { None, Library, Toc, Settings, Goto, Help, About, Browser };
  // Opens a panel and brings it to the front; on phones every panel is a full-screen sheet, so the others close.
  void showPanel(Panel p, int libraryTab = -1);
  void togglePanel(Panel p);
  bool panelOpen(Panel p) const;
  void focusIfRequested(Panel p);  // call right before the panel's ImGui::Begin
  void drawUi();
  void drawToolbar();
  // The status bar at the bottom (chapter, progress bar, page, percentage). It shows and hides together with
  // the toolbar; while both show, the page is laid out between them (updateBars).
  void drawStatusBar();
  void updateBars();               // call inside an ImGui frame, before drawUi()
  float toolbarBarHeight() const;  // window units; inside an ImGui frame
  float statusBarBarHeight() const;
  bool statusBarTwoRows() const;   // narrow screens: the progress bar gets a row of its own
  bool countingPages() const { return doc_ && barsShown_; }  // page numbers only show on the status bar
  void drawLibrary();
  void drawLibraryRecent();
  void drawLibrarySearch();
  void drawLibraryFind();
  void drawToc();
  void drawSettings();
  void drawGoto();
  void drawHelp();
  void drawAbout();
  void drawFootnote();
  void drawMessages();
  void drawToast();
  void drawStoragePrompt();
  void showToast(const std::string& text, double seconds = 5.0);
  void applyImGuiStyle();
  void startLibrarySearch();
  void openFileDialog();
  void addFolderDialog();
  bool anyPanelOpen() const;
  bool storageAccess();  // cached platform::hasStorageAccess(), re-checked every second
  void onStorageAccessGranted();
  void drawStorageAccessNotice();
  bool narrowUi() const;  // inside a panel: it is narrow (phones), so lists show fewer columns
  // Positions the next panel window: every panel opens in the top left corner of the reading area and covers
  // half of it (the left half on a wide screen, the top half on a tall one). Returns extra ImGuiWindowFlags
  // for its Begin(): on touch screens panels stay put, so a finger scrolling one never drags it.
  int placePanel();

  // In-app file browser (FileBrowser.cpp): used on Android, where system pickers return content URIs.
  void openFileBrowser(bool folderMode);
  void drawFileBrowser();
  void browseTo(const std::string& dir);

  // frame pacing
  void requestRedraw(int frames = 3) { redrawFrames_ = std::max(redrawFrames_, frames); }
  void updateCallbackRate();
  void wake();
  void pollAsync();
  double now() const;
  const Theme& theme() const { return theme_; }
  void refreshTheme();
  void showError(const std::string& msg);

  // window / GL
  SDL_Window* window_ = nullptr;
  SDL_GLContext gl_ = nullptr;
  float displayScale_ = 1.0f;
  int fbW_ = 0, fbH_ = 0;
  int winW_ = 0, winH_ = 0;
  Uint32 wakeEvent_ = 0;
  std::string prefDir_;
  std::string settingsFile_;
  std::string imguiIni_;

  // text
  Settings settings_;
  Theme theme_{};
  FontLibrary fonts_;
  std::map<std::string, FontFamily> families_;
  std::unique_ptr<Shaper> bookShaper_;
  std::unique_ptr<Shaper> uiShaper_;
  std::vector<int> fallbackFaces_;
  int fontGeneration_ = 0;
  HyphenationService hyph_;
  std::unique_ptr<BookLayout> layout_;
  std::unique_ptr<Document> doc_;
  std::string bookPath_;
  std::string bookFingerprint_;

  // rendering
  Renderer2D r2d_;
  PageTurn turn_;
  gl::RenderTarget rtA_, rtB_, rtShot_;
  // Instant turns: pre-rendered next / previous views (see fillPageCache).
  struct CachedView {
    gl::RenderTarget rt;
    LinePos start;
    uint64_t signature = 0;
    bool valid = false;
  } cacheNext_, cachePrev_;
  GLuint presentTex_ = 0;       // a cached view to show this frame instead of drawing the page
  int instantCached_ = 0, instantDrawn_ = 0;  // diagnostics: instant turns served from the cache / drawn
  int layoutGeneration_ = 0;    // bumped when the layout parameters change (part of renderSignature)
  std::unordered_map<int, gl::Texture> images_;
  std::vector<unsigned char> uiFontData_;
  ImFont* uiFont_ = nullptr;
  int maxTextureSize_ = 2048;

  // geometry (framebuffer pixels)
  float fontPx_ = 20;
  float marginTop_ = 0, marginBottom_ = 0;
  bool barsShown_ = false;                  // toolbar and status bar on screen (with a book open)
  float topBarH_ = 0, bottomBarH_ = 0;      // their heights in window units, while shown
  float columnW_ = 0, columnX_[2] = {0, 0};
  int columns_ = 1;
  bool twoPagesFit_ = true;  // "2" asked for, but the window is too narrow for two readable pages

  // reading state
  int anchorBlock_ = 0;
  uint32_t anchorOffset_ = 0;
  LinePos viewStart_;
  View view_;
  bool viewValid_ = false;
  struct Highlight {
    int block = -1;
    uint32_t start = 0, end = 0;
  } highlight_;

  // page turn animation
  enum class TurnStyle { Curl, Slide, Fade };
  bool turning_ = false;
  bool turnForward_ = true;
  double turnStart_ = 0;
  float turnT_ = 0;
  TurnStyle turnStyle_ = TurnStyle::Curl;
  LinePos turnTarget_;

  // UI state
  bool showToolbar_ = false;
  double toolbarSeen_ = 0;
  bool showLibrary_ = false, showToc_ = false, showSettings_ = false, showHelp_ = false, showGoto_ = false;
  bool showAbout_ = false;
  Panel focusPanel_ = Panel::None;  // brought to the front on its next draw
  std::string noticesText_;         // About > licences, loaded on first use
  int libraryTab_ = 0;  // 0 recent, 1 search, 2 find in book
  bool focusQuery_ = false;
  bool showFootnote_ = false;
  std::string footnoteTitle_, footnoteText_;
  int footnoteBlock_ = -1;
  float footnoteX_ = 0, footnoteY_ = 0;
  std::vector<std::string> messages_;
  float gotoPercent_ = 0;
  int gotoPage_ = 1;
  // Status bar: the page number or the percentage being typed in.
  enum class StatusEdit { None, Page, Percent };
  StatusEdit statusEdit_ = StatusEdit::None;
  bool statusEditFocus_ = false;
  std::string statusText_;

  // library search
  MetaCache metaCache_;
  std::string metaCacheFile_;
  std::unique_ptr<LibrarySearch> search_;
  std::vector<SearchHit> hits_;
  std::string query_;
  bool searchStarted_ = false;
  int hitsSortColumn_ = -1;
  bool hitsSortAsc_ = true;

  // find in book
  std::string findQuery_;
  std::vector<FindHit> findHits_;
  bool findTruncated_ = false;

  // async results from dialogs / threads
  std::mutex asyncMutex_;
  std::vector<std::string> pendingOpen_;
  std::vector<std::string> pendingFolders_;

  // frame pacing / persistence
  int redrawFrames_ = 3;
  std::string rateHint_;
  bool saveDirty_ = false;
  double lastSave_ = 0;
  SDL_TimerID saveTimer_ = 0;
  SDL_TimerID minuteTimer_ = 0;
  float wheelAccum_ = 0;
  float zoomAccum_ = 0;
  uint64_t startCounter_ = 0;
  bool quitting_ = false;

  ShotOptions shot_;
  std::vector<std::pair<std::string, std::string>> overrides_;  // command line settings overrides
  bool turnFrozen_ = false;    // screenshot mode: keep the curl at a fixed t
  bool shotAllowSave_ = false; // screenshot mode normally never writes settings
  bool shotFindGo_ = false;    // screenshot mode: jump to the first --find match
  double countWork_ = 0;       // time spent in background pagination (diagnostics)
  bool searchWasRunning_ = false;
  bool toolbarPinned_ = false;
  int autoNightState_ = -1;
  std::map<SDL_FingerID, std::pair<float, float>> fingers_;
  float pinchDist_ = 0;
  bool hitsSorted_ = true;
  int appliedLibraryTab_ = -1;
  std::unordered_map<std::string, bool> existsCache_;
  double existsCacheTime_ = -100;

  // touch gestures
  struct Touch {
    bool active = false;
    bool multi = false;      // a second finger joined: pinch, not a tap/swipe
    bool overUi = false;     // started on a panel: ImGui handles it
    bool dismiss = false;    // started outside open menus/panels: lifting the finger returns to reading
    bool brightness = false; // a vertical swipe on the left part of the page: screen brightness (Android)
    float brightnessY = 0;   // where the brightness swipe started, and the level it started from
    float brightnessFrom = 0;
    SDL_FingerID id = 0;
    float x0 = 0, y0 = 0;    // framebuffer pixels
    float x = 0, y = 0;
    double t0 = 0;
  } touch_;
  bool touchFirst_ = false;  // phone/tablet UI conventions
  bool quitRequested_ = false;
  float toolbarHeight_ = 0;  // window units, measured each frame (panels are placed below it)

  // short notes near the top ("Two pages need a wider screen ...")
  std::string toast_;
  double toastUntil_ = 0;

  // safe area (notches, rounded corners, navigation bar) in framebuffer pixels
  float safeLeft_ = 0, safeTop_ = 0, safeRight_ = 0, safeBottom_ = 0;

  // storage permission (Android)
  bool storageAccessCached_ = true;
  bool storageAccessKnown_ = false;
  double storageAccessChecked_ = -100;
  bool storagePromptOpen_ = false;    // first start without access: explain and ask
  bool searchNeedsAccess_ = false;    // the last library search ran without access: repeat it once granted

  // file browser
  struct BrowserEntry {
    std::string name;
    std::string path;
    bool dir = false;
    uint64_t size = 0;
  };
  struct FileBrowser {
    bool open = false;
    bool folderMode = false;
    std::string dir;
    std::vector<BrowserEntry> entries;
    std::string error;
    bool scrollTop = false;
  } browser_;
};

}  // namespace ll
```
