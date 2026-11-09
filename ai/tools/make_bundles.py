#!/usr/bin/env python3
"""Regenerates ai/files/: the files of the Lanternleaf repository that the regeneration prompts carry verbatim.

    python -I ai/tools/make_bundles.py [repository-root]

Without an argument it works on the repository that contains this script. It writes

    ai/files/01-build-system.md ... 05-docs-assets-tools.md   every verbatim file, in fenced blocks
    ai/files/checksums.sha256                                 SHA-256 of every verbatim file and asset

and warns about repository files that no bundle, no spec and no list below accounts for, so new files are not
forgotten when the prompts are refreshed for a later version. Standard library only (Python 3.8+).

The regenerated application is published under the MIT License. Since 0.7.0 the repository itself is the MIT
edition, so LICENSE_EDITS and NEW_FILES are empty; they remain for a source tree whose files must be edited (or
added) before they are published: the bundles then carry the edited text and the checksums are those of the
edited files.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
OUT = ROOT / "ai" / "files"

MIT_LICENSE = """MIT License

Copyright (c) 2026 Vitali Pinzari

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# (file, old text, new text): every occurrence is replaced; each edit must apply at least once.
LICENSE_EDITS = []
# Files that exist only in the MIT edition of the repository (the repository has its own LICENSE since 0.7.0;
# it must equal MIT_LICENSE, which main() checks).
NEW_FILES = {}

BUNDLES = [
    ("01-build-system.md", "Build system, version, licence, build scripts and installer",
     "The root of the repository: the version file, the MIT licence, CMake (also used by the Android build through "
     "Gradle), the vcpkg manifest, the CMake helper modules, the Windows resource and version templates, the three "
     "PowerShell build scripts, and the WiX source of the Windows installer with its licence page.",
     ["VERSION", "LICENSE", ".gitignore", "CMakeLists.txt", "CMakePresets.json", "vcpkg.json",
      "cmake/HarfBuzzAmalgamated.cmake", "cmake/StageRelease.cmake", "res/lanternleaf.rc.in", "src/app/Version.h.in",
      "build.ps1", "build-android.ps1", "build-msi.ps1", "installer/Lanternleaf.wxs", "installer/License.rtf"]),
    ("02-source-interfaces.md", "Source: every header, the entry point and the platform, theme and settings code",
     "Every header of the code base (the interfaces the specifications in ai/spec implement), the entry point, and "
     "the three .cpp files that are data or operating-system glue rather than algorithms: the colour themes, the "
     "settings file format and the platform layer. The other .cpp files are specified in ai/spec/03-10 and 15.",
     ["src/main.cpp",
      "src/core/Unicode.h", "src/core/Encoding.h", "src/core/XmlReader.h", "src/core/Document.h",
      "src/core/FileUtil.h", "src/core/ImageCodec.h", "src/core/Fb2Parser.h", "src/core/TxtParser.h",
      "src/core/PdfReader.h", "src/core/PdfCrypt.h", "src/core/PdfContent.h", "src/core/PdfParser.h",
      "src/core/BookLoader.h", "src/core/Hyphenator.h", "src/core/LineBreaker.h", "src/core/LibrarySearch.h",
      "src/text/FontLibrary.h", "src/text/Shaper.h", "src/text/BookLayout.h",
      "src/render/Gl.h", "src/render/GlCommon.h", "src/render/GlyphAtlas.h", "src/render/Renderer2D.h",
      "src/render/PageTurn.h",
      "src/platform/Platform.h", "src/platform/Platform.cpp",
      "src/app/Themes.h", "src/app/Themes.cpp", "src/app/Settings.h", "src/app/Settings.cpp",
      "src/app/UiHelpers.h", "src/app/App.h"]),
    ("03-android-project.md", "Android project (Gradle, manifest, resources, Java)",
     "The Gradle project in android/. The SDL Java glue in android/app/src/main/java/org/libsdl/app/ is not listed: "
     "it is the unmodified android-project/app/src/main/java/org/libsdl/app/ folder of SDL 3.4.18 (see "
     "ai/spec/11-platform-and-android.md); only the licence file that sits next to it is listed here. The launcher "
     "PNGs come from tools/make_icon.py, the Gradle wrapper (gradlew, gradlew.bat, gradle-wrapper.jar) from "
     "`gradle wrapper`.",
     ["android/settings.gradle", "android/build.gradle", "android/gradle.properties",
      "android/gradle/wrapper/gradle-wrapper.properties", "android/app/build.gradle",
      "android/app/src/main/AndroidManifest.xml", "android/app/src/main/res/values/colors.xml",
      "android/app/src/main/res/values/strings.xml", "android/app/src/main/res/values/styles.xml",
      "android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml",
      "android/app/src/main/java/app/lanternleaf/reader/LanternleafActivity.java",
      "android/app/src/main/java/app/lanternleaf/reader/LanternleafSurface.java",
      "android/app/src/main/java/org/libsdl/app/LICENSE.txt"]),
    ("04-tests.md", "Unit tests",
     "The whole unit test program. The re-created code must compile against it unchanged and pass every check.",
     ["tests/core_tests.cpp"]),
    ("05-docs-assets-tools.md", "Documentation, project workflow files, asset texts and the icon generator",
     "The README (MIT edition), the original build prompt, the change list, the bug and feature backlog files, the "
     "texts that ship in assets/ (hyphenation notes and the third-party notices shown in the About panel) and the "
     "icon generator.",
     ["README.md", "PROMPT.md", "CHANGELIST.md", "bugs/prompt.md", "bugs/report.md", "features/prompt.md",
      "features/features.md", "assets/hyphenation/README.md", "assets/licenses/THIRD-PARTY-NOTICES.txt",
      "tools/make_icon.py"]),
]

# Binary or downloaded files: not bundled, but their checksums are listed (they are described in ai/spec/12).
ASSET_GLOBS = ["assets/fonts/*", "assets/hyphenation/*.txt", "res/lanternleaf.ico", "res/lanternleaf.png",
               "android/app/src/main/res/mipmap-*/*.png"]

# .cpp files whose implementation is specified (not reproduced) in ai/spec.
SPECIFIED = {
    "src/core/Unicode.cpp": "03", "src/core/Encoding.cpp": "03", "src/core/XmlReader.cpp": "03",
    "src/core/Document.cpp": "03", "src/core/FileUtil.cpp": "03", "src/core/ImageCodec.cpp": "03",
    "src/core/Fb2Parser.cpp": "04", "src/core/TxtParser.cpp": "04", "src/core/BookLoader.cpp": "04",
    "src/core/Hyphenator.cpp": "05", "src/core/LineBreaker.cpp": "05", "src/core/LibrarySearch.cpp": "06",
    "src/text/FontLibrary.cpp": "07", "src/text/Shaper.cpp": "07", "src/text/BookLayout.cpp": "07",
    "src/render/GlCommon.cpp": "08", "src/render/GlyphAtlas.cpp": "08", "src/render/Renderer2D.cpp": "08",
    "src/render/PageTurn.cpp": "08", "src/app/App.cpp": "09", "src/app/AppUi.cpp": "10",
    "src/app/FileBrowser.cpp": "10",
    "src/core/PdfReader.cpp": "15", "src/core/PdfCrypt.cpp": "15", "src/core/PdfContent.cpp": "15",
    "src/core/PdfParser.cpp": "15",
}
# Accounted for elsewhere (generated, downloaded, secret or machine-specific).
OTHER = [r"^android/app/src/main/java/org/libsdl/app/.*\.java$", r"^android/gradlew(\.bat)?$",
         r"^android/gradle/wrapper/gradle-wrapper\.jar$", r"^android/local\.properties$",
         r"^android/keystore\.properties$", r"^android/keystore/", r"^docs/.*\.png$"]
IGNORED_DIRS = {"ai", "build", "release", "books", ".git", ".vs", ".vscode", "out", ".gradle", ".idea", ".cxx",
                ".kotlin"}

LANG = {".h": "cpp", ".cpp": "cpp", ".in": "", ".cmake": "cmake", ".json": "json", ".ps1": "powershell",
        ".gradle": "groovy", ".properties": "properties", ".xml": "xml", ".java": "java", ".py": "python",
        ".md": "markdown", ".txt": "text"}


def content_of(rel: str) -> bytes:
    if rel in NEW_FILES:
        return NEW_FILES[rel].encode("utf-8")
    data = (ROOT / rel).read_bytes()
    edits = [(old, new) for f, old, new in LICENSE_EDITS if f == rel]
    if edits:
        text = data.decode("utf-8")
        for old, new in edits:
            if old not in text:
                sys.exit(f"error: licence edit for {rel} no longer applies: {old!r}")
            text = text.replace(old, new)
        data = text.encode("utf-8")
    return data


def describe(data: bytes) -> str:
    """Encoding, line endings and the final newline: what a fenced block cannot show."""
    parts = []
    if data.startswith(b"\xef\xbb\xbf"):
        parts.append("UTF-8 with BOM")
    else:
        try:
            data.decode("ascii")
            parts.append("ASCII")
        except UnicodeDecodeError:
            parts.append("UTF-8 without BOM")
    lines = data.split(b"\n")
    crlf = [i + 1 for i, line in enumerate(lines[:-1]) if line.endswith(b"\r")]
    lf = [i + 1 for i, line in enumerate(lines[:-1]) if not line.endswith(b"\r")]
    if crlf and lf:
        if len(lf) <= 5:
            parts.append(f"CRLF line endings except LF after line {', '.join(map(str, lf))}")
        else:
            parts.append(f"LF line endings except CRLF after line {', '.join(map(str, crlf))}")
    elif crlf:
        parts.append("CRLF line endings")
    elif lf:
        parts.append("LF line endings")
    parts.append("ends with a newline" if data.endswith(b"\n") else "no newline at the end")
    if b"\t" in data:
        parts.append("contains tabs")
    return ", ".join(parts)


def fence_for(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def language(rel: str) -> str:
    name = Path(rel).name
    if name == "CMakeLists.txt":
        return "cmake"
    if name.endswith(".rc.in"):
        return "c"
    if name.endswith(".h.in"):
        return "cpp"
    return LANG.get(Path(rel).suffix, "text")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_bundle(name, title, intro, files, sums):
    out = [f"# {title}", "",
           intro, "",
           "Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the "
           "complete content (the fences are not part of the file); the line under each heading gives what a block "
           "cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` "
           "has the SHA-256 of each file for checking.", "",
           "| File | Bytes | SHA-256 |", "|---|---:|---|"]
    blobs = []
    for rel in files:
        data = content_of(rel)
        sums.append((sha256(data), rel))
        out.append(f"| `{rel}` | {len(data)} | `{sha256(data)[:16]}…` |")
        blobs.append((rel, data))
    out.append("")
    for rel, data in blobs:
        text = data.decode("utf-8-sig").replace("\r\n", "\n")
        fence = fence_for(text)
        out += [f"## `{rel}`", "", describe(data) + ".", "", fence + language(rel),
                text + ("" if text.endswith("\n") else "\n") + fence, ""]
    (OUT / name).write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"wrote {OUT / name} ({len(files)} files)")


def repository_files():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in IGNORED_DIRS or any(part in IGNORED_DIRS for part in rel.split("/")[:-1]):
            continue
        yield rel


def main():
    if "LICENSE" not in NEW_FILES and (ROOT / "LICENSE").read_text(encoding="utf-8") != MIT_LICENSE:
        sys.exit("error: LICENSE is not the MIT licence text of MIT_LICENSE")
    OUT.mkdir(parents=True, exist_ok=True)
    sums = []
    bundled = set()
    for name, title, intro, files in BUNDLES:
        write_bundle(name, title, intro, files, sums)
        bundled.update(files)
    assets = []
    for pattern in ASSET_GLOBS:
        for p in sorted(ROOT.glob(pattern)):
            rel = p.relative_to(ROOT).as_posix()
            if rel not in bundled:
                assets.append((sha256(p.read_bytes()), rel))
    lines = ["# SHA-256 of the files of Lanternleaf (MIT edition) that the prompts reproduce exactly.",
             "# Verbatim files (ai/files/*.md):"]
    lines += [f"{h}  {rel}" for h, rel in sums]
    lines += ["# Assets and icons (ai/spec/12-assets-and-icons.md):"]
    lines += [f"{h}  {rel}" for h, rel in assets]
    (OUT / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT / 'checksums.sha256'} ({len(sums) + len(assets)} files)")

    covered = bundled | set(SPECIFIED) | {rel for _, rel in assets}
    missing = [rel for rel in repository_files()
               if rel not in covered and not any(re.search(rx, rel) for rx in OTHER)]
    for rel in missing:
        print(f"warning: {rel} is in no bundle, spec or list: add it to make_bundles.py")
    specs = ROOT / "ai" / "spec"
    for rel, num in SPECIFIED.items():
        if not (ROOT / rel).exists():
            print(f"warning: {rel} (specified in ai/spec/{num}-*.md) no longer exists")
    for num in sorted(set(SPECIFIED.values())):
        if not list(specs.glob(f"{num}-*.md")):
            files = ", ".join(rel for rel, n in SPECIFIED.items() if n == num)
            print(f"warning: ai/spec/{num}-*.md is missing (it specifies {files})")


if __name__ == "__main__":
    main()
