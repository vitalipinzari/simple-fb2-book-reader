# Unit tests

The whole unit test program. The re-created code must compile against it unchanged and pass every check.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `tests/core_tests.cpp` | 65210 | `a6da6c5137e18772…` |

## `tests/core_tests.cpp`

UTF-8 without BOM, CRLF line endings, ends with a newline.

```cpp
// Lanternleaf unit tests (no framework: a failing CHECK prints the location and the run returns 1).
#include <miniz.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <thread>
#include <vector>

#include "core/BookLoader.h"
#include "core/Document.h"
#include "core/Encoding.h"
#include "core/Fb2Parser.h"
#include "core/FileUtil.h"
#include "core/Hyphenator.h"
#include "core/ImageCodec.h"
#include "core/LibrarySearch.h"
#include "core/LineBreaker.h"
#include "core/PdfContent.h"
#include "core/PdfCrypt.h"
#include "core/PdfParser.h"
#include "core/PdfReader.h"
#include "core/TxtParser.h"
#include "core/Unicode.h"
#include "core/XmlReader.h"

#ifdef LL_TESTS_WITH_TEXT
#include "text/BookLayout.h"
#include "text/FontLibrary.h"
#include "text/Shaper.h"
#endif

using namespace ll;

static int g_failures = 0;
static int g_checks = 0;
#define CHECK(cond)                                                          \
  do {                                                                       \
    ++g_checks;                                                              \
    if (!(cond)) {                                                           \
      ++g_failures;                                                          \
      std::printf("FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond);          \
    }                                                                        \
  } while (0)
#define CHECK_EQ(a, b)                                                                     \
  do {                                                                                     \
    ++g_checks;                                                                            \
    const auto& va_ = (a);                                                                 \
    const auto& vb_ = (b);                                                                 \
    if (!(va_ == vb_)) {                                                                   \
      ++g_failures;                                                                        \
      std::printf("FAILED %s:%d: %s == %s\n", __FILE__, __LINE__, #a, #b);                 \
    }                                                                                      \
  } while (0)

static std::string g_assets = "assets";

static std::string readAsset(const std::string& rel) {
  std::string s;
  readFile(g_assets + "/" + rel, s);
  return s;
}

// Encodes UTF-8 text into a single-byte charset by inverting the decoder.
static std::string encodeSingleByte(const std::string& utf8, Charset cs) {
  std::map<char32_t, unsigned char> inv;
  for (int b = 0x80; b <= 0xFF; ++b) {
    const std::string one(1, static_cast<char>(b));
    const std::string dec = decodeToUtf8(one, cs);
    size_t i = 0;
    inv[utf8Decode(dec, i)] = static_cast<unsigned char>(b);
  }
  std::string out;
  for (size_t i = 0; i < utf8.size();) {
    const char32_t c = utf8Decode(utf8, i);
    if (c < 0x80) out.push_back(static_cast<char>(c));
    else out.push_back(static_cast<char>(inv.count(c) ? inv[c] : '?'));
  }
  return out;
}

static void testUnicode() {
  const std::string s = "Ёж «ёлка» — Straße";
  const std::u32string u = utf8ToU32(s);
  CHECK_EQ(u32ToUtf8(u), s);
  CHECK_EQ(utf8Length(s), size_t(18));
  CHECK_EQ(toLowerUtf8("ПРИВЕТ Мир ЁЖ"), std::string("привет мир ёж"));
  CHECK_EQ(foldForSearch("ЁЛКА  «Ёжик»\tCafé"), std::string("елка \"ежик\" cafe"));
  CHECK(toUpperCp(U'я') == U'Я');
  CHECK(toLowerCp(U'Ї') == U'ї');
  // Invalid UTF-8 never stalls and yields U+FFFD.
  const std::string bad = "a\xC3(b\xE2\x82";
  size_t i = 0;
  int count = 0;
  while (i < bad.size()) {
    utf8Decode(bad, i);
    ++count;
  }
  CHECK_EQ(count, 6);
  size_t multi = 0, errs = 0;
  CHECK(!utf8Validate(bad, &multi, &errs));
  CHECK(errs > 0);
  CHECK_EQ(collapseSpaces("  a \t b\n\nc  "), std::string("a b c"));
}

static const char* kRussianSample =
    "Все счастливые семьи похожи друг на друга, каждая несчастливая семья несчастлива по-своему. "
    "Все смешалось в доме Облонских. Жена узнала, что муж был в связи с бывшею в их доме "
    "француженкою-гувернанткой, и объявила мужу, что не может жить с ним в одном доме.";

static void testEncodings() {
  const std::string ru = kRussianSample;
  for (Charset cs : {Charset::Cp1251, Charset::Koi8R, Charset::Cp866}) {
    const std::string enc = encodeSingleByte(ru, cs);
    CHECK(enc.size() < ru.size());
    CHECK(detectCharset(enc) == cs);
    CHECK_EQ(decodeToUtf8(enc, cs), ru);
    CHECK_EQ(bytesToUtf8(enc), ru);
  }
  CHECK(detectCharset(ru) == Charset::Utf8);
  // UTF-16 with and without BOM
  std::string u16 = "\xFF\xFE";
  for (char32_t c : utf8ToU32("Привет, world")) {
    u16.push_back(static_cast<char>(c & 0xFF));
    u16.push_back(static_cast<char>(c >> 8));
  }
  CHECK_EQ(bytesToUtf8(u16), std::string("Привет, world"));
  CHECK(charsetFromName("Windows-1251") == Charset::Cp1251);
  CHECK(charsetFromName("koi8-r") == Charset::Koi8R);
  // Western text with smart quotes goes to cp1252.
  const std::string west = "Caf\xE9 cr\xE8me br\xFBl\xE9\x65 \x93quoted\x94 na\xEFve r\xE9sum\xE9 \xE0 la carte";
  CHECK(detectCharset(west) == Charset::Cp1252);
}

static void testXml() {
  XmlReader r("<?xml version='1.0'?><!-- c --><a x=\"1&amp;2\" l:href='#n1'>T&lt;e&#x41;&mdash;<b/>x < y &bogus; </a>");
  CHECK(r.next() == XmlReader::Token::StartTag);
  CHECK(r.name() == "a");
  CHECK(r.attr("x") == "1&2");
  CHECK(r.attr("href") == "#n1");
  CHECK(r.next() == XmlReader::Token::Text);
  CHECK_EQ(r.text(), std::string("T<eA\xE2\x80\x94"));
  CHECK(r.next() == XmlReader::Token::StartTag);
  CHECK(r.name() == "b");
  CHECK(r.selfClosing());
  CHECK(r.next() == XmlReader::Token::EndTag);
  CHECK(r.next() == XmlReader::Token::Text);
  CHECK_EQ(r.text(), std::string("x < y &bogus; "));
  CHECK(r.next() == XmlReader::Token::EndTag);
  CHECK(r.next() == XmlReader::Token::End);
}

// 1x1 transparent PNG
static const char* kPngB64 =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

static std::string sampleFb2(const char* encodingDecl) {
  std::string s = std::string("<?xml version=\"1.0\" encoding=\"") + encodingDecl + "\"?>\n";
  s += "<FictionBook xmlns=\"http://www.gribuser.ru/xml/fictionbook/2.0\" xmlns:l=\"http://www.w3.org/1999/xlink\">\n"
       "<description><title-info><genre>prose_classic</genre>"
       "<author><first-name>Лев</first-name><middle-name>Николаевич</middle-name><last-name>Толстой</last-name></author>"
       "<book-title>Анна Каренина</book-title><annotation><p>Роман о любви.</p></annotation>"
       "<coverpage><image l:href=\"#cover.png\"/></coverpage><lang>ru</lang>"
       "<sequence name=\"Классика\" number=\"3\"/></title-info>"
       "<document-info><author><nickname>converter</nickname></author></document-info></description>\n"
       "<body><title><p>Лев Толстой</p><p>Анна Каренина</p></title>"
       "<epigraph><p>Мне отмщение, и аз воздам.</p></epigraph>"
       "<section id=\"part1\"><title><p>Часть первая</p></title>"
       "<section><title><p>I</p></title>"
       "<p>Все <emphasis>счастливые</emphasis> семьи похожи<a l:href=\"#n1\" type=\"note\">1</a> друг на друга.</p>"
       "<p>   Второй    абзац\n с <strong>жирным <emphasis>и курсивом</emphasis></strong> текстом.  </p>"
       "<empty-line/><p>* * *</p>"
       "<poem><stanza><v>Строка один</v><v>Строка два</v></stanza><stanza><v>Строка три</v></stanza></poem>"
       "<p>Незакрытый <emphasis>курсив</p><p>Обычный текст</p>"
       "</section></section></body>\n"
       "<body name=\"notes\"><title><p>Примечания</p></title>"
       "<section id=\"n1\"><title><p>1</p></title><p>Текст сноски.</p></section></body>\n"
       "<binary id=\"cover.png\" content-type=\"image/png\">";
  s += kPngB64;
  s += "</binary></FictionBook>\n";
  return s;
}

static void checkSampleDoc(const Document& doc) {
  CHECK_EQ(doc.meta.title, std::string("Анна Каренина"));
  CHECK(doc.meta.authors.size() == 1);
  if (!doc.meta.authors.empty()) CHECK_EQ(doc.meta.authors[0], std::string("Лев Николаевич Толстой"));
  CHECK_EQ(doc.meta.series, std::string("Классика"));
  CHECK_EQ(doc.meta.seriesIndex, 3);
  CHECK_EQ(doc.meta.lang, std::string("ru"));
  CHECK_EQ(doc.meta.annotation, std::string("Роман о любви."));
  CHECK(doc.coverImage == 0);
  CHECK(!doc.blocks.empty() && doc.blocks[0].type == BlockType::Image);
  // body title, part, chapter, notes title
  CHECK(doc.toc.size() == 4);
  if (doc.toc.size() == 4) {
    CHECK_EQ(doc.toc[0].title, std::string("Лев Толстой. Анна Каренина"));
    CHECK_EQ(doc.toc[1].title, std::string("Часть первая"));
    CHECK_EQ(doc.toc[1].level, 1);
    CHECK_EQ(doc.toc[2].title, std::string("I"));
    CHECK_EQ(doc.toc[2].level, 2);
    CHECK_EQ(doc.toc[3].title, std::string("Примечания"));
  }
  const Block* para = nullptr;
  const Block* second = nullptr;
  int verses = 0, stanzaStarts = 0;
  bool sawSeparator = false, sawEmpty = false, sawEpigraph = false;
  const Block* unclosed = nullptr;
  const Block* plain = nullptr;
  for (const Block& b : doc.blocks) {
    if (b.text.rfind("Все ", 0) == 0) para = &b;
    if (b.text.rfind("Второй", 0) == 0) second = &b;
    if (b.type == BlockType::Verse) {
      ++verses;
      stanzaStarts += b.stanzaStart ? 1 : 0;
    }
    if (b.type == BlockType::Separator) sawSeparator = true;
    if (b.type == BlockType::EmptyLine) sawEmpty = true;
    if (b.type == BlockType::Epigraph) sawEpigraph = true;
    if (b.text.rfind("Незакрытый", 0) == 0) unclosed = &b;
    if (b.text == "Обычный текст") plain = &b;
  }
  CHECK(verses == 3);
  CHECK(stanzaStarts == 2);
  CHECK(sawSeparator);
  CHECK(sawEmpty);
  CHECK(sawEpigraph);
  CHECK(para != nullptr);
  if (para) {
    CHECK_EQ(para->text, std::string("Все счастливые семьи похожи1 друг на друга."));
    const uint32_t italicAt = static_cast<uint32_t>(std::string("Все ").size());
    CHECK((spanFlagsAt(*para, italicAt) & kSpanItalic) != 0);
    CHECK((spanFlagsAt(*para, 0) & kSpanItalic) == 0);
    const uint32_t noteAt = static_cast<uint32_t>(para->text.find('1'));
    int32_t link = -1;
    const uint8_t f = spanFlagsAt(*para, noteAt, &link);
    CHECK((f & kSpanNoteRef) != 0);
    CHECK((f & kSpanSup) != 0);
    CHECK(link >= 0 && link < static_cast<int32_t>(doc.links.size()));
    if (link >= 0 && link < static_cast<int32_t>(doc.links.size())) CHECK_EQ(doc.links[link], std::string("#n1"));
  }
  CHECK(second != nullptr);
  if (second) {
    CHECK_EQ(second->text, std::string("Второй абзац с жирным и курсивом текстом."));
    const uint32_t boldItalic = static_cast<uint32_t>(second->text.find("курсивом"));
    CHECK((spanFlagsAt(*second, boldItalic) & (kSpanBold | kSpanItalic)) == (kSpanBold | kSpanItalic));
  }
  CHECK(unclosed != nullptr);
  CHECK(plain != nullptr);
  if (plain) CHECK(spanFlagsAt(*plain, 0) == 0);  // unclosed <emphasis> must not leak
  auto it = doc.anchors.find("n1");
  CHECK(it != doc.anchors.end());
  if (it != doc.anchors.end()) {
    const std::string note = doc.plainText(it->second.block, it->second.endBlock);
    CHECK(note.find("Текст сноски.") != std::string::npos);
    CHECK(doc.blocks[it->second.block].notes);
  }
  CHECK(doc.anchors.count("part1") == 1);
  CHECK(doc.totalChars > 100);
}

static void testFb2() {
  Document doc;
  std::string err;
  CHECK(parseFb2(sampleFb2("UTF-8"), doc, &err));
  checkSampleDoc(doc);
  // Same book stored in windows-1251.
  const std::string cp = encodeSingleByte(sampleFb2("windows-1251"), Charset::Cp1251);
  Document doc2;
  CHECK(parseFb2(cp, doc2, &err));
  checkSampleDoc(doc2);
  CHECK_EQ(doc2.meta.encoding, std::string("windows-1251"));
  // Declared windows-1251 but actually UTF-8.
  Document doc3;
  CHECK(parseFb2(sampleFb2("windows-1251"), doc3, &err));
  checkSampleDoc(doc3);
  // Metadata fast path.
  BookMeta meta;
  CHECK(parseFb2Meta(cp, meta));
  CHECK_EQ(meta.title, std::string("Анна Каренина"));
  // Plain text for full-text search excludes binaries.
  std::string text;
  BookMeta m2;
  fb2ExtractText(cp, text, &m2);
  CHECK(text.find("друг на друга") != std::string::npos);
  CHECK(text.find("iVBOR") == std::string::npos);
  CHECK_EQ(m2.title, std::string("Анна Каренина"));
  // Garbage never crashes.
  Document junk;
  parseFb2("<FictionBook><body><section><p>broken <emphasis>text</section", junk, &err);
  CHECK(!junk.blocks.empty());
}

static void testTxt() {
  // Hard-wrapped, blank-line separated (Project Gutenberg style).
  std::string g =
      "Title: Test Book\r\nAuthor: Jane Doe\r\n\r\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\r\n\r\n"
      "CHAPTER I\r\n\r\n";
  for (int p = 0; p < 6; ++p) {
    g += "It was a bright cold day in April, and the clocks were striking thirteen.\r\n"
         "Winston Smith, his chin nuzzled into his breast in an effort to escape the\r\n"
         "vile wind, slipped quickly through the glass doors of Victory Mansions.\r\n\r\n";
  }
  g += "CHAPTER II\r\n\r\nShort.\r\n\r\n*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\r\nlicense text";
  Document doc;
  CHECK(parseTxt(g, doc, "whatever"));
  CHECK_EQ(doc.meta.title, std::string("Test Book"));
  CHECK(doc.meta.authors.size() == 1 && doc.meta.authors[0] == "Jane Doe");
  CHECK(doc.toc.size() == 2);
  int paras = 0;
  for (const Block& b : doc.blocks) {
    if (b.type == BlockType::Paragraph) {
      ++paras;
      CHECK(b.text.find("\n") == std::string::npos);
    }
    CHECK(b.text.find("license") == std::string::npos);
  }
  CHECK_EQ(paras, 7);
  if (doc.blocks.size() > 1) {
    CHECK(doc.blocks[1].text.rfind("It was a bright", 0) == 0);
    CHECK(doc.blocks[1].text.find("Mansions.") != std::string::npos);
  }

  // Russian, indented paragraphs, cp1251, lib.ru style.
  std::string r;
  r += "     Глава 1\n\n";
  for (int p = 0; p < 5; ++p) {
    r += "     Все счастливые семьи похожи друг на друга, каждая несчастливая\n"
         "семья несчастлива по-своему. Все смешалось в доме Облонских.\n";
  }
  r += "     Глава вторая\n";
  r += "     Жена узнала, что муж был в связи с бывшею в их доме француженкою.\n";
  const std::string cp = encodeSingleByte(r, Charset::Cp1251);
  Document d2;
  CHECK(parseTxt(cp, d2, "Толстой - Анна Каренина"));
  CHECK_EQ(d2.meta.title, std::string("Анна Каренина"));
  CHECK(d2.meta.authors.size() == 1 && d2.meta.authors[0] == "Толстой");
  CHECK_EQ(d2.meta.encoding, std::string("windows-1251"));
  CHECK(d2.toc.size() == 2);
  int p2 = 0;
  for (const Block& b : d2.blocks) {
    if (b.type == BlockType::Paragraph) ++p2;
  }
  CHECK_EQ(p2, 6);

  // One paragraph per line, no wrapping.
  std::string lines;
  for (int i = 0; i < 20; ++i) {
    lines += "This is a long paragraph number " + std::to_string(i) +
             " that goes on and on without any hard wrapping, as modern text files usually do. " +
             std::string(static_cast<size_t>(i % 5) * 20, 'x') + "\n";
  }
  Document d3;
  CHECK(parseTxt(lines, d3, "x"));
  CHECK_EQ(d3.blocks.size(), size_t(20));
}

static void testHyphenation(HyphenationService& hs) {
  CHECK(hs.english().load(readAsset("hyphenation/hyph-en-us.pat.txt"), readAsset("hyphenation/hyph-en-us.hyp.txt"),
                          2, 3));
  CHECK(hs.russian().load(readAsset("hyphenation/hyph-ru.pat.txt"), readAsset("hyphenation/hyph-ru.hyp.txt"), 2,
                          2));
  auto hyph = [&](const std::string& w) {
    std::vector<int> br;
    const std::u32string u = utf8ToU32(w);
    hs.hyphenate(u, br);
    std::u32string out;
    size_t k = 0;
    for (size_t i = 0; i < u.size(); ++i) {
      if (k < br.size() && static_cast<size_t>(br[k]) == i) {
        out.push_back(U'-');
        ++k;
      }
      out.push_back(u[i]);
    }
    return u32ToUtf8(out);
  };
  std::printf("  hyphenation: %s %s %s %s %s %s %s\n", hyph("hyphenation").c_str(), hyph("computer").c_str(),
              hyph("Table").c_str(), hyph("переносы").c_str(), hyph("программирование").c_str(),
              hyph("Достоевский").c_str(), hyph("несчастливая").c_str());
  CHECK_EQ(hyph("hyphenation"), std::string("hy-phen-ation"));
  CHECK_EQ(hyph("Table"), std::string("Ta-ble"));
  CHECK_EQ(hyph("переносы"), std::string("пе-ре-но-сы"));
  CHECK_EQ(hyph("abc"), std::string("abc"));
  CHECK_EQ(hyph("Москва2"), std::string("Москва2"));  // digits: untouched
}

static void testLineBreaker() {
  // Ten words of width 10 separated by glue 3 (+1.5/-1); line width 40 -> 3 words per line.
  std::vector<LbItem> items;
  for (int i = 0; i < 10; ++i) {
    if (i > 0) items.push_back(LbItem{LbItem::Glue, false, 3, 1.5f, 1, 0});
    items.push_back(LbItem{LbItem::Box, false, 10, 0, 0, 0});
  }
  items.push_back(LbItem{LbItem::Glue, false, 0, kLbFillStretch, 0, 0});
  items.push_back(LbItem{LbItem::Penalty, true, 0, 0, 0, -kLbInfPenalty});
  std::vector<LbBreak> br;
  CHECK(breakLinesOptimal(items, {40.f}, LbParams{}, br));
  CHECK_EQ(br.size(), size_t(4));
  CHECK(br.back().item == static_cast<int>(items.size()) - 1);
  std::vector<LbBreak> greedy;
  breakLinesGreedy(items, {40.f}, greedy);
  CHECK_EQ(greedy.size(), size_t(4));
  // A box wider than the line: optimal fails, greedy overflows gracefully.
  std::vector<LbItem> wide = {LbItem{LbItem::Box, false, 100, 0, 0, 0},
                              LbItem{LbItem::Glue, false, 0, kLbFillStretch, 0, 0},
                              LbItem{LbItem::Penalty, true, 0, 0, 0, -kLbInfPenalty}};
  CHECK(!breakLinesOptimal(wide, {40.f}, LbParams{}, br));
  breakLinesGreedy(wide, {40.f}, greedy);
  CHECK_EQ(greedy.size(), size_t(1));
}

static void testMatching() {
  CHECK_EQ(translitSkeleton(foldForSearch("Толстой")), translitSkeleton("tolstoy"));
  CHECK_EQ(translitSkeleton(foldForSearch("Толстой")), translitSkeleton("Tolstoj"));
  CHECK_EQ(translitSkeleton(foldForSearch("Достоевский")), translitSkeleton(foldForSearch("Dostoevsky")));
  CHECK_EQ(translitSkeleton(foldForSearch("Цветаева")), translitSkeleton(foldForSearch("Tsvetaeva")));
  CHECK_EQ(translitSkeleton(foldForSearch("Чехов")), translitSkeleton(foldForSearch("Chekhov")));
  QueryMatcher q("толстой каренина");
  CHECK(q.termCount() == 2);
  CHECK(q.matchField("Tolstoy_Anna-Karenina.fb2") == q.allTermsMask());
  CHECK(q.matchField("Лев Толстой") == 1u);
  CHECK(q.matchField("Something else") == 0u);
  QueryMatcher ph("счастливые семьи");
  const std::string text = "Все  СЧАСТЛИВЫЕ\nсемьи похожи";
  const size_t pos = ph.findPhrase(text);
  CHECK(pos != std::string::npos);
  CHECK(pos == text.find("СЧАСТЛИВЫЕ"));
  CHECK(makeSnippet(text, pos, 10, 5).find("СЧАСТЛИВЫЕ") != std::string::npos);
  CHECK(QueryMatcher("").empty());
  CHECK(LibrarySearch::isNonBookTextName("LICENSE"));
  CHECK(LibrarySearch::isNonBookTextName("grid-third-party-licenses"));
  CHECK(LibrarySearch::isNonBookTextName("ReadMe"));
  CHECK(LibrarySearch::isNonBookTextName("InstallLog"));
  CHECK(!LibrarySearch::isNonBookTextName("Война и мир"));
  CHECK(!LibrarySearch::isNonBookTextName("Pride and Prejudice"));
}

static void testTxtTypography() {
  std::string g = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n";
  g += "It is _very_ good--said he. - Yes.\n\n- Dialogue line here...- he said.\n\n";
  Document d;
  CHECK(parseTxt(g, d, "x"));
  CHECK(d.blocks.size() == 2);
  if (d.blocks.size() == 2) {
    CHECK_EQ(d.blocks[0].text, std::string("It is very good\xE2\x80\x94said he. \xE2\x80\x94 Yes."));
    const uint32_t v = static_cast<uint32_t>(d.blocks[0].text.find("very"));
    CHECK((spanFlagsAt(d.blocks[0], v) & kSpanItalic) != 0);
    CHECK((spanFlagsAt(d.blocks[0], v + 5) & kSpanItalic) == 0);
    CHECK_EQ(d.blocks[1].text, std::string("\xE2\x80\x94 Dialogue line here... \xE2\x80\x94 he said."));
  }
}

static void writeBytes(const std::filesystem::path& p, const std::string& data) {
  std::ofstream f(p, std::ios::binary);
  f.write(data.data(), static_cast<std::streamsize>(data.size()));
}

static void testWebAddresses() {
  const std::string text =
      "See https://www.gutenberg.org/ebooks/1342. Or www.example.com, (http://a.b/c_(d)) and "
      "\xC2\xABhttp://x.ru/\xD0\xBF\xD1\x83\xD1\x82\xD1\x8C\xC2\xBB.";
  const auto found = findWebAddresses(text);
  std::vector<std::string> urls;
  for (const auto& [b, e] : found) urls.push_back(text.substr(b, e - b));
  CHECK_EQ(static_cast<int>(urls.size()), 4);
  if (urls.size() == 4) {
    CHECK_EQ(urls[0], std::string("https://www.gutenberg.org/ebooks/1342"));  // sentence full stop left out
    CHECK_EQ(urls[1], std::string("www.example.com"));                        // comma left out
    CHECK_EQ(urls[2], std::string("http://a.b/c_(d)"));                       // own brackets kept, outer one not
    CHECK_EQ(urls[3], std::string("http://x.ru/\xD0\xBF\xD1\x83\xD1\x82\xD1\x8C"));  // ends at the guillemet
  }
  CHECK(findWebAddresses("version 1.2, file.txt, e.g. me@www.x.com, www.").empty());
  CHECK(isWebLink("https://x.org") && isWebLink("HTTP://X.ORG") && isWebLink("mailto:a@b.c") && !isWebLink("#note1"));

  // finalize() turns them into links and keeps the other styles of the text around them.
  Document d;
  Block b;
  b.text = "Visit https://example.com/page now";
  b.spans = {Span{0, kSpanItalic, -1}};
  d.blocks.push_back(b);
  d.finalize();
  CHECK(d.links.size() == 1 && d.links[0] == "https://example.com/page");
  const Block& r = d.blocks[0];
  int32_t link = -1;
  CHECK((spanFlagsAt(r, 6, &link) & (kSpanLink | kSpanItalic)) == (kSpanLink | kSpanItalic));
  CHECK_EQ(link, 0);
  CHECK((spanFlagsAt(r, 29) & kSpanLink) != 0);
  CHECK((spanFlagsAt(r, 30, &link) & kSpanLink) == 0);  // " now"
  CHECK((spanFlagsAt(r, 30) & kSpanItalic) != 0);
  CHECK_EQ(link, -1);
  CHECK((spanFlagsAt(r, 2) & kSpanLink) == 0);  // "Visit"
  // An address that already is a link in the book is left alone; "www." addresses open with https.
  Document d2;
  Block b2;
  b2.text = "go http://x.org and www.gutenberg.org";
  b2.spans = {Span{3, kSpanLink, 0}, Span{15, 0, -1}};
  d2.links.push_back("http://x.org");
  d2.blocks.push_back(b2);
  d2.finalize();
  CHECK_EQ(static_cast<int>(d2.links.size()), 2);
  if (d2.links.size() == 2) CHECK_EQ(d2.links[1], std::string("https://www.gutenberg.org"));
  CHECK((spanFlagsAt(d2.blocks[0], 22, &link) & kSpanLink) != 0);
  CHECK_EQ(link, 1);
}

static void testLibrarySearch() {
  namespace fs = std::filesystem;
  const fs::path dir = fs::temp_directory_path() /
                       ("lanternleaf_tests_" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(dir / u8"Загрузки" / "deep");
  fs::create_directories(dir / "node_modules");
  writeBytes(dir / u8"Загрузки" / "book1.fb2", encodeSingleByte(sampleFb2("windows-1251"), Charset::Cp1251));
  std::string bigTxt;
  for (int i = 0; i < 300; ++i) bigTxt += std::string(kRussianSample) + "\n\n";
  bigTxt += "Уникальная фраза для поиска внутри текста.\n";
  writeBytes(dir / u8"Загрузки" / "deep" / u8"Неизвестный - Записки.txt", encodeSingleByte(bigTxt, Charset::Koi8R));
  writeBytes(dir / "small.txt", "tiny");
  writeBytes(dir / "node_modules" / "hidden.fb2", sampleFb2("UTF-8"));
  {
    // zipped FB2
    const std::string fb2 = sampleFb2("UTF-8");
    mz_zip_archive zip;
    std::memset(&zip, 0, sizeof(zip));
    CHECK(mz_zip_writer_init_heap(&zip, 0, 0));
    CHECK(mz_zip_writer_add_mem(&zip, "Tolstoy_Anna.fb2", fb2.data(), fb2.size(),
                                static_cast<mz_uint>(MZ_DEFAULT_LEVEL)));
    void* buf = nullptr;
    size_t size = 0;
    CHECK(mz_zip_writer_finalize_heap_archive(&zip, &buf, &size));
    writeBytes(dir / "Tolstoy_Anna.fb2.zip", std::string(static_cast<const char*>(buf), size));
    mz_zip_writer_end(&zip);
  }
  const std::string root = pathToUtf8(dir);

  // Zip loading
  Document zdoc;
  std::string err;
  CHECK(loadBook(pathToUtf8(dir / "Tolstoy_Anna.fb2.zip"), zdoc, &err));
  CHECK_EQ(zdoc.meta.title, std::string("Анна Каренина"));
  CHECK(zdoc.meta.format == "FB2 (zip)");
  CHECK(!bookFingerprint(pathToUtf8(dir / "Tolstoy_Anna.fb2.zip")).empty());

  MetaCache cache;
  auto run = [&](SearchOptions o) {
    LibrarySearch s(cache);
    o.roots = {root};
    s.start(o);
    s.wait();
    std::vector<SearchHit> hits = s.takeHits();
    CHECK(s.progress().finished);
    return hits;
  };
  SearchOptions all;
  const auto everything = run(all);
  CHECK_EQ(everything.size(), size_t(3));  // node_modules skipped, tiny txt ignored

  SearchOptions byAuthor;
  byAuthor.query = "толстой";
  const auto a = run(byAuthor);
  CHECK_EQ(a.size(), size_t(2));
  for (const auto& h : a) CHECK((h.matched & (kMatchAuthor | kMatchName)) != 0);

  SearchOptions byName;
  byName.query = "записки";
  byName.byMeta = false;
  CHECK_EQ(run(byName).size(), size_t(1));

  SearchOptions byText;
  byText.query = "уникальная фраза для поиска";
  byText.byContent = true;
  const auto t = run(byText);
  CHECK_EQ(t.size(), size_t(1));
  if (!t.empty()) {
    CHECK(t[0].matched == kMatchText);
    CHECK(t[0].snippet.find("Уникальная фраза") != std::string::npos);
  }
  SearchOptions none;
  none.query = "zzzqqq";
  none.byContent = true;
  CHECK(run(none).empty());

  // Cache round trip
  const std::string cacheFile = pathToUtf8(dir / "cache.json");
  CHECK(cache.size() >= 3);
  CHECK(cache.save(cacheFile));
  MetaCache c2;
  CHECK(c2.load(cacheFile));
  CHECK_EQ(c2.size(), cache.size());

  std::error_code ec;
  fs::remove_all(dir, ec);
}

#ifdef LL_TESTS_WITH_TEXT
static void testTextLayout(HyphenationService& hs) {
  FontLibrary lib;
  CHECK(lib.ok());
  FontFamily fam;
  fam.name = "PT Serif";
  const char* files[4] = {"PTSerif-Regular.ttf", "PTSerif-Italic.ttf", "PTSerif-Bold.ttf", "PTSerif-BoldItalic.ttf"};
  for (int s = 0; s < 4; ++s) {
    fam.faces[s] = lib.addFromFile(g_assets + "/fonts/" + files[s]);
    CHECK(fam.faces[s] >= 0);
  }
  if (!fam.valid()) return;
  Shaper shaper(lib);
  shaper.setFamily(fam);
  const ShapedRun& r1 = shaper.shape("Привет, мир!", 0);
  CHECK(r1.glyphs.size() == 12);
  CHECK(r1.advance > 4.0f && r1.advance < 8.0f);
  CHECK(&shaper.shape("Привет, мир!", 0) == &r1);
  CHECK(&shaper.shape("Привет, мир!", 1) != &r1);
  const float av = shaper.shape("AV", 0).advance;
  const float a = shaper.shape("A", 0).advance, v = shaper.shape("V", 0).advance;
  std::printf("  kerning AV: %.3f vs %.3f\n", av, a + v);
  CHECK(av <= a + v);

  // A document with long paragraphs in both languages.
  Document doc;
  for (int i = 0; i < 40; ++i) {
    Block t;
    if (i % 10 == 0) {
      t.type = BlockType::Title;
      t.level = 1;
      t.text = "Глава " + std::to_string(i / 10 + 1);
      t.pageBreakBefore = i > 0;
      doc.blocks.push_back(t);
    }
    Block b;
    b.text = (i % 2 == 0) ? std::string(kRussianSample) + " " + kRussianSample
                          : "It was the best of times, it was the worst of times, it was the age of wisdom, it was "
                            "the age of foolishness, it was the epoch of belief, it was the epoch of incredulity, "
                            "it was the season of Light, it was the season of Darkness, internationalization.";
    doc.blocks.push_back(b);
  }
  doc.finalize();
  BookLayout layout(shaper, &hs);
  layout.setDocument(&doc);
  LayoutParams p;
  p.fontSize = 20;
  p.pageWidth = 420;
  p.pageHeight = 600;
  layout.setParams(p);

  int overflow = 0, ragged = 0, totalLines = 0, hyphenated = 0;
  for (int bi = 0; bi < layout.blockCount(); ++bi) {
    const BlockLayout& bl = layout.block(bi);
    for (size_t li = 0; li < bl.lines.size(); ++li) {
      const LayoutLine& L = bl.lines[li];
      ++totalLines;
      if (L.runs.empty()) continue;
      const PlacedRun& last = L.runs.back();
      const float right = last.x + last.width;
      if (right > p.pageWidth + 0.75f) ++overflow;
      if (doc.blocks[bi].type == BlockType::Paragraph && li + 1 < bl.lines.size() && std::fabs(right - p.pageWidth) > 0.75f)
        ++ragged;
      if (last.run == &shaper.shape("-", 0) && last.start == last.end) ++hyphenated;
    }
  }
  std::printf("  lines=%d overflow=%d ragged=%d hyphenated=%d (optimal ok=%llu fail=%llu greedy=%llu)\n", totalLines,
              overflow, ragged, hyphenated, static_cast<unsigned long long>(lbStats().optimalOk),
              static_cast<unsigned long long>(lbStats().optimalFail), static_cast<unsigned long long>(lbStats().greedy));
  CHECK(overflow == 0);
  CHECK(ragged == 0);
  CHECK(hyphenated > 0);

  // Pagination covers every line exactly once and pages are consistent forwards/backwards.
  std::vector<LinePos> starts;
  LinePos pos = layout.normalize(LinePos{0, 0});
  int pageLines = 0;
  while (!layout.isEnd(pos)) {
    const Page pg = layout.pageFrom(pos);
    CHECK(!pg.empty());
    if (pg.empty()) break;
    CHECK(pg.lines.front().pos == pos);
    float bottom = 0;
    for (const PageLine& pl : pg.lines) bottom = pl.y + layout.metrics(pl.pos.block).lineHeights[pl.pos.line];
    CHECK(bottom <= p.pageHeight + 0.01f);
    pageLines += static_cast<int>(pg.lines.size());
    starts.push_back(pos);
    pos = pg.end;
  }
  CHECK_EQ(pageLines, totalLines);
  int consistent = 0;
  for (size_t k = 1; k < starts.size(); ++k) {
    if (layout.pageStartBefore(starts[k]) == starts[k - 1]) ++consistent;
  }
  std::printf("  pages=%zu back-consistent=%d\n", starts.size(), consistent);
  CHECK(consistent >= static_cast<int>(starts.size()) - 2);
  // Chapters start on a new page.
  for (size_t k = 0; k < starts.size(); ++k) {
    const Page pg = layout.pageFrom(starts[k]);
    for (size_t li = 1; li < pg.lines.size(); ++li) {
      const LinePos lp = pg.lines[li].pos;
      CHECK(!(lp.line == 0 && doc.blocks[lp.block].pageBreakBefore));
    }
  }
  // Background page count agrees with manual pagination.
  while (!layout.countDone()) layout.countStep(5.0);
  CHECK_EQ(layout.pageCount(), static_cast<int>(starts.size()));
  if (starts.size() > 3) CHECK_EQ(layout.pageIndexOf(starts[3]), 3);

  // The menu bars come and go: only the page height changes. The pages counted for the shorter height match
  // a fresh layout, and switching back restores the earlier page count at once.
  {
    const int fullPages = layout.pageCount();
    LayoutParams shorter = p;
    shorter.pageHeight = 480;
    layout.setParams(shorter);
    CHECK(!layout.countDone());
    while (!layout.countDone()) layout.countStep(5.0);
    BookLayout fresh(shaper, &hs);
    fresh.setDocument(&doc);
    fresh.setParams(shorter);
    while (!fresh.countDone()) fresh.countStep(5.0);
    CHECK_EQ(layout.pageCount(), fresh.pageCount());
    CHECK(layout.pageCount() > fullPages);
    bool samePages = true;
    for (int k = 0; k < fresh.pageCount(); ++k) samePages = samePages && layout.pageStart(k) == fresh.pageStart(k);
    CHECK(samePages);
    layout.setParams(p);
    CHECK(layout.countDone());
    CHECK_EQ(layout.pageCount(), fullPages);
    layout.setParams(shorter);
    CHECK(layout.countDone());
    CHECK_EQ(layout.pageCount(), fresh.pageCount());
    layout.setParams(p);
  }

  // Zoom keeps the reading position: the line containing an offset stays the line containing it.
  const int blk = 5;
  const uint32_t off = static_cast<uint32_t>(doc.blocks[blk].text.size() / 2);
  p.fontSize = 28;
  layout.setParams(p);
  const LinePos z = layout.posForOffset(blk, off);
  const BlockMetrics& zm = layout.metrics(blk);
  CHECK(z.block == blk);
  CHECK(zm.lineStarts[z.line] <= off);
  if (z.line + 1 < static_cast<int>(zm.lineStarts.size())) CHECK(zm.lineStarts[z.line + 1] > off);

  // A heading taller than the whole page (broken FB2: the title holds the entire table of contents) starts
  // right after the previous heading instead of leaving that page empty.
  {
    Document dh;
    Block h1;
    h1.type = BlockType::Title;
    h1.level = 1;
    h1.text = "Chapter I";
    dh.blocks.push_back(h1);
    Block h2 = h1;
    h2.text.clear();
    for (int k = 2; k <= 40; ++k) h2.text += "Chapter " + std::to_string(k) + ". The Rabbit Sends in a Little Bill ";
    dh.blocks.push_back(h2);
    Block body;
    body.text = kRussianSample;
    dh.blocks.push_back(body);
    dh.finalize();
    BookLayout lh(shaper, &hs);
    lh.setDocument(&dh);
    LayoutParams ph = p;
    ph.fontSize = 20;
    lh.setParams(ph);
    float h2Height = 0;
    for (float h : lh.metrics(1).lineHeights) h2Height += h;
    CHECK(h2Height > ph.pageHeight);
    const Page first = lh.pageFrom(lh.normalize(LinePos{0, 0}));
    bool hasH2 = false;
    for (const PageLine& pl : first.lines) hasH2 = hasH2 || pl.pos.block == 1;
    CHECK(hasH2);
    // ...while normal headings in the middle of the text never end a page: they move on with their text.
    Document ds;
    for (int k = 0; k < 30; ++k) {
      Block sub;
      sub.type = BlockType::Title;
      sub.level = 2;
      sub.text = "Part " + std::to_string(k + 1);
      ds.blocks.push_back(sub);
      Block para;
      const std::string english =
          "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of "
          "foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, it "
          "was the season of Darkness, it was the spring of hope, it was the winter of despair, we had everything "
          "before us, we had nothing before us, we were all going direct to Heaven, we were all going direct the "
          "other way.";
      para.text = (k % 3 == 0) ? std::string(kRussianSample) : english.substr(0, 120 + (37 * k) % 280);
      ds.blocks.push_back(para);
    }
    ds.finalize();
    BookLayout ls(shaper, &hs);
    ls.setDocument(&ds);
    ls.setParams(ph);
    int titleAtBottom = 0, pages = 0;
    for (LinePos q = ls.normalize(LinePos{0, 0}); !ls.isEnd(q) && pages < 500; ++pages) {
      const Page pg = ls.pageFrom(q);
      if (pg.empty()) break;
      if (!ls.isEnd(pg.end) && ds.blocks[pg.lines.back().pos.block].type == BlockType::Title) ++titleAtBottom;
      q = pg.end;
    }
    std::printf("  subtitle pages=%d, ending in a heading=%d\n", pages, titleAtBottom);
    CHECK(pages > 3);
    CHECK_EQ(titleAtBottom, 0);
  }

  // Very narrow column with an unbreakable URL: no crash, no endless loop, text overflows nowhere.
  Document d2;
  Block u;
  u.text = "See https://example.com/a/very/long/path/that/cannot/be/hyphenated/at/all/index.html for details.";
  d2.blocks.push_back(u);
  d2.finalize();
  BookLayout l2(shaper, &hs);
  l2.setDocument(&d2);
  LayoutParams p2 = p;
  p2.fontSize = 18;
  p2.pageWidth = 160;
  l2.setParams(p2);
  const BlockLayout& ub = l2.block(0);
  CHECK(ub.lines.size() >= 4);
  for (const LayoutLine& L : ub.lines) {
    if (!L.runs.empty()) CHECK(L.runs.back().x + L.runs.back().width <= p2.pageWidth + 1.0f);
  }
  // The address became a link (finalize) and is never hyphenated: lines end after a slash or before a dot.
  CHECK(d2.links.size() == 1);
  int urlHyphens = 0, slashEnds = 0;
  for (const LayoutLine& L : ub.lines) {
    if (L.runs.empty()) continue;
    const PlacedRun& last = L.runs.back();
    if (last.run == &shaper.shape("-", 0) && last.start == last.end) ++urlHyphens;
    if (last.end > 0 && last.end <= u.text.size() && u.text[last.end - 1] == '/') ++slashEnds;
  }
  std::printf("  narrow URL: %zu lines, %d end after a slash, %d hyphens\n", ub.lines.size(), slashEnds, urlHyphens);
  CHECK_EQ(urlHyphens, 0);
  CHECK(slashEnds >= 2);
}
#endif

// ---- PDF -------------------------------------------------------------------------------------------------------------

static std::string toHex(std::string_view s) {
  static const char* kDigits = "0123456789abcdef";
  std::string out;
  for (unsigned char c : s) {
    out += kDigits[c >> 4];
    out += kDigits[c & 15];
  }
  return out;
}

static std::string fromHex(std::string_view h) {
  std::string out;
  for (size_t k = 0; k + 1 < h.size(); k += 2)
    out += static_cast<char>(std::stoi(std::string(h.substr(k, 2)), nullptr, 16));
  return out;
}

static std::string deflateBytes(const std::string& data) {
  mz_ulong n = mz_compressBound(static_cast<mz_ulong>(data.size()));
  std::string out(n, '\0');
  mz_compress(reinterpret_cast<unsigned char*>(out.data()), &n, reinterpret_cast<const unsigned char*>(data.data()),
              static_cast<mz_ulong>(data.size()));
  out.resize(n);
  return out;
}

// A PDF made of numbered objects (1-based) with a classic cross-reference table.
struct PdfBuilder {
  std::vector<std::string> objs;
  int add(const std::string& body) {
    objs.push_back(body);
    return static_cast<int>(objs.size());
  }
  static std::string stream(const std::string& dict, const std::string& data) {
    return "<< " + dict + " /Length " + std::to_string(data.size()) + " >>\nstream\n" + data + "\nendstream";
  }
  std::string build(int root, const std::string& trailerExtra = "", int offsetError = 0) const {
    std::string out = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";
    std::vector<size_t> offs;
    for (size_t k = 0; k < objs.size(); ++k) {
      offs.push_back(out.size());
      out += std::to_string(k + 1) + " 0 obj\n" + objs[k] + "\nendobj\n";
    }
    const size_t xref = out.size();
    out += "xref\n0 " + std::to_string(objs.size() + 1) + "\n0000000000 65535 f \n";
    for (size_t o : offs) {
      char b[32];
      std::snprintf(b, sizeof(b), "%010zu 00000 n \n", o + static_cast<size_t>(offsetError));
      out += b;
    }
    out += "trailer\n<< /Size " + std::to_string(objs.size() + 1) + " /Root " + std::to_string(root) + " 0 R " +
           trailerExtra + " >>\nstartxref\n" + std::to_string(xref) + "\n%%EOF\n";
    return out;
  }
};

// A font whose glyphs are all half an em wide, so that lines of 50 characters are full lines.
static std::string testFont(const char* name) {
  std::string w;
  for (int c = 32; c <= 126; ++c) w += "500 ";
  return std::string("<< /Type /Font /Subtype /Type1 /BaseFont /") + name +
         " /FirstChar 32 /LastChar 126 /Widths [" + w + "] /Encoding /WinAnsiEncoding >>";
}

// A two-page book: running heads with page numbers, a chapter title, a hyphenated line end, a paragraph that goes on
// over the page break, a compound word broken at its hyphen, a list and an outline.
static std::string pdfTestBook(int offsetError = 0) {
  PdfBuilder b;
  const int catalog = b.add("<< /Type /Catalog /Pages 2 0 R /Outlines 9 0 R >>");
  b.add("<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> >>");
  b.add("<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>");
  b.add("<< /Type /Page /Parent 2 0 R /Contents 7 0 R >>");
  b.add(testFont("TestSerif"));
  auto page = [](const char* n, const std::string& body) {
    return std::string("BT /F1 8 Tf 20 385 Td (TEST BOOK) Tj ET BT /F1 8 Tf 262 385 Td (") + n + ") Tj ET\n" + body;
  };
  b.add(PdfBuilder::stream("", page("1",
      "BT /F1 16 Tf 20 350 Td (Chapter One) Tj ET\n"
      "BT /F1 10 Tf 13 TL 20 320 Td (The first paragraph of this book has many words to) Tj T*\n"
      "(fill several lines, and this one ends with a popu-) Tj T* (lation broken by hyphenation.) Tj ET\n"
      "BT /F1 10 Tf 13 TL 20 268 Td (A second paragraph begins here, and its final line) Tj T*\n"
      "[(on the first page is full, and so the text )-0(runs on)] TJ T*\n"
      "(to the next page; the next line carries on with no) Tj ET\n")));
  b.add(PdfBuilder::stream("", page("2",
      "BT /F1 10 Tf 13 TL 20 350 Td (break. A compound word broken at its hyphen: self-) Tj T*\n"
      "(made keeps the hyphen in the joined text of lines.) Tj T* (That is all.) Tj ET\n"
      "BT /F1 10 Tf 13 TL 20 300 Td (\\225 first item) Tj T* (\\225 second item) Tj ET\n")));
  b.add("<< /Title <feff" + toHex(std::string("\0T\0e\0s\0t\0 \0B\0o\0o\0k", 18)) + "> /Author (Jane Doe) >>");
  b.add("<< /Type /Outlines /First 10 0 R /Last 10 0 R /Count 2 >>");
  b.add("<< /Title (Chapter One) /Parent 9 0 R /First 11 0 R /Last 11 0 R /Dest [3 0 R /XYZ 0 400 null] >>");
  b.add("<< /Title (Page two) /Parent 10 0 R /Dest [4 0 R /XYZ 0 400 null] >>");
  return b.build(catalog, "/Info 8 0 R", offsetError);
}

static void checkTestBook(const Document& doc) {
  CHECK_EQ(doc.meta.format, std::string("PDF"));
  CHECK_EQ(doc.meta.title, std::string("Test Book"));
  CHECK(doc.meta.authors.size() == 1 && doc.meta.authors[0] == "Jane Doe");
  CHECK_EQ(doc.blocks.size(), size_t(5));
  if (doc.blocks.size() < 5) return;
  CHECK(doc.blocks[0].type == BlockType::Title && doc.blocks[0].level == 1);
  CHECK_EQ(doc.blocks[0].text, std::string("Chapter One"));
  CHECK_EQ(doc.blocks[1].text, std::string("The first paragraph of this book has many words to fill several lines, "
                                           "and this one ends with a population broken by hyphenation."));
  CHECK_EQ(doc.blocks[2].text,
           std::string("A second paragraph begins here, and its final line on the first page is full, and so the text "
                       "runs on to the next page; the next line carries on with no break. A compound word broken at "
                       "its hyphen: self-made keeps the hyphen in the joined text of lines. That is all."));
  CHECK_EQ(doc.blocks[3].text, std::string("\xE2\x80\xA2 first item"));
  CHECK_EQ(doc.blocks[4].text, std::string("\xE2\x80\xA2 second item"));
  CHECK_EQ(doc.toc.size(), size_t(2));
  if (doc.toc.size() == 2) {
    CHECK(doc.toc[0].title == "Chapter One" && doc.toc[0].block == 0 && doc.toc[0].level == 1);
    CHECK(doc.toc[1].title == "Page two" && doc.toc[1].level == 2);
  }
}

// Cross-reference stream (PNG "Up" predictor), an object stream, compressed content and a composite font
// (Identity-H) whose ToUnicode map uses bfrange and bfchar. With indirectXrefLength the cross-reference stream's
// /Length is a reference (to object 10).
static std::string pdfCompressed(bool indirectXrefLength = false) {
  const std::string o4 = "<< /Type /Font /Subtype /Type0 /BaseFont /CidTest /Encoding /Identity-H "
                         "/DescendantFonts [5 0 R] /ToUnicode 6 0 R >>";
  const std::string o5 = "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /CidTest /DW 1000 /W [1 [500 500 500] 4 4 250] >>";
  const std::string cmap =
      "/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <0000> <FFFF> "
      "endcodespacerange 1 beginbfrange <0001> <0003> <0041> endbfrange 1 beginbfchar <0004> <0020> endbfchar "
      "endcmap end end";
  const std::string content = deflateBytes("BT /F1 12 Tf 30 250 Td <000100020003000400010002> Tj ET");
  const std::string hdr = "4 0 5 " + std::to_string(o4.size() + 1) + " ";
  const std::string objStm = deflateBytes(hdr + o4 + " " + o5);
  std::string out = "%PDF-1.5\n";
  std::vector<size_t> off(10, 0);
  auto put = [&](int n, const std::string& body) {
    off[static_cast<size_t>(n)] = out.size();
    out += std::to_string(n) + " 0 obj\n" + body + "\nendobj\n";
  };
  put(1, "<< /Type /Catalog /Pages 2 0 R >>");
  put(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  put(3, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>");
  put(6, PdfBuilder::stream("", cmap));
  put(7, PdfBuilder::stream("/Filter /FlateDecode", content));
  put(8, PdfBuilder::stream("/Type /ObjStm /N 2 /First " + std::to_string(hdr.size()) + " /Filter /FlateDecode", objStm));
  // Object 10: the length of the cross-reference stream, ten digits filled in when it is known.
  size_t lengthAt = 0;
  if (indirectXrefLength) {
    off.resize(11, 0);
    off[10] = out.size();
    out += "10 0 obj\n";
    lengthAt = out.size();
    out += "0000000000\nendobj\n";
  }
  // Cross-reference stream: type (1 byte), offset or object stream (4 bytes), generation or index (2 bytes).
  const size_t xrefOff = out.size();
  std::string rows, prev(7, '\0');
  auto row = [&](int type, uint32_t f1, uint16_t f2) {
    std::string r(7, '\0');
    r[0] = static_cast<char>(type);
    for (int k = 0; k < 4; ++k) r[1 + static_cast<size_t>(k)] = static_cast<char>((f1 >> (24 - 8 * k)) & 0xFF);
    r[5] = static_cast<char>(f2 >> 8);
    r[6] = static_cast<char>(f2 & 0xFF);
    rows += '\x02';  // PNG "Up"
    for (size_t k = 0; k < 7; ++k)
      rows += static_cast<char>(static_cast<unsigned char>(r[k]) - static_cast<unsigned char>(prev[k]));
    prev = r;
  };
  row(0, 0, 0xFFFF);
  for (int n = 1; n <= 3; ++n) row(1, static_cast<uint32_t>(off[static_cast<size_t>(n)]), 0);
  row(2, 8, 0);
  row(2, 8, 1);
  for (int n = 6; n <= 8; ++n) row(1, static_cast<uint32_t>(off[static_cast<size_t>(n)]), 0);
  row(1, static_cast<uint32_t>(xrefOff), 0);
  if (indirectXrefLength) row(1, static_cast<uint32_t>(off[10]), 0);
  const std::string xrefData = deflateBytes(rows);
  const std::string xrefDict = std::string("/Type /XRef /Size ") + (indirectXrefLength ? "11" : "10") +
                               " /W [1 4 2] /Root 1 0 R /Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 7 >>";
  if (indirectXrefLength) {
    char digits[16];
    std::snprintf(digits, sizeof(digits), "%010zu", xrefData.size());
    out.replace(lengthAt, 10, digits);
    out += "9 0 obj\n<< " + xrefDict + " /Length 10 0 R >>\nstream\n" + xrefData + "\nendstream\nendobj\n";
  } else {
    put(9, PdfBuilder::stream(xrefDict, xrefData));
  }
  out += "startxref\n" + std::to_string(xrefOff) + "\n%%EOF\n";
  return out;
}

// One page with a picture (2x2 RGB, compressed) above a line of text.
static std::string pdfWithImage() {
  PdfBuilder b;
  const int catalog = b.add("<< /Type /Catalog /Pages 2 0 R >>");
  b.add("<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  b.add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R >> "
        "/XObject << /Im1 6 0 R >> >> /Contents 4 0 R >>");
  b.add(PdfBuilder::stream("", "q 200 0 0 150 50 120 cm /Im1 Do Q BT /F1 10 Tf 20 60 Td (A picture above.) Tj ET"));
  b.add(testFont("TestSerif"));
  const std::string px("\xFF\x00\x00\x00\xFF\x00\x00\x00\xFF\xFF\xFF\xFF", 12);  // red green / blue white
  b.add(PdfBuilder::stream("/Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB "
                           "/BitsPerComponent 8 /Filter /FlateDecode",
                           deflateBytes(px)));
  return b.build(catalog);
}

// A page encrypted by the standard security handler with an empty user password.
// kind: 0 = RC4 40-bit (revision 2), 1 = AES-128 (revision 4), 2 = AES-256 (revision 5). With identityContent the
// page's content stream is stored unencrypted, marked with the Identity crypt filter.
static std::string pdfEncrypted(int kind, bool identityContent = false) {
  const std::string pad = fromHex("28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a");
  const std::string id0 = fromHex("0123456789abcdef0123456789abcdef");
  const std::string pbytes = fromHex("fcffffff");  // P = -4, little-endian
  std::string key, encDict;
  auto xorKey = [](std::string k, int v) {
    for (char& c : k) c = static_cast<char>(static_cast<unsigned char>(c) ^ v);
    return k;
  };
  if (kind == 0 || kind == 1) {
    const size_t n = kind == 0 ? 5 : 16;
    // Algorithm 3 (owner password "owner"): O encrypts the (empty) user password.
    std::string h = pdf::md5("owner" + pad.substr(0, 27));
    if (kind == 1) {
      for (int k = 0; k < 50; ++k) h = pdf::md5(h.substr(0, n));
    }
    std::string o = pdf::rc4(h.substr(0, n), pad);
    if (kind == 1) {
      for (int k = 1; k <= 19; ++k) o = pdf::rc4(xorKey(h.substr(0, n), k), o);
    }
    // Algorithm 2: the file key; then U (algorithm 4 or 5).
    std::string fh = pdf::md5(pad + o + pbytes + id0);
    if (kind == 1) {
      for (int k = 0; k < 50; ++k) fh = pdf::md5(fh.substr(0, n));
    }
    key = fh.substr(0, n);
    std::string u;
    if (kind == 0) {
      u = pdf::rc4(key, pad);
    } else {
      u = pdf::rc4(key, pdf::md5(pad + id0));
      for (int k = 1; k <= 19; ++k) u = pdf::rc4(xorKey(key, k), u);
      u += std::string(16, '\0');
    }
    encDict = kind == 0 ? "<< /Filter /Standard /V 1 /R 2 /O <" + toHex(o) + "> /U <" + toHex(u) + "> /P -4 >>"
                        : "<< /Filter /Standard /V 4 /R 4 /Length 128 /CF << /StdCF << /CFM /AESV2 /Length 16 >> >> "
                          "/StmF /StdCF /StrF /StdCF /O <" +
                              toHex(o) + "> /U <" + toHex(u) + "> /P -4 >>";
  } else {
    key = fromHex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff");
    const std::string vsalt = "vsalt123", ksalt = "ksalt456";
    const std::string u = pdf::sha256(vsalt) + vsalt + ksalt;
    const std::string ue = pdf::aesCbcEncrypt(pdf::sha256(ksalt), std::string(16, '\0'), key);
    encDict = "<< /Filter /Standard /V 5 /R 5 /Length 256 /CF << /StdCF << /CFM /AESV3 /Length 32 >> >> /StmF /StdCF "
              "/StrF /StdCF /O <" + toHex(std::string(48, '\x11')) + "> /U <" + toHex(u) + "> /OE <" +
              toHex(std::string(32, '\x22')) + "> /UE <" + toHex(ue) + "> /P -4 >>";
  }
  auto aes = [](const std::string& k, const std::string& iv, std::string data) {
    const size_t padN = 16 - data.size() % 16;
    data.append(padN, static_cast<char>(padN));
    return iv + pdf::aesCbcEncrypt(k, iv, data);
  };
  auto encrypt = [&](const std::string& data, int num) {
    if (kind == 2) return aes(key, "0123456789ABCDEF", data);
    std::string k = key;
    k += static_cast<char>(num & 0xFF);
    k += std::string("\0\0\0\0", 4);  // the rest of the 3-byte object number and the 2-byte generation (all zero)
    if (kind == 1) k += "sAlT";
    const std::string objKey = pdf::md5(k).substr(0, std::min<size_t>(key.size() + 5, 16));
    return kind == 0 ? pdf::rc4(objKey, data) : aes(objKey, "FEDCBA9876543210", data);
  };
  PdfBuilder b;
  const int catalog = b.add("<< /Type /Catalog /Pages 2 0 R >>");
  b.add("<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> >>");
  b.add("<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>");
  const std::string content = "BT /F1 16 Tf 20 350 Td (Secret Chapter) Tj ET "
                              "BT /F1 10 Tf 20 320 Td (Only readers with the key can see this line.) Tj ET";
  if (identityContent) {
    b.add(PdfBuilder::stream("/Filter [/Crypt] /DecodeParms [<< /Name /Identity >>]", content));
  } else {
    b.add(PdfBuilder::stream("", encrypt(content, 4)));
  }
  b.add(testFont("TestSerif"));
  b.add("<< /Title <" + toHex(encrypt("Locked Book", 6)) + "> >>");
  b.add(encDict);
  return b.build(catalog, "/Info 6 0 R /Encrypt 7 0 R /ID [<" + toHex(id0) + "> <" + toHex(id0) + ">]");
}

// Content that breaks the rules: a form with an unclosed artifact and more Q than q, and a ToUnicode map with a bfrange
// onto an array (more entries after it in the same block) and a range that ends at <FFFFFFFF>.
static std::string pdfDamagedContent() {
  PdfBuilder b;
  const int catalog = b.add("<< /Type /Catalog /Pages 2 0 R >>");
  b.add("<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  b.add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R /F2 8 0 R >> "
        "/XObject << /Fm1 7 0 R >> >> /Contents 4 0 R >>");
  b.add(PdfBuilder::stream("", "q /Fm1 Do Q BT /F1 12 Tf 30 250 Td <000100020003000400050006> Tj ET "
                               "BT /F2 12 Tf 30 200 Td (after the form) Tj ET"));
  b.add("<< /Type /Font /Subtype /Type0 /BaseFont /CidTest /Encoding /Identity-H /DescendantFonts [<< /Type /Font "
        "/Subtype /CIDFontType2 /BaseFont /CidTest /DW 500 >>] /ToUnicode 6 0 R >>");
  b.add(PdfBuilder::stream("", "begincmap 1 begincodespacerange <0000> <FFFF> endcodespacerange 3 beginbfrange "
                               "<0001> <0003> [<0041> <0042> <0043>] <0004> <0004> <0020> <0005> <0006> <0058> "
                               "endbfrange 1 beginbfrange <FFFFFF00> <FFFFFFFF> <0041> endbfrange endcmap"));
  b.add(PdfBuilder::stream("/Type /XObject /Subtype /Form /BBox [0 0 300 300]", "/Artifact BMC q Q Q Q"));
  b.add(testFont("TestSans"));
  return b.build(catalog);
}

// Two tables of evenly spaced lines, a page each: one with a row per line (values in lower case), one whose single row
// goes on over two lines.
static std::string pdfTable() {
  PdfBuilder b;
  const int catalog = b.add("<< /Type /Catalog /Pages 2 0 R >>");
  b.add("<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> >>");
  b.add("<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>");
  b.add("<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>");
  b.add(PdfBuilder::stream("", "BT /F1 10 Tf 30 250 Td (Name) Tj 120 0 Td (Value) Tj ET "
                               "BT /F1 10 Tf 30 236 Td (alpha) Tj 120 0 Td (red) Tj ET "
                               "BT /F1 10 Tf 30 222 Td (beta) Tj 120 0 Td (dark green) Tj ET"));
  b.add(PdfBuilder::stream("", "BT /F1 10 Tf 30 250 Td (Customer) Tj 120 0 Td (Rider request and pickup) Tj ET "
                               "BT /F1 10 Tf 30 236 Td (Journey) Tj 120 0 Td (continue the trust.) Tj ET"));
  b.add(testFont("TestSans"));
  return b.build(catalog);
}

static void testPdf() {
  // Hashes and ciphers (RFC 1321, FIPS 180-4 and FIPS 197 vectors; the long messages checked with Python's hashlib).
  CHECK_EQ(toHex(pdf::md5("abc")), std::string("900150983cd24fb0d6963f7d28e17f72"));
  CHECK_EQ(toHex(pdf::md5(std::string(1000, 'a'))), std::string("cabe45dcc9ae5b66ba86600cca6b8ba8"));
  CHECK_EQ(toHex(pdf::sha256("abc")), std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
  CHECK_EQ(toHex(pdf::sha256(std::string(1000, 'a'))),
           std::string("41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3"));
  CHECK_EQ(toHex(pdf::sha384("abc")), std::string("cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed"
                                                  "8086072ba1e7cc2358baeca134c825a7"));
  CHECK_EQ(toHex(pdf::sha512(std::string(1000, 'a'))),
           std::string("67ba5535a46e3f86dbfbed8cbbaf0125c76ed549ff8b0b9e03e0c88cf90fa634fa7b12b47d77b694de488ace8d9a6596"
                       "7dc96df599727d3292a8d9d447709c97"));
  CHECK_EQ(toHex(pdf::rc4("Key", "Plaintext")), std::string("bbf316e8d940af0ad3"));
  const std::string block = fromHex("00112233445566778899aabbccddeeff"), zero(16, '\0');
  CHECK_EQ(toHex(pdf::aesCbcEncrypt(fromHex("000102030405060708090a0b0c0d0e0f"), zero, block)),
           std::string("69c4e0d86a7b0430d8cdb78070b4c55a"));
  const std::string k256 = fromHex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f");
  CHECK_EQ(toHex(pdf::aesCbcEncrypt(k256, zero, block)), std::string("8ea2b7ca516745bfeafc49904b496089"));
  CHECK_EQ(pdf::aesCbcDecrypt(k256, zero, fromHex("8ea2b7ca516745bfeafc49904b496089")), block);

  // Lexer.
  {
    pdf::Lexer lx("<< /Na#20me (a\\(b\\)c\\101\\\n) /Hex <48 65 6C6> /Arr [-.5 4. --3 7 0 R (x)] /K true /N null >>");
    pdf::Object o;
    CHECK(lx.object(o) && o.isDict());
    CHECK_EQ(o["Na me"].s, std::string("a(b)cA"));
    CHECK_EQ(o["Hex"].s, std::string("Hel`"));
    const pdf::Object& arr = o["Arr"];
    CHECK(arr.size() == 5 && arr.at(0).num() == -0.5 && arr.at(1).num() == 4.0 && arr.at(2).integer() == -3);
    CHECK(arr.at(3).isRef() && arr.at(3).i == 7 && arr.at(4).s == "x");
    CHECK(o["K"].type == pdf::ObjType::Bool && o["K"].flag && o["N"].isNull());
  }
  // Filters.
  {
    std::string out;
    pdf::FilterParams p;
    CHECK(pdf::applyFilter("FlateDecode", p, deflateBytes("Hello, PDF!"), out, 1 << 20) && out == "Hello, PDF!");
    std::string big(100000, 'x');
    for (size_t k = 0; k < big.size(); k += 7) big[k] = static_cast<char>('a' + k % 26);
    CHECK(pdf::applyFilter("Fl", p, deflateBytes(big), out, 1 << 20) && out == big);  // output over many windows
    CHECK(pdf::applyFilter("ASCIIHexDecode", p, "48 65 6c 6C6F7>", out, 100) && out == "Hellop");
    CHECK(pdf::applyFilter("ASCII85Decode", p, "<~9jqo^~>", out, 100) && out == "Man ");
    CHECK(pdf::applyFilter("RunLengthDecode", p, std::string("\x02" "abc" "\xFE" "z" "\x80", 7), out, 100) &&
          out == "abczzz");
    // LZW: the example in PDF 32000-1, 7.4.4.2.
    CHECK(pdf::applyFilter("LZWDecode", p, fromHex("800b6050220c0c8501"), out, 100) && out == "-----A---B");
    pdf::FilterParams png;
    png.predictor = 12;
    png.columns = 3;
    const std::string rows = std::string("\x00" "abc", 4) + std::string("\x02\x01\x01\x01", 4);  // None, then Up
    CHECK(pdf::applyFilter("FlateDecode", png, deflateBytes(rows), out, 100) && out == "abcbcd");
    // A predictor row longer than the whole stream (damaged parameters) never makes the output larger than the input.
    pdf::FilterParams wide = png;
    wide.columns = 1 << 24;
    CHECK(pdf::applyFilter("FlateDecode", wide, deflateBytes(rows), out, 1 << 30) && out.size() <= rows.size());
    CHECK(!pdf::applyFilter("DCTDecode", p, "x", out, 100));
  }
  // Text strings and glyph names.
  CHECK_EQ(pdf::textToUtf8("\x93" "fi" "\x94" "ne"), std::string("\xEF\xAC\x81" "fi\xEF\xAC\x82" "ne"));
  CHECK_EQ(pdf::textToUtf8(std::string("\xFE\xFF\x04\x1F\x04\x40\x00\x20\x00\x21", 10)),
           std::string("\xD0\x9F\xD1\x80 !"));
  CHECK_EQ(pdf::glyphNameToUtf8("afii10017"), std::string("\xD0\x90"));
  CHECK_EQ(pdf::glyphNameToUtf8("f_f_i"), std::string("ffi"));
  CHECK_EQ(pdf::glyphNameToUtf8("uni0416.sc"), std::string("\xD0\x96"));
  CHECK_EQ(pdf::glyphNameToUtf8("g123"), std::string());

  // A book.
  Document doc;
  std::string err;
  const std::string book = pdfTestBook();
  CHECK(looksLikePdf(book));
  CHECK(parsePdf(book, doc, "stem", &err));
  checkTestBook(doc);
  // The same book with every cross-reference offset wrong: the objects are found by scanning.
  Document repaired;
  CHECK(parsePdf(pdfTestBook(3), repaired, "stem", &err));
  checkTestBook(repaired);
  // Metadata from the first and the last bytes only.
  BookMeta meta;
  CHECK(parsePdfMeta(std::string_view(book).substr(0, 64), std::string_view(book).substr(book.size() / 3),
                     book.size(), meta) &&
        meta.title == "Test Book");
  // Text for full-text search.
  std::string text;
  pdfExtractText(book, text, &meta, "stem");
  CHECK(text.find("a population broken") != std::string::npos && meta.authorsJoined() == "Jane Doe");

  // Cross-reference stream, object stream, composite font; title and author from the file name.
  Document c;
  CHECK(parsePdf(pdfCompressed(), c, "Author - Compressed Title", &err));
  CHECK(c.blocks.size() == 1 && c.blocks[0].text == "ABC AB");
  CHECK(c.meta.title == "Compressed Title" && c.meta.authorsJoined() == "Author");
  // The same with an indirect /Length in the cross-reference stream: read without a repair. A File opens a second
  // file as if it were new.
  {
    const std::string indirect = pdfCompressed(true);
    pdf::File f;
    CHECK(f.open(indirect, &err) && !f.repaired() && f.version() == "1.5");
    CHECK(f.open(book, &err) && !f.repaired() && f.version() == "1.4");
    Document ci;
    CHECK(parsePdf(indirect, ci, "stem", &err) && ci.blocks.size() == 1 && ci.blocks[0].text == "ABC AB");
  }

  // A picture: stored still compressed, decoded when shown.
  Document im;
  CHECK(parsePdf(pdfWithImage(), im, "stem", &err));
  CHECK(im.blocks.size() == 2 && im.blocks[0].type == BlockType::Image && im.blocks[1].text == "A picture above.");
  CHECK_EQ(im.images.size(), size_t(1));
  if (!im.images.empty()) {
    const ImageData& id = im.images[0];
    CHECK(id.width == 2 && id.height == 2);
    std::vector<unsigned char> rgba;
    int w = 0, h = 0;
    CHECK(decodeImageRgba(id.bytes.data(), id.bytes.size(), rgba, w, h) && w == 2 && h == 2);
    CHECK(rgba.size() == 16 && rgba[0] == 255 && rgba[1] == 0 && rgba[5] == 255 && rgba[10] == 255 && rgba[12] == 255);
  }

  // Encrypted files that open without a password.
  int opened = 0;
  for (int kind = 0; kind < 3; ++kind) {
    Document e;
    const bool ok = parsePdf(pdfEncrypted(kind), e, "stem", &err);
    CHECK(ok);
    CHECK(e.blocks.size() == 2 && e.blocks[0].text == "Secret Chapter" &&
          e.blocks[1].text == "Only readers with the key can see this line.");
    CHECK_EQ(e.meta.title, std::string("Locked Book"));
    opened += ok ? 1 : 0;
  }
  // A stream an encrypted file keeps in the clear (the Identity crypt filter).
  Document clear;
  CHECK(parsePdf(pdfEncrypted(1, true), clear, "stem", &err) && clear.blocks.size() == 2 &&
        clear.blocks[0].text == "Secret Chapter");
  // Content that breaks the rules does not break the page.
  Document dc;
  CHECK(parsePdf(pdfDamagedContent(), dc, "stem", &err));
  CHECK(dc.blocks.size() == 2 && dc.blocks[0].text == "ABC XY" && dc.blocks[1].text == "after the form");
  // Tables of evenly spaced lines: a row per line, and a row whose cells go on over two lines.
  Document tb;
  CHECK(parsePdf(pdfTable(), tb, "stem", &err));
  CHECK(tb.blocks.size() == 4 && tb.blocks[0].type == BlockType::TableRow && tb.blocks[0].text == "Name | Value" &&
        tb.blocks[1].text == "alpha | red" && tb.blocks[2].text == "beta | dark green" &&
        tb.blocks[3].text == "Customer Journey | Rider request and pickup continue the trust.");
  // Not a PDF that can be read.
  Document bad;
  CHECK(!parsePdf("%PDF-1.4\ngarbage", bad, "stem", &err) && !err.empty());
  std::printf("  pdf: %zu blocks, %zu contents entries, repaired %zu blocks, encrypted files opened %d of 3\n",
              doc.blocks.size(), doc.toc.size(), repaired.blocks.size(), opened);
}

int main(int argc, char** argv) {
  if (argc > 1) g_assets = argv[1];
  HyphenationService hs;
  std::printf("unicode\n");
  testUnicode();
  std::printf("encodings\n");
  testEncodings();
  std::printf("xml\n");
  testXml();
  std::printf("fb2\n");
  testFb2();
  std::printf("txt\n");
  testTxt();
  testTxtTypography();
  std::printf("pdf\n");
  testPdf();
  std::printf("hyphenation\n");
  testHyphenation(hs);
  std::printf("line breaking\n");
  testLineBreaker();
  std::printf("matching\n");
  testMatching();
  std::printf("web addresses\n");
  testWebAddresses();
  std::printf("library search\n");
  testLibrarySearch();
#ifdef LL_TESTS_WITH_TEXT
  std::printf("text layout\n");
  testTextLayout(hs);
#endif
  std::printf("%d checks, %d failures\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
```
