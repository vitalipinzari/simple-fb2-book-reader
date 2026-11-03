# Unit tests

The whole unit test program. The re-created code must compile against it unchanged and pass every check.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `tests/core_tests.cpp` | 38416 | `04c3bc957aee1a6f…` |

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
#include "core/LibrarySearch.h"
#include "core/LineBreaker.h"
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
