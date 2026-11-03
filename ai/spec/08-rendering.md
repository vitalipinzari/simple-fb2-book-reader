# 08 — Rendering: GL helpers, glyph atlas, 2D batch renderer, 3D page turn

This file specifies the four implementation files of `src/render/`. `GlCommon.cpp` covers colour packing, the 4×4 matrix, shader compilation, textures, render targets and the GL version string. `GlyphAtlas.cpp` rasterises glyphs with FreeType on demand into one R8 texture, using shelf packing and four horizontal sub-pixel positions. `Renderer2D.cpp` is the batched textured-quad renderer that draws every glyph, rule, rectangle, gradient and picture. `PageTurn.cpp` is the 3D page curl, for a single page and for a two-page spread. The headers `render/Gl.h`, `render/GlCommon.h`, `render/GlyphAtlas.h`, `render/Renderer2D.h`, `render/PageTurn.h`, `text/FontLibrary.h` and `text/Shaper.h` are reproduced verbatim elsewhere. This file refers to their declarations by name and does not repeat them. The only client is `App` (specified in `09-application.md`); section 5 states only the contracts that `App` relies on. None of the four files logs anything or calls `glGetError`.

---

## 0. Conventions shared by the four files

- **Namespaces and layout.** Everything is in `namespace ll`. The GL helpers (`shaderSource`, `compileProgram`, `Texture`, `RenderTarget`, `glVersionString`) are defined in a `namespace gl { … }` block nested inside `namespace ll`. File-local constants, helpers and shader strings live in an anonymous namespace. In `GlCommon.cpp` that anonymous namespace holds only `compileStage`; it sits inside `namespace gl`, between `shaderSource` and `compileProgram`.
- **2D pixel space.** Coordinates are framebuffer pixels with the origin at the top-left corner, x to the right and y downwards. Every 2D projection in the module is `Mat4::ortho(0, W, H, 0, -1, 1)` (left 0, right W, bottom H, top 0), so y = 0 maps to NDC y = +1, the top of the viewport.
- **Render-target textures are bottom-up.** As in any GL framebuffer, texel row 0 of a render target's colour texture is the bottom row of the picture. Whoever shows such a texture in pixel space flips v: callers of `Renderer2D::image` pass `u0 = 0, v0 = 1, u1 = 1, v1 = 0`, and the page-turn shaders compute `v = 1 - y / H`.
- **GL state.** Each drawing function sets the state it depends on (viewport, blend, depth, cull, program, VAO, texture units). Nothing is saved or restored except where stated, and GL errors are never queried.
- **Shader bodies** are `const char*` C++ raw string literals `R"( … )"` in the anonymous namespace. Each literal opens with `R"(` at the end of a line and closes with `)"` at the start of a line. So every body begins with a newline character and ends with the newline after its last `}`. Bodies contain no `#version` line and no precision statement; `gl::shaderSource` prepends them. All bodies are written in the common subset of GLSL 4.10 core and GLSL ES 3.00:
  - Vertex inputs are declared `layout(location = N) in …`. The C++ side never calls `glBindAttribLocation`.
  - Varyings use `in`/`out`. The single fragment output is a user-declared `out vec4 fragColor;`, and `glBindFragDataLocation` is never called.
  - All sampling uses `texture(…)`, never `texture2D`, and `gl_FragColor` is never used.
  - Every float literal has a decimal point (`0.0`, `1.0`, `2.0 * r`), because GLSL ES has no implicit int→float conversion. The only integer uniform, `uMode`, is compared with integer literals.
  - The bodies contain no precision qualifiers. On GLES the prepended `precision highp float;` applies to both stages. That is what makes the uniforms declared in both stages of the sheet program (`uSize`, `uRadius`) legal: they get the same precision in both.

---

## 1. GlCommon.cpp

Includes: `"render/GlCommon.h"`, `<cmath>`, `<vector>`.
Definition order: `Color::packed`, `Mat4::ortho`, `Mat4::perspective`, `Mat4::lookAt`, `Mat4::operator*`, then inside `namespace gl`: `shaderSource`, the anonymous `compileStage`, `compileProgram`, `Texture::createRgba`, `Texture::destroy`, `RenderTarget::ensure`, `RenderTarget::destroy`, `glVersionString`.

### 1.1 `Color::packed`

Each channel is clamped to [0, 1], scaled to 255 and rounded half-up by truncation. R goes to the low byte, which is the byte order that a `4 × GL_UNSIGNED_BYTE` vertex attribute reads as (R, G, B, A) on a little-endian machine.

```cpp
auto c = [](float v) -> uint32_t {
  const float x = v < 0 ? 0 : (v > 1 ? 1 : v);
  return static_cast<uint32_t>(x * 255.0f + 0.5f);
};
return c(r) | (c(g) << 8) | (c(b) << 16) | (c(a) << 24);
```

Every colour that passes through `Renderer2D` (vertex colours and tints) is therefore quantised to steps of 1/255. For example, alpha 0.045 becomes 11, because 11.475 + 0.5 truncates to 11.

### 1.2 `Mat4`

Storage is column-major, `m[col * 4 + row]`, and every matrix is uploaded with `transpose = GL_FALSE`. The default member initializer in the header is the identity. `ortho` and `perspective` start from a default-constructed matrix and overwrite only the elements listed below.

**`ortho(l, r, b, t, n, f)`** builds the `glOrtho` matrix:
- `m[0] = 2.0f / (r - l)`, `m[5] = 2.0f / (t - b)`, `m[10] = -2.0f / (f - n)`
- `m[12] = -(r + l) / (r - l)`, `m[13] = -(t + b) / (t - b)`, `m[14] = -(f + n) / (f - n)`
- All other elements keep their identity values (`m[15] = 1`).

**`perspective(fovy, aspect, n, f)`** builds the `gluPerspective` matrix, with `k = 1.0f / std::tan(fovy * 0.5f)`:
- `m[0] = k / aspect`, `m[5] = k`, `m[10] = (f + n) / (n - f)`, `m[11] = -1.0f`, `m[14] = 2.0f * f * n / (n - f)`, `m[15] = 0.0f`
- All other elements keep their identity values (0).

**`lookAt(ex, ey, ez, cx, cy, cz, ux, uy, uz)`** builds the `gluLookAt` matrix (right-handed; the camera looks along its own −z):
1. `f = c − e`. Compute `fl = std::sqrt(fx*fx + fy*fy + fz*fz)` and divide each component by `fl`.
2. `s = f × u`: `sx = fy*uz − fz*uy`, `sy = fz*ux − fx*uz`, `sz = fx*uy − fy*ux`. Divide each component by its length, computed with `std::sqrt` in the same way.
3. `v = s × f`: `vx = sy*fz − sz*fy`, `vy = sz*fx − sx*fz`, `vz = sx*fy − sy*fx`. It is not normalised again.
4. Every element of the result is written:

| | col 0 | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| row 0 | `m[0] = sx` | `m[4] = sy` | `m[8] = sz` | `m[12] = -(sx*ex + sy*ey + sz*ez)` |
| row 1 | `m[1] = vx` | `m[5] = vy` | `m[9] = vz` | `m[13] = -(vx*ex + vy*ey + vz*ez)` |
| row 2 | `m[2] = -fx` | `m[6] = -fy` | `m[10] = -fz` | `m[14] = fx*ex + fy*ey + fz*ez` |
| row 3 | `m[3] = 0` | `m[7] = 0` | `m[11] = 0` | `m[15] = 1` |

There is no guard against a zero-length forward or side vector.

**`operator*(b)`** is the ordinary product `this × b`, so `(A * B)·x = A·(B·x)` and `proj * view` applies the view first:

```cpp
Mat4 o;
for (int col = 0; col < 4; ++col) {
  for (int row = 0; row < 4; ++row) {
    float s = 0;
    for (int k = 0; k < 4; ++k) s += m[k * 4 + row] * b.m[col * 4 + k];
    o.m[col * 4 + row] = s;
  }
}
return o;
```

### 1.3 `gl::shaderSource(body, fragment)`

Returns a prefix followed by `body`. The prefix is chosen at compile time with `#if defined(LL_GLES)`; `Gl.h` defines `LL_GLES` on Android or when `LL_USE_GLES` is defined.

- GLES: `"#version 300 es\nprecision highp float;\n"`
- Desktop: `"#version 410 core\n"`

Both branches ignore `fragment` (`(void)fragment;`). Vertex and fragment shaders get the same prefix, so on GLES the vertex shader also starts with `precision highp float;`. Because every body starts with a newline, line 2 (desktop) or line 3 (GLES) of every compiled shader is empty.

### 1.4 `compileStage` (file-local) and `gl::compileProgram`

`GLuint compileStage(GLenum type, const std::string& src, std::string* log)`:
1. `glCreateShader(type)`, then `glShaderSource(sh, 1, &p, nullptr)` with `p = src.c_str()`, then `glCompileShader`.
2. Query `GL_COMPILE_STATUS` with `glGetShaderiv`. On success, return the shader. No log is read on success.
3. On failure:
   - Query `GL_INFO_LOG_LENGTH` (`glGetShaderiv`) into `len`.
   - Allocate a zero-filled `std::vector<char>` of `len > 1 ? len : 1` bytes and call `glGetShaderInfoLog(sh, size, nullptr, buf.data())`.
   - If `log` is non-null, append `"vertex: "` (when `type == GL_VERTEX_SHADER`) or `"fragment: "` (any other type), followed by the log text up to its first NUL. No separator or newline is added; whatever line ends the driver's log has are kept.
   - Delete the shader and return 0.

`GLuint compileProgram(vertexBody, fragmentBody, log)`:
1. Call `compileStage(GL_VERTEX_SHADER, shaderSource(vertexBody, false), log)`, then `compileStage(GL_FRAGMENT_SHADER, shaderSource(fragmentBody, true), log)`. Both stages are always compiled, so one call can append both a vertex message and a fragment message.
2. If either result is 0, `glDeleteShader` the stage that did compile and return 0. No link is attempted and no `"link: "` text is written.
3. Otherwise `glCreateProgram`, `glAttachShader` the vertex shader and then the fragment shader, call `glLinkProgram`, then `glDeleteShader` both. They stay attached; nothing is detached.
4. Query `GL_LINK_STATUS` with `glGetProgramiv`. On failure, read the log the same way as in `compileStage` (`GL_INFO_LOG_LENGTH` via `glGetProgramiv`, same length rule, `glGetProgramInfoLog`). If `log` is non-null, append `"link: "` + text. Call `glDeleteProgram` and return 0.
5. Return the program. There is no `glValidateProgram` and no attribute or output binding; the layouts in the bodies fix them.

Messages accumulate: callers pass the same `std::string*` to several calls, and each message is simply appended to what is already there.

### 1.5 `Texture`

`createRgba(rgba, w, h, mipmaps)`:
1. Call `destroy()` to free a previous texture.
2. `glGenTextures(1, &id)` and `glBindTexture(GL_TEXTURE_2D, id)` on the currently active texture unit. The texture is left bound.
3. `glPixelStorei(GL_UNPACK_ALIGNMENT, 4)`. It is left at 4.
4. `glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba)`. The caller's rows are uploaded as given, with no flip.
5. With `glTexParameteri`, set `GL_TEXTURE_WRAP_S` and `GL_TEXTURE_WRAP_T` to `GL_CLAMP_TO_EDGE`, then `GL_TEXTURE_MAG_FILTER` to `GL_LINEAR`.
6. If `mipmaps`: call `glGenerateMipmap(GL_TEXTURE_2D)`, then set `GL_TEXTURE_MIN_FILTER` to `GL_LINEAR_MIPMAP_LINEAR`. Otherwise set `GL_TEXTURE_MIN_FILTER` to `GL_LINEAR`.
7. Set `width = w` and `height = h`, and return `id != 0`.

There is no argument validation, no anisotropic filtering and no swizzle.

`destroy()`: if `id` is non-zero, call `glDeleteTextures`. Then set `id = 0` and `width = height = 0`.

### 1.6 `RenderTarget`

`ensure(w, h, withDepth)`:
1. **Reuse rule.** If `fbo != 0 && w == width && h == height && (depth != 0) == withDepth`, return `true` at once. No GL call is made and nothing is bound.
2. Otherwise call `destroy()`. Any change of size or of the depth flag recreates everything, and the old contents are lost.
3. If `w <= 0 || h <= 0`, return `false`. The target is now empty.
4. Colour attachment:
   - `glGenTextures`, then bind the texture to `GL_TEXTURE_2D` on the active unit. It is left bound.
   - `glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr)`: contents uninitialised, no mipmaps.
   - Set `GL_TEXTURE_MIN_FILTER` and `GL_TEXTURE_MAG_FILTER` to `GL_LINEAR`, then `GL_TEXTURE_WRAP_S` and `GL_TEXTURE_WRAP_T` to `GL_CLAMP_TO_EDGE`.
5. `glGenFramebuffers`, `glBindFramebuffer(GL_FRAMEBUFFER, fbo)`, then `glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, color, 0)`.
6. If `withDepth`: `glGenRenderbuffers` and `glBindRenderbuffer` (it is left bound to `GL_RENDERBUFFER`). Then `glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, w, h)` and `glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth)`. There is no stencil and no multisampling.
7. `ok = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE`.
8. `glBindFramebuffer(GL_FRAMEBUFFER, 0)`. This always binds the default framebuffer, not the framebuffer that was bound before the call.
9. Set `width = w` and `height = h`. If `!ok`, call `destroy()`, which zeroes the sizes again. Return `ok`.

`destroy()`: in this order and each only if non-zero, `glDeleteFramebuffers(fbo)`, `glDeleteTextures(color)` and `glDeleteRenderbuffers(depth)`. Then zero `fbo`, `color`, `depth`, `width` and `height`.

### 1.7 `gl::glVersionString()`

Returns `reinterpret_cast<const char*>(glGetString(GL_VERSION))`, or the literal `"unknown"` when that pointer is null.

---

## 2. GlyphAtlas.cpp

Includes: `"render/GlyphAtlas.h"`, `<ft2build.h>`, `#include FT_FREETYPE_H`, `#include FT_OUTLINE_H`, `<algorithm>`, `<cmath>`, `<cstring>`.
Definition order: `init`, `shutdown`, `reset`, `allocate`, `get`. The file has no file-local helpers.

The atlas is one square single-channel texture:
- Glyph bitmaps (8-bit coverage) are packed on horizontal shelves.
- A 4×4 opaque block at the origin serves every solid fill.
- A hash map keyed by (face, glyph, quarter-pixel size, sub-pixel bin) holds a `GlyphEntry` for every glyph requested since the last reset.

The atlas never resets itself. When a glyph does not fit, it reports overflow and the client resets it (section 5).

### 2.1 `init(size)`

1. `GLint maxTex = 2048; glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxTex);`, then `size_ = std::min(size, static_cast<int>(maxTex))`. The value 2048 is only the fallback for a query that writes nothing.
2. `glGenTextures(1, &tex_)` and bind it to `GL_TEXTURE_2D` on the active unit.
3. Fill a buffer of `size_ * size_` bytes with zeros and set `glPixelStorei(GL_UNPACK_ALIGNMENT, 1)`. Then `glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, size_, size_, 0, GL_RED, GL_UNSIGNED_BYTE, zero.data())`, so the whole atlas starts at 0.
4. With `glTexParameteri`, set `GL_TEXTURE_MIN_FILTER` and `GL_TEXTURE_MAG_FILTER` to `GL_LINEAR` (no mipmaps), then `GL_TEXTURE_WRAP_S` and `GL_TEXTURE_WRAP_T` to `GL_CLAMP_TO_EDGE`.
5. **No swizzle** is set. The texture samples as `(r, 0, 0, 1)`, and the 2D shader reads only `.r`.
6. Call `reset()`, then return `tex_ != 0`. After the first `init`, `generation()` is therefore 1.

`init` does not delete a texture that already exists.

### 2.2 `shutdown()`

If `tex_` is non-zero, delete it. Then set `tex_ = 0` and call `map_.clear()`. The shelves, `shelfY_`, the overflow flag and the generation are left unchanged.

### 2.3 `reset()`

1. `map_.clear()`, `shelves_.clear()`, `shelfY_ = 0`, `overflowed_ = false`, `++generation_`.
2. The white block (source comment: `// A small opaque block for solid fills (rectangles, rules, progress bars).`): call `allocate(4, 4, x, y)`. As the first allocation it creates shelf `{y = 0, h = 5, x = 0}` and returns (0, 0). The shelf's x is left at 5 and `shelfY_` at 5.
3. Fill `unsigned char white[16]` with 255. Bind `tex_`, set `GL_UNPACK_ALIGNMENT` to 1, then `glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, 4, 4, GL_RED, GL_UNSIGNED_BYTE, white)`.
4. `whiteUV_ = (static_cast<float>(x) + 2.0f) / static_cast<float>(size_)`, which is 2/size_. `whiteU()` and `whiteV()` (header) both return it; the block's y is 0 as well. That point is the shared corner of the block's four central texels, so bilinear sampling there returns exactly 1.0.

The texture contents are **not** cleared. Texels of earlier glyphs stay until a new glyph overwrites them. Right after a reset, `fill()` (header: `shelfY_ / size_`) is 5/size_.

### 2.4 `allocate(w, h, x, y)`: shelf packing

Each rectangle is padded with a 1-px gutter on its right and bottom (`pw = w + 1`, `ph = h + 1`; source comment `// 1 px gutter`). The gutter is never written. `Shelf` (header) holds `{y, h, x}`: the top, the height and the next free x.

```
allocate(w, h, &x, &y):
  pw = w + 1; ph = h + 1
  best = -1
  for i = 0 .. shelves_.size()-1:                                   // in creation order
     s = shelves_[i]
     if s.h >= ph && s.h <= ph + ph / 3 + 2 && s.x + pw <= size_:   // integer division
        if best < 0 || s.h < shelves_[best].h: best = i            // lowest fitting shelf, earliest on ties
  if best < 0:
     if shelfY_ + ph > size_ || pw > size_: return false            // full: nothing changes
     shelves_.push_back(Shelf{shelfY_, ph, 0})                       // y = shelfY_, h = ph, x = 0
     shelfY_ += ph
     best = last index
  x = shelves_[best].x; y = shelves_[best].y
  shelves_[best].x += pw
  return true
```

A glyph with padded height `ph` may go on an existing shelf of height `S` if `ph ≤ S ≤ ph + ⌊ph/3⌋ + 2` and the shelf still has `pw` pixels of width left. Among the shelves that qualify, the one with the smallest `S` wins. If none qualifies, a new shelf exactly `ph` tall opens directly below the last one. Shelves are never closed or reorganised; space comes back only with `reset()`.

### 2.5 `get(lib, face, glyph, sizePx, bin)`

```
sizeQ = static_cast<uint32_t>(std::lround(sizePx * 4.0f)) & 0xFFFFu          // quarter pixels
key   = (uint64)(face & 0xFFFF) << 48 | (uint64)glyph << 32 | (uint64)sizeQ << 8 | (uint64)(bin & 0xFF)
if map_ contains key: return &entry               // also for cached empty entries
if overflowed_: return nullptr                     // once full, nothing new is rasterised
FontFace& f = lib.face(face)
lib.setPixelSize(face, static_cast<float>(sizeQ) / 4.0f)      // the quantised size, not sizePx
GlyphEntry e                                       // all fields zero
if FT_Load_Glyph(f.ft, glyph, FT_LOAD_TARGET_LIGHT | FT_LOAD_NO_BITMAP) == 0:
   FT_GlyphSlot slot = f.ft->glyph
   if slot->format == FT_GLYPH_FORMAT_OUTLINE && bin != 0:
      FT_Outline_Translate(&slot->outline, static_cast<FT_Pos>(bin * 64 / kSubpixelBins), 0)
   if FT_Render_Glyph(slot, FT_RENDER_MODE_NORMAL) == 0:
      const FT_Bitmap& bm = slot->bitmap
      e.left = (int16_t)slot->bitmap_left;  e.top = (int16_t)slot->bitmap_top
      e.w = (uint16_t)bm.width;             e.h = (uint16_t)bm.rows
      if e.w > 0 && e.h > 0 && bm.pixel_mode == FT_PIXEL_MODE_GRAY:
         if !allocate(e.w, e.h, x, y): overflowed_ = true; return nullptr       // nothing is cached
         scratch_.resize(e.w * e.h)
         for row in 0 .. bm.rows-1: memcpy(&scratch_[row * e.w], bm.buffer + row * bm.pitch, e.w)
         glBindTexture(GL_TEXTURE_2D, tex_); glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
         glTexSubImage2D(GL_TEXTURE_2D, 0, x, y, e.w, e.h, GL_RED, GL_UNSIGNED_BYTE, scratch_.data())
         inv = 1.0f / size_
         e.u0 = x * inv;  e.v0 = y * inv;  e.u1 = (x + e.w) * inv;  e.v1 = (y + e.h) * inv
      else:
         e.w = e.h = 0                             // left/top keep the bitmap offsets
return &map_.emplace(key, e).first->second
```

Details:
- **Key.** Face (16 bits) occupies bits 48–63, glyph index bits 32–47, quantised size bits 8–23 and bin bits 0–7; bits 24–31 are zero. Sizes that round to the same quarter pixel share entries.
- **Size quantisation.** The cache key and the rasterised size both use `sizeQ / 4`. `FontLibrary::setPixelSize` then selects `lround(sizeQ/4 · 64) = 16·sizeQ` in 26.6 units at 72 dpi, and does nothing when that size is already selected. `setPixelSize` is called before every rasterisation, even when the glyph then fails to load. Glyph positions in `Renderer2D::text` use the exact size.
- **Hinting.** The load flags are exactly `FT_LOAD_TARGET_LIGHT | FT_LOAD_NO_BITMAP`: FreeType light hinting (vertical fitting only), with embedded bitmaps ignored. The code uses no `FT_LOAD_RENDER`, `FT_LOAD_NO_HINTING`, `FT_LOAD_FORCE_AUTOHINT` or `FT_LOAD_COLOR`, no `FT_Set_Transform` and no LCD mode. The outline is hinted at load time, then translated, then rendered.
- **Sub-pixel bins.** `kSubpixelBins` is 4. The shift is integer arithmetic in 26.6 units: bin 1 → 16 (¼ px), bin 2 → 32 (½ px), bin 3 → 48 (¾ px), always to the right (+x, y unchanged). Bin 0, and any slot that does not hold an outline, is not translated. The shift changes the bitmap's coverage and possibly `bitmap_left`, so `e.left` already accounts for it.
- **Render mode.** `FT_RENDER_MODE_NORMAL` gives 8-bit anti-aliased coverage (`FT_PIXEL_MODE_GRAY`). Coverage is stored linearly; the text gamma is applied later in the shader.
- **Upload.** Rows are copied tightly packed (`w` bytes per row; source row r at `bm.buffer + r * bm.pitch`) into the reusable `scratch_` buffer. The upload binds the atlas to `GL_TEXTURE_2D` on whichever texture unit is active.
- **UVs** are the exact texel rectangle. Bitmap row 0 (the top of the glyph) goes to atlas row `y`, so v grows downwards.
- **Empty and failed glyphs** are cached too: failed load, failed render, a zero-size bitmap (space) or a non-gray pixel mode. Their entries have `w = h = 0` and are not retried within the generation. If FreeType fails, the entry is all zeros. If the bitmap is merely empty or not gray, `left`/`top` hold the bitmap offsets.
- **Overflow.** When `allocate` fails, `overflowed_` is set, nothing is cached and `nullptr` is returned. From then until `reset()` (or the header's `clearOverflow()`), cache hits still return their entries but every miss returns `nullptr` without touching FreeType.
- The returned pointer stays valid until `reset()` or `shutdown()` clears the map.

---

## 3. Renderer2D.cpp

Includes: `"render/Renderer2D.h"`, `<cmath>`.
Definition order: an anonymous namespace holding `kVs` and `kFs`, then `init`, `shutdown`, `ensureIndices`, `begin`, `flush`, `quad`, `quad4`, `rect`, `gradientH`, `gradientV`, `image`, `text`, `drawText`, `textWidth`.

### 3.1 Shaders (verbatim)

```cpp
const char* kVs = R"(
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;
layout(location = 2) in vec4 aColor;
uniform mat4 uProj;
out vec2 vUV;
out vec4 vColor;
void main() {
  vUV = aUV;
  vColor = aColor;
  gl_Position = uProj * vec4(aPos, 0.0, 1.0);
}
)";

const char* kFs = R"(
in vec2 vUV;
in vec4 vColor;
uniform sampler2D uTex;
uniform int uMode;
uniform float uGamma;
out vec4 fragColor;
void main() {
  if (uMode == 0) {
    float a = pow(texture(uTex, vUV).r, uGamma);
    fragColor = vec4(vColor.rgb, vColor.a * a);
  } else if (uMode == 1) {
    fragColor = texture(uTex, vUV) * vColor;
  } else {
    vec4 c = texture(uTex, vUV);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    fragColor = vec4(vColor.rgb * l, c.a * vColor.a);
  }
}
)";
```

The three modes selected by `uMode` (there is no separate "solid" mode):

| `uMode` | used by | fragment colour |
|---|---|---|
| 0 | every batched quad: glyphs, `rect`, `gradientH`, `gradientV` (all sample the atlas) | rgb = vColor.rgb; a = vColor.a · pow(atlas.r, uGamma). Solid fills sample the white block (r = 1.0), so their alpha is vColor.a. |
| 1 | `image(…, mono = false)` | texel × vColor, component-wise on all four channels |
| 2 (`else`) | `image(…, mono = true)` | rgb = vColor.rgb · dot(texel.rgb, (0.299, 0.587, 0.114)); a = texel.a · vColor.a |

### 3.2 Vertex format and buffers

`Renderer2D::Vertex` (header) is `x, y, u, v` as `float` followed by `rgba` as `uint32_t`: 20 bytes with no padding. The VAO holds three attributes:

| location | name | source | type | normalised | offset | stride |
|---|---|---|---|---|---|---|
| 0 | `aPos` | x, y | 2 × `GL_FLOAT` | `GL_FALSE` | 0 | `sizeof(Vertex)` = 20 |
| 1 | `aUV` | u, v | 2 × `GL_FLOAT` | `GL_FALSE` | 8 | 20 |
| 2 | `aColor` | rgba | 4 × `GL_UNSIGNED_BYTE` | `GL_TRUE` | 16 | 20 |

Because `Color::packed` puts R in the low byte, `aColor` = (R, G, B, A)/255.

**Index buffer.** All draws share one static element buffer of 32-bit indices (`GL_UNSIGNED_INT`, which ES 3.0 allows), attached to the VAO. Quad q uses vertices 4q…4q+3 in the order top-left, top-right, bottom-right, bottom-left (see `quad`), with indices `4q, 4q+1, 4q+2, 4q+2, 4q+3, 4q`. That makes triangles (TL, TR, BR) and (BR, BL, TL).

`ensureIndices(quads)`:
```
if quads <= iboQuads_: return
n = iboQuads_ ? iboQuads_ : 1024
while n < quads: n *= 2
idx = n * 6 uint32: for q in 0..n-1, b = 4q: b, b+1, b+2, b+2, b+3, b
glBindVertexArray(vao_); glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo_)
glBufferData(GL_ELEMENT_ARRAY_BUFFER, idx bytes, idx, GL_STATIC_DRAW)   // the VAO stays bound
iboQuads_ = n
```
The whole buffer is re-specified at the new size, which doubles from the previous capacity.

### 3.3 `init(err)`

1. `prog_ = gl::compileProgram(kVs, kFs, err)`. If it is 0, return `false`; nothing else is created.
2. Look up uniform locations with `glGetUniformLocation`: `uProj_` ← `"uProj"`, `uTex_` ← `"uTex"`, `uMode_` ← `"uMode"`, `uGamma_` ← `"uGamma"`.
3. Create the vertex state:
   - `glGenVertexArrays` (VAO), then `glGenBuffers` for the VBO and for the IBO. Bind the VAO and bind the VBO to `GL_ARRAY_BUFFER`.
   - For attributes 0, 1 and 2, in that order, call `glEnableVertexAttribArray` and `glVertexAttribPointer` as in 3.2.
   - Bind the IBO to `GL_ELEMENT_ARRAY_BUFFER`.
   - Call `ensureIndices(4096)`: n goes 1024 → 2048 → 4096, giving 24 576 indices.
   - Bind VAO 0. No vertex data is uploaded yet.
4. Call `atlas_.init(2048)`. If it fails and `err` is non-null, append `"glyph atlas creation failed"` (no newline) to `*err`. Return `false` in that case and `true` otherwise.

### 3.4 `shutdown()`

Call `atlas_.shutdown()`. Then, each only if non-zero and in this order: `glDeleteBuffers` (IBO), `glDeleteBuffers` (VBO), `glDeleteVertexArrays` (VAO), `glDeleteProgram`. Set all four handles to 0. `iboQuads_` is **not** reset. A second `init` after `shutdown` would therefore find `ensureIndices(4096)` already satisfied and leave the new IBO without data; `App` never does this.

### 3.5 `begin(width, height)`

`begin` draws into whatever framebuffer is currently bound; it binds none itself.
- Store `width_` and `height_`, then `verts_.clear()`. Quads that were not flushed are discarded, not drawn.
- `glViewport(0, 0, width, height)`.
- `glDisable(GL_DEPTH_TEST)`, `glDisable(GL_CULL_FACE)`, `glEnable(GL_BLEND)`.
- `glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)`. This gives colour = src.rgb·src.a + dst.rgb·(1 − src.a) and alpha = src.a + dst.a·(1 − src.a): source colours are straight, not premultiplied. The blend equation keeps its default (`GL_FUNC_ADD`). Scissor, colour mask and depth mask are not touched.

`begin` does not reset `gamma_`.

### 3.6 Batching and `flush()`

`rect`, `gradientH`, `gradientV` and `text` only append 4 vertices per quad to `verts_` on the CPU. `flush()` draws everything appended since the previous flush with one `glDrawElements`, in append order (painter's order). A flush happens only in these cases:
- the caller calls `flush()`;
- `image()` starts;
- `setTextGamma(g)` (header) is called with a `g` different from the current gamma.

A batch has no size limit (the index buffer grows) and needs no texture switch, because the atlas is its only texture.

`flush()`:
1. Return if `verts_` is empty.
2. `quads = verts_.size() / 4`; call `ensureIndices(quads)`.
3. `glUseProgram(prog_)`. Set `uProj` to `Mat4::ortho(0, (float)width_, (float)height_, 0, -1, 1)` via `glUniformMatrix4fv(uProj_, 1, GL_FALSE, proj.m)`. Set `uTex = 0`, `uMode = 0` and `uGamma = gamma_`.
4. `glActiveTexture(GL_TEXTURE0)`, then bind `atlas_.texture()`.
5. Bind the VAO and bind the VBO to `GL_ARRAY_BUFFER`. Then `glBufferData(GL_ARRAY_BUFFER, verts_.size() * sizeof(Vertex), verts_.data(), GL_STREAM_DRAW)`; the buffer is re-specified on every flush.
6. `glDrawElements(GL_TRIANGLES, quads * 6, GL_UNSIGNED_INT, nullptr)`, then bind VAO 0 and call `verts_.clear()`.

Afterwards the program is `prog_`, texture unit 0 is active with the atlas bound, and `GL_ARRAY_BUFFER` is the VBO. Glyphs rasterised during a batch go into the atlas immediately (`glTexSubImage2D` inside `GlyphAtlas::get`). The draw at flush time reads the atlas as it is at that moment.

### 3.7 Quads, rectangles, gradients

`quad(x, y, w, h, u0, v0, u1, v1, c)` appends four vertices, all with colour `c`:
`(x, y, u0, v0)`, `(x + w, y, u1, v0)`, `(x + w, y + h, u1, v1)`, `(x, y + h, u0, v1)`.

`quad4(x, y, w, h, u, v, c00, c10, c11, c01)` appends the same four corners, all with texture coordinate (u, v). Their colours are `c00` (top-left), `c10` (top-right), `c11` (bottom-right) and `c01` (bottom-left).

- `rect(x, y, w, h, c)`: return if `w <= 0 || h <= 0`. Otherwise `quad(x, y, w, h, u, v, u, v, c.packed())` with `u = whiteU()`, `v = whiteV()`. Coordinates are not rounded.
- `gradientH(x, y, w, h, left, right)`: same size test. Then `quad4(x, y, w, h, whiteU(), whiteV(), l, r, r, l)` with `l = left.packed()`, `r = right.packed()`.
- `gradientV(x, y, w, h, top, bottom)`: same size test. Then `quad4(…, t, t, b, b)` with `t = top.packed()`, `b = bottom.packed()`.

The rasteriser interpolates the 8-bit corner colours over the two triangles. Both triangles of a gradient quad carry equal colours along the edges where the gradient is constant, so the result varies only along x (`gradientH`) or y (`gradientV`). Colour and alpha are interpolated unpremultiplied, then blended as in 3.5.

### 3.8 `image(tex, x, y, w, h, tint, u0, v0, u1, v1, mono)`

`image` draws at once, outside the batch:
1. Call `flush()`, so everything batched before the image is drawn first and order is kept.
2. Build a local `const Vertex v[4]` in `quad` order: `(x, y, u0, v0)`, `(x + w, y, u1, v0)`, `(x + w, y + h, u1, v1)`, `(x, y + h, u0, v1)`. Each vertex carries `tint.packed()`.
3. `glUseProgram(prog_)`. Set `uProj` to the same ortho as `flush`, `uTex = 0` and `uMode = mono ? 2 : 1`. `uGamma` is not set.
4. `glActiveTexture(GL_TEXTURE0)`, then bind `tex`. It is left bound.
5. Bind the VAO and the VBO, then `glBufferData(GL_ARRAY_BUFFER, sizeof(v) /* 80 */, v, GL_STREAM_DRAW)`. Then `glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, nullptr)` and bind VAO 0.

There is no size test, so zero or negative sizes still issue the draw. There is no `ensureIndices` call either, because the first 6 indices always exist. The texture is sampled with its own filter and wrap state, and `verts_` stays empty.

### 3.9 `text`, `drawText`, `textWidth`

`text(lib, run, x, baseline, size, c)` takes pen positions from the shaped run in em units (`ShapedGlyph::x` is measured from the run origin, `y` is positive upwards) and scales them by `size` px:

```cpp
const uint32_t col = c.packed();
const float by = std::round(baseline);
for (const ShapedGlyph& g : run.glyphs) {
  const float gx = x + g.x * size;
  const float gy = by - std::round(g.y * size);
  float ix = std::floor(gx);
  int bin = static_cast<int>(std::lround((gx - ix) * GlyphAtlas::kSubpixelBins));
  if (bin >= GlyphAtlas::kSubpixelBins) {
    ix += 1.0f;
    bin = 0;
  }
  const GlyphEntry* e = atlas_.get(lib, g.face, g.glyph, size, bin);
  if (!e || e->w == 0) continue;
  quad(ix + e->left, gy - e->top, e->w, e->h, e->u0, e->v0, e->u1, e->v1, col);
}
```

- **Vertical.** The baseline and each glyph's vertical offset are rounded to whole pixels with `std::round` (halves away from zero).
- **Horizontal.** The run's x is never rounded as a whole. Each glyph's pen x is split into an integer pixel `ix` and the nearest quarter pixel (`std::lround`, halves away from zero). A fractional part in [0, 0.125) gives bin 0, [0.125, 0.375) bin 1, [0.375, 0.625) bin 2 and [0.625, 0.875) bin 3. A fractional part in [0.875, 1) gives bin 0 of the next pixel.
- **Pixel alignment.** Every glyph quad has integer corners and exactly the bitmap's size, so atlas texels map 1:1 onto pixels. The sub-pixel position lives in the rasterised bitmap (2.5).
- **Atlas call.** The atlas receives the unquantised `size`. A `nullptr` result (overflow) and an empty bitmap are both skipped silently. `text` never flushes.

`drawText(shaper, utf8, style, x, baseline, size, c)`: `const ShapedRun& run = shaper.shape(utf8, style)` (shaping is cached), then `text(shaper.library(), run, x, baseline, size, c)`. Returns `run.advance * size`, unrounded.

`textWidth(shaper, utf8, style, size)` is static and makes no GL call. It returns `shaper.shape(utf8, style).advance * size`.

---

## 4. PageTurn.cpp

Includes: `"render/PageTurn.h"`, `<algorithm>`, `<cmath>`, `<vector>`.
Definition order: an anonymous namespace holding `kCols`, `kRows`, `kPi` and the four shader strings in the order below, then `init`, `shutdown`, `draw`.

### 4.1 File-local constants and shaders (verbatim)

```cpp
constexpr int kCols = 96;
constexpr int kRows = 40;
constexpr float kPi = 3.14159265358979f;

// Page space: pixels, x right, y down. A lifted point gets world z = -height (towards the camera).
const char* kSheetVs = R"(
layout(location = 0) in vec2 aUV;
uniform mat4 uMVP;
uniform vec2 uSize;
uniform vec2 uSheetX0;      // x = left edge of the sheet, y = sheet width
uniform vec2 uAxisPoint;
uniform vec2 uAxisNormal;
uniform float uRadius;
out vec2 vPos;
out float vFacing;
out float vDist;
void main() {
  vec2 p = vec2(uSheetX0.x + aUV.x * uSheetX0.y, aUV.y * uSize.y);
  float d = dot(p - uAxisPoint, uAxisNormal);
  vec3 pos = vec3(p, 0.0);
  float facing = 1.0;
  if (d > 0.0) {
    vec2 base = p - d * uAxisNormal;
    float r = max(uRadius, 0.001);
    float arc = 3.14159265 * r;
    if (d < arc) {
      float a = d / r;
      pos = vec3(base + uAxisNormal * (r * sin(a)), -r * (1.0 - cos(a)));
      facing = cos(a);
    } else {
      pos = vec3(base - uAxisNormal * (d - arc), -2.0 * r);
      facing = -1.0;
    }
  }
  vPos = p;
  vFacing = facing;
  vDist = d;
  gl_Position = uMVP * vec4(pos, 1.0);
}
)";

const char* kSheetFs = R"(
in vec2 vPos;
in float vFacing;
in float vDist;
uniform vec2 uSize;
uniform sampler2D uFront;
uniform sampler2D uBack;
uniform vec3 uPaper;
uniform float uBackPrint;
uniform float uRadius;
uniform float uShadows;
uniform float uSpine;
uniform float uSpread;
out vec4 fragColor;
void main() {
  vec2 uv = vec2(vPos.x / uSize.x, 1.0 - vPos.y / uSize.y);
  if (vFacing >= 0.0) {
    vec3 c = texture(uFront, uv).rgb;
    float light = mix(0.78, 1.0, vFacing);
    float s = uShadows * (1.0 - clamp(-vDist / (max(uRadius, 1.0) * 1.2), 0.0, 1.0)) * step(vDist, 0.0);
    light *= 1.0 - 0.18 * s;
    fragColor = vec4(c * light, 1.0);
  } else {
    vec3 back;
    if (uSpread > 0.5) {
      // The other side of the sheet is the next left page, mirrored about the spine.
      back = texture(uBack, vec2((2.0 * uSpine - vPos.x) / uSize.x, uv.y)).rgb;
    } else {
      back = mix(uPaper, texture(uFront, uv).rgb, uBackPrint);
    }
    float light = mix(0.84, 1.0, -vFacing);
    fragColor = vec4(back * light, 1.0);
  }
}
)";

const char* kUnderVs = R"(
layout(location = 0) in vec2 aPos;
uniform mat4 uProj;
out vec2 vPos;
void main() {
  vPos = aPos;
  gl_Position = uProj * vec4(aPos, 0.0, 1.0);
}
)";

const char* kUnderFs = R"(
in vec2 vPos;
uniform sampler2D uTexA;
uniform sampler2D uTexB;
uniform vec2 uSize;
uniform vec2 uAxisPoint;
uniform vec2 uAxisNormal;
uniform float uRadius;
uniform float uSpine;
uniform float uShadows;
out vec4 fragColor;
void main() {
  vec2 uv = vec2(vPos.x / uSize.x, 1.0 - vPos.y / uSize.y);
  vec3 c;
  if (vPos.x < uSpine) {
    c = texture(uTexA, uv).rgb;   // left page of the current spread (two-page mode only)
  } else {
    c = texture(uTexB, uv).rgb;
    float r = max(uRadius, 4.0);
    float d = dot(vPos - uAxisPoint, uAxisNormal);
    float s = 1.0 - clamp((d - uRadius) / (r * 2.5), 0.0, 1.0);
    c *= 1.0 - uShadows * 0.5 * s * s;
  }
  fragColor = vec4(c, 1.0);
}
)";
```

Programs: the **sheet program** is `kSheetVs` + `kSheetFs`, and the **under program** is `kUnderVs` + `kUnderFs`. In the sheet shaders the constant π appears as the GLSL literal `3.14159265`. On the C++ side it is `kPi = 3.14159265358979f`.

### 4.2 The geometric model

Page space is the 2D pixel space of section 0 (x right, y down), covering the whole viewport 0…W × 0…H, plus a z axis. The page lies in the plane z = 0, and a lifted point gets world z = −height, i.e. it moves towards the camera.

The fold is defined by a unit normal **n** = (nx, ny) = (cos θ, sin θ) and a scalar s. The fold line is the set of points with dot(p, **n**) = s, and the axis point **A** = s·**n** is passed as `uAxisPoint`. For a sheet point p, `d = dot(p − A, n)` is its signed distance past the fold line. With R = `max(uRadius, 0.001)` in the vertex shader:

| d | position of the point | `facing` |
|---|---|---|
| d ≤ 0 | unchanged: (p, 0) | 1 |
| 0 < d < πR | rolled onto a cylinder of radius R that touches the page along the fold line. With a = d/R: moved R·sin a along **n** and lifted to height R(1 − cos a), i.e. z = −R(1 − cos a). | cos a |
| d ≥ πR | past the half circumference, the sheet runs flat again at height 2R (z = −2R), back over the page: at distance d − πR from the fold line on the −**n** side | −1 |

Here `base = p − d·n` is the foot of p on the fold line. Since **n** points right and slightly down (θ > 0), the right edge peels off first, starting at the bottom-right corner, and the turned-over part lies on top of the page to the left of the fold line. `vPos` always carries the flat position p and `vDist` carries d, so texture coordinates and shading come from the unbent page.

### 4.3 `init(err)`

1. `sheetProg_ = gl::compileProgram(kSheetVs, kSheetFs, err)`, then `underProg_ = gl::compileProgram(kUnderVs, kUnderFs, err)`. Both compilations are always attempted, and their messages accumulate in `*err`. If either program is 0, return `false`; the one that succeeded stays allocated until `shutdown()`.
2. Uniform locations (`glGetUniformLocation`), first all of the sheet program, then all of the under program. The sheet program's are stored in `us_`: `mvp` ← `"uMVP"`, `size` ← `"uSize"`, `sheetX0` ← `"uSheetX0"`, `axisPoint` ← `"uAxisPoint"`, `axisNormal` ← `"uAxisNormal"`, `radius` ← `"uRadius"`, `front` ← `"uFront"`, `back` ← `"uBack"`, `paper` ← `"uPaper"`, `backPrint` ← `"uBackPrint"`, `shadows` ← `"uShadows"`, `spine` ← `"uSpine"`, `spread` ← `"uSpread"`.
   Uniform locations of the under program, stored in `uu_`: `proj` ← `"uProj"`, `size` ← `"uSize"`, `axisPoint` ← `"uAxisPoint"`, `axisNormal` ← `"uAxisNormal"`, `radius` ← `"uRadius"`, `texA` ← `"uTexA"`, `texB` ← `"uTexB"`, `spine` ← `"uSpine"`, `shadows` ← `"uShadows"`.
3. **Mesh.** The mesh has (kCols + 1) × (kRows + 1) = 97 × 41 = 3 977 vertices of two floats each, row by row (r outer, 0…40; c inner, 0…96). Vertex `r·97 + c` holds `aUV = (float(c) / kCols, float(r) / kRows)`. For every cell, r in 0…39 and c in 0…95:
   ```
   a = r * (kCols + 1) + c;  b = a + 1;  d = a + (kCols + 1);  e = d + 1;
   indices += { a, b, e,  e, d, a }      // uint32
   ```
   `indexCount_` = 96 · 40 · 6 = 23 040. Here a is the top-left corner, b top-right, e bottom-right and d bottom-left of the cell, in page space.
4. Create the buffers:
   - `meshVao_` (`glGenVertexArrays`), `meshVbo_` and `meshIbo_` (`glGenBuffers`): bind the VAO. Upload the vertices to the VBO with `GL_STATIC_DRAW`. Enable attribute 0 with `glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * sizeof(float), nullptr)`. Bind the IBO to `GL_ELEMENT_ARRAY_BUFFER`, recorded in the VAO, and upload the indices with `GL_STATIC_DRAW`.
   - `quadVao_` (`glGenVertexArrays`), `quadVbo_` (`glGenBuffers`): bind the VAO and the VBO. Call `glBufferData(GL_ARRAY_BUFFER, 12 * sizeof(float), nullptr, GL_DYNAMIC_DRAW)`. Enable attribute 0 with the same pointer as the mesh (2 floats, stride 8, offset 0). This VAO has no index buffer.
   - Bind VAO 0 and return `true`.

### 4.4 `shutdown()`

Delete, each only if non-zero and in this order: `meshIbo_`, `meshVbo_`, `quadVbo_` (`glDeleteBuffers`), `meshVao_`, `quadVao_` (`glDeleteVertexArrays`), then `sheetProg_` and `underProg_` (`glDeleteProgram`). Set all seven handles to 0.

### 4.5 `draw(p)`: derived values

`draw` renders into the currently bound framebuffer, which needs a depth buffer for pass 2. The parameter block is reproduced verbatim because its exact float expressions matter:

```cpp
const float W = static_cast<float>(p.width), H = static_cast<float>(p.height);
if (W <= 0 || H <= 0) return;
const bool spread = p.spineX > 0.0f && p.spineX < W;
const float sheetX0 = spread ? p.spineX : 0.0f;
const float sheetW = W - sheetX0;
const float t = std::clamp(p.t, 0.0f, 1.0f);
const float e = t < 0.5f ? 4 * t * t * t : 1 - std::pow(-2 * t + 2, 3.0f) / 2;  // ease in-out

// Fold line slightly tilted so the lower corner lifts first. A spread flattens the curl as the page
// lands, so that it ends up lying exactly mirrored about the spine.
const float theta0 = 0.16f;
const float r0 = std::max(18.0f, std::min(sheetW, H) * 0.085f);
float theta = theta0, radius = r0;
if (spread) {
  theta = theta0 * (1.0f - e);
  radius = r0 * std::min(1.0f, 2.0f * (1.0f - e));
}
const float nx = std::cos(theta), ny = std::sin(theta);
const float sStart = W * nx + H * ny + 2.0f;  // nothing lifted yet
const float sEnd = spread ? p.spineX - kPi * radius * 0.5f : -(kPi * r0 + r0) - 0.06f * W - H * ny;
const float s = sStart + (sEnd - sStart) * e;
const float ax = nx * s, ay = ny * s;
const float shadows = p.shadows ? 1.0f : 0.0f;
```

What these values mean:
- If `W <= 0 || H <= 0`, the function returns before any GL call.
- `e` is the cubic ease-in-out of the clamped `t`, so e(0) = 0, e(0.5) = 0.5 and e(1) = 1. The fold moves linearly in `e` from `sStart` to `sEnd`.
- `sStart` puts the fold line 2 px beyond the page's bottom-right corner (W, H) along **n**. Every page point then has d ≤ −2, so nothing is lifted.
- **Single page.** θ = 0.16 rad and R = r0 = max(18, 0.085·min(W, H)) stay constant for the whole turn. The fold travels to `sEnd = −(π·r0 + r0) − 0.06·W − H·ny`. That is far enough left that at e = 1 the whole turned-over sheet (at height 2R, slightly magnified by the perspective) is outside the viewport. The cast shadow has also left the viewport: every viewport point then has d ≥ π·r0 + r0 > 3.5·r0, the end of the shadow.
- **Spread.** The tilt goes to 0 linearly in `e`. The radius stays r0 up to e = 0.5, then shrinks linearly to 0 at e = 1. Here r0 uses `sheetW = W − spineX`. `sEnd = spineX − π·radius/2` uses the current, shrinking radius, so at e = 1 the fold line is the vertical line x = spineX.
- **Fold normal and axis point.** `(nx, ny)` is passed as `uAxisNormal` and `(ax, ay) = s·n` as `uAxisPoint`. The same `radius` value goes to both programs as `uRadius`.

### 4.6 GL sequence of `draw`

```
glViewport(0, 0, p.width, p.height)
glDisable(GL_BLEND); glDisable(GL_CULL_FACE); glDisable(GL_DEPTH_TEST)

// 1) What lies underneath: the new page (and in a spread the current left page), with the curl's shadow.
quad[12] = {0, 0, W, 0, W, H, W, H, 0, H, 0, 0}          // two triangles covering the viewport
glUseProgram(underProg_)
uProj = Mat4::ortho(0, W, H, 0, -1, 1); uSize = (W, H); uAxisPoint = (ax, ay); uAxisNormal = (nx, ny)
uRadius = radius; uSpine = spread ? p.spineX : 0; uShadows = shadows; uTexA = 0; uTexB = 1
glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, p.sheetTex)
glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, p.underTex)
glBindVertexArray(quadVao_); glBindBuffer(GL_ARRAY_BUFFER, quadVbo_)
glBufferData(GL_ARRAY_BUFFER, sizeof(quad) /* 48 */, quad, GL_DYNAMIC_DRAW)
glDrawArrays(GL_TRIANGLES, 0, 6)

// 2) The turning sheet in perspective; the camera maps the z = 0 plane 1:1 onto the viewport.
glClear(GL_DEPTH_BUFFER_BIT)
glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL)
camera (below)
glUseProgram(sheetProg_)
uMVP = proj * view; uSize = (W, H); uSheetX0 = (sheetX0, sheetW); uAxisPoint = (ax, ay)
uAxisNormal = (nx, ny); uRadius = radius; uFront = 0; uBack = 1
uPaper = (p.paper.r, p.paper.g, p.paper.b); uBackPrint = p.backPrint; uShadows = shadows
uSpine = spread ? p.spineX : 0; uSpread = spread ? 1 : 0
glBindVertexArray(meshVao_); glDrawElements(GL_TRIANGLES, indexCount_, GL_UNSIGNED_INT, nullptr)
glBindVertexArray(0)
glDisable(GL_DEPTH_TEST)
glActiveTexture(GL_TEXTURE1); glBindTexture(GL_TEXTURE_2D, 0); glActiveTexture(GL_TEXTURE0)
```

All matrices are uploaded with `glUniformMatrix4fv(loc, 1, GL_FALSE, m.m)`, the vec2/vec3 uniforms with `glUniform2f`/`glUniform3f`, the floats with `glUniform1f` and the samplers with `glUniform1i`. The texture bindings made in pass 1 serve pass 2 unchanged: unit 0 holds `sheetTex` (the sheet's `uFront`) and unit 1 holds `underTex` (the sheet's `uBack`). Both passes are opaque, with no blending, and write alpha 1.0.

**Camera** (verbatim):

```cpp
const float dist = H * 1.8f;
const float fovy = 2.0f * std::atan((H * 0.5f) / dist);
const Mat4 proj = Mat4::perspective(fovy, W / H, dist * 0.2f, dist * 3.0f);
const Mat4 view = Mat4::lookAt(W * 0.5f, H * 0.5f, -dist, W * 0.5f, H * 0.5f, 0.0f, 0.0f, -1.0f, 0.0f);
const Mat4 mvp = proj * view;
```

- The eye is at distance 1.8·H in front of the page centre, looking along +z. The up vector is (0, −1, 0), which matches page space with y down.
- fovy = 2·atan(1/3.6) ≈ 0.5419 rad ≈ 31.05° for every size. The aspect is W/H, near = 0.36·H and far = 5.4·H.
- With these values, a page point (x, y, 0) lands at NDC ((2x − W)/W, (H − 2y)/H), the same as the pass-1 ortho. The flat, unlifted part of the sheet therefore covers the viewport pixel for pixel.
- A lifted point (z < 0) has clip w = dist + z, so it appears magnified about the viewport centre by dist/(dist + z).

### 4.7 Pass 1: the page underneath

The pass draws a full-viewport quad, with the depth test disabled, so it writes no depth. Texture coordinates are `uv = (x / W, 1 − y / H)`, computed from the interpolated pixel position.

| region | colour |
|---|---|
| x < uSpine (spread only; with `uSpine = 0` in single-page mode it never happens) | `sheetTex(uv)`, unshaded: the current spread's left page |
| otherwise | `underTex(uv) · (1 − uShadows · 0.5 · s²)` with `s = 1 − clamp((d − R)/(2.5 · max(R, 4)), 0, 1)` and `d = dot(pos − A, n)` |

The cast shadow is full strength (×0.5) everywhere with d ≤ R, including d < 0. R is the farthest the curl reaches past the fold line in the plane. Beyond that the shadow fades with a quadratic falloff over 2.5·max(R, 4) px. The ×0.5 region lies under the sheet's flat part (d ≤ 0) and under the curl (0 < d ≤ R), so pass 2 draws over most of it.

### 4.8 Pass 2: the sheet and its shading

The mesh spans `[sheetX0, sheetX0 + sheetW] × [0, H]`: the whole viewport for a single page, or the part right of the spine for a spread. Each mesh cell is sheetW/96 × H/40 px. The vertex shader bends the mesh (4.2), and depth testing with `GL_LEQUAL` against the freshly cleared depth buffer (cleared to the default 1.0) resolves where the sheet overlaps itself. Triangles are drawn in mesh order (rows top to bottom, cells left to right), so where two fragments have equal depth the later one wins. The sheet always draws over pass 1, because pass 1 wrote no depth.

In the fragment shader, `uv = (vPos.x / W, 1 − vPos.y / H)` is computed from the interpolated flat position. Front or back is chosen from the sign of the interpolated `vFacing`, not from `gl_FrontFacing`.

| interpolated `vFacing` | colour (R = `uRadius`) |
|---|---|
| ≥ 0 (front side) | `front(uv) · mix(0.78, 1.0, vFacing) · (1 − 0.18 · s_fold)` |
| < 0 (back side) | `back · mix(0.84, 1.0, −vFacing)` |

- `s_fold = uShadows · (1 − clamp(−vDist / (max(R, 1) · 1.2), 0, 1)) · step(vDist, 0.0)`. `step(vDist, 0.0)` is 1 exactly when `vDist ≤ 0`, so `s_fold` is 0 on the curl.
- On the flat part (vFacing = 1) the facing factor is 1. There `s_fold` darkens up to 18 % at the fold line and fades linearly to nothing at 1.2·max(R, 1) px before it.
- On the curl the front-side factor falls from 1 to 0.78 as the surface turns edge-on (facing = cos a → 0). The back-side factor rises from 0.84 (edge-on) to 1.0 at the top of the cylinder. The flat turned-over part (facing −1) has light 1.0. Fragments of triangles that straddle these boundaries use the interpolated `vFacing`/`vDist` in the same formulas.
- Single-page back side: `back = mix(uPaper, front(uv), uBackPrint)`. The back is the paper colour with a fraction `backPrint` of the print showing through. Because the print is sampled at the same page position, it appears mirrored as seen from behind.
- Spread back side: `back = uBack((2·uSpine − vPos.x) / W, uv.y)`, i.e. the "to" view sampled at the mirror image of x about the spine. The back of the right page is therefore the next left page.
- The lighting has no light direction and no specular term.
- With `shadows = false`, `uShadows = 0` removes both the fold darkening and the cast shadow, but the facing-based lighting stays.

### 4.9 Two-page spread

A spread is active exactly when `0 < spineX < W`; any other value, including 0, gives single-page mode.
- **What moves.** Only the right part [spineX, W] moves. It is the sheet: the current right page, with its margin, sampled from `sheetTex`.
- **What stays.** Pass 1 keeps the left part [0, spineX) static and unshaded from `sheetTex`, which is the current left page. The right part of pass 1 shows `underTex`, the next right page, under the cast shadow.
- **The flip.** As `e` grows, the sheet rolls over the spine. Its back side shows `underTex` mirrored about the spine, which is the next left page. Over the second half of the turn the curl radius shrinks to 0 and the tilt to 0.
- **Landing (e = 1).** The fold line is x = spineX, R is 0 (the vertex shader clamps it to 0.001) and n = (1, 0). Every sheet point with d ≥ π·0.001 (the `else` branch) lies at (2·spineX − x + π·0.001, y, −0.002). The sheet therefore lands mirrored about the spine, flat on top of the left part, showing the next left page practically 1:1.
- **Residual shadow.** At that moment pass 1 still darkens the strip [spineX, spineX + 10) right of the spine by 1 − 0.5·(1 − (x − spineX)/10)², because R = 0 gives max(R, 4) = 4 and 2.5·4 = 10.
- **Off-centre spine.** If the spine is right of the centre (2·spineX > W), the landed sheet does not reach the strip [0, 2·spineX − W), which keeps showing `sheetTex`. If the spine is left of the centre, sheet points with x > 2·spineX sample the back at u < 0, which clamps to the edge (render targets use `GL_CLAMP_TO_EDGE`).

### 4.10 GL state left by `draw`

Viewport (0, 0, width, height); `GL_BLEND` **disabled** (not re-enabled); `GL_CULL_FACE` disabled; `GL_DEPTH_TEST` disabled; depth function `GL_LEQUAL`; program `sheetProg_`; VAO 0; `GL_ARRAY_BUFFER` = `quadVbo_`; texture unit 1 bound to 0; texture unit 0 active and still holding `p.sheetTex`.

### 4.11 Constants of the page turn

| constant | value | role |
|---|---|---|
| `kCols`, `kRows` | 96, 40 | mesh cells across and down the sheet |
| `kPi` (C++) | 3.14159265358979f | single-page and spread `sEnd` |
| π in `kSheetVs` | `3.14159265` | `arc = 3.14159265 * r`, the half circumference |
| `theta0` | 0.16 rad | fold tilt (single page constant; spread ×(1 − e)) |
| r0 | max(18, 0.085·min(sheetW, H)) | curl radius |
| spread radius factor | min(1, 2(1 − e)) | flattens the curl in the second half |
| `sStart` margin | +2.0 px | nothing lifted at e = 0 |
| single `sEnd` | −(π·r0 + r0) − 0.06·W − H·ny | fully off-screen at e = 1 |
| spread `sEnd` | spineX − π·radius·0.5 | fold line at the spine at e = 1 |
| eye distance | 1.8·H | camera |
| near / far | 0.2·dist / 3.0·dist | projection |
| VS radius floor | 0.001 | avoids division by 0 |
| front light | mix(0.78, 1.0, facing) | sheet front |
| fold shading | 0.18 strength, width 1.2·max(R, 1.0) | sheet flat part |
| back light | mix(0.84, 1.0, −facing) | sheet back |
| spread test | `uSpread > 0.5` | back-side source |
| cast shadow | strength 0.5, squared falloff, width 2.5·max(R, 4.0), starts at d = R | page underneath |

---

## 5. Contracts with `App` (context only; `App` is specified in `09-application.md`)

- **Initialisation.** `App` calls `r2d_.init(&err)` and, only if that succeeds, `turn_.init(&err)`, both with one string. On failure it shows `"OpenGL initialisation failed:\n" + err`. That string then holds the concatenated `"vertex: …"`, `"fragment: …"` and `"link: …"` messages or `"glyph atlas creation failed"`. Once initialised, it logs `gl::glVersionString()`.
- **2D frames.** `App::renderView` calls `begin(w, h)`, clears colour, calls `setTextGamma(theme gamma)`, draws (`text`, `drawText`, `rect`, `gradientH` for the spine crease, `image` for book pictures with a white tint), then `flush()`. For the instant, slide and fade turns, `App` shows render-target textures with `image(tex, x, 0, W, H, tint, 0, 1, 1, 0)` (flipped v; x is 0, or the slide offset). It never passes `mono = true`. Book pictures are `gl::Texture`s created with `mipmaps = true`.
- **Atlas maintenance.** The atlas only reports. Before each frame `App` calls `reset()` if `fill() > 0.92f`. After rendering a frame, or a pre-rendered page, it checks `overflowed()`; if set, it calls `reset()` and renders the same frame or page again, so missing glyphs are never shown. `generation()` and `clearOverflow()` are unused.
- **Render targets.** The turn sources `rtA_` (earlier view) and `rtB_` (later view) and the pre-rendered page caches use `ensure(fbW, fbH, false)`. In screenshot mode the frame itself goes into `rtShot_.ensure(fbW, fbH, true)`; it needs depth for `PageTurn`. Because `ensure` may leave framebuffer 0 bound, `App` binds the framebuffer it wants after calling it.
- **`PageTurn::Params` for the curl.**
  - `sheetTex = rtA_.color`, `underTex = rtB_.color`.
  - `width`/`height` = framebuffer size.
  - `t` = turn progress: 0 → 1 forwards, 1 → 0 backwards, so a backward turn plays the forward animation in reverse.
  - `spineX = columns == 2 ? std::round((columnX[0] + columnW + columnX[1]) * 0.5f) : 0`.
  - `paper` = theme background, `backPrint = theme dark ? 0.08f : 0.13f`, `shadows` = default `true`.

  Before calling `draw`, `App` binds the target framebuffer (default framebuffer with a 24-bit depth buffer, or `rtShot_`), sets the viewport and clears colour (to the theme background) and depth. Dear ImGui draws afterwards with its own state.

---

## Checklist

**GlCommon**
- [ ] `Color{1, 0.5f, 0, 1}.packed() == 0xFF0080FF`; `Color{-1, 2, 0.25f, 0}.packed() == 0x0040FF00` (clamp, then `x*255 + 0.5` truncated, R in the low byte).
- [ ] `Mat4::ortho(0, 800, 600, 0, -1, 1)` maps pixel (0, 0) to NDC (−1, +1) and (800, 600) to (+1, −1); its `m[15]` is 1.
- [ ] `Mat4::perspective` sets `m[11] = −1`, `m[14] = 2fn/(n − f)` and `m[15] = 0`; every element other than `m[0]`, `m[5]`, `m[10]`, `m[11]` and `m[14]` is 0.
- [ ] `(A * B)·x == A·(B·x)` for column vectors; element (row, col) is `m[col*4 + row]`.
- [ ] With W = 1000, H = 800, the page-turn `proj * view` maps (0, 0, 0) to NDC (−1, +1), (W, H, 0) to (+1, −1) and (W/2, H/2, 0) to (0, 0). A point at z = −10 maps farther from the centre than the same point at z = 0.
- [ ] `shaderSource("X", any)` returns `"#version 410 core\nX"` on desktop and `"#version 300 es\nprecision highp float;\nX"` on GLES, for both values of the `fragment` flag.
- [ ] A broken vertex body appends `"vertex: "` + driver log, the fragment body is still compiled (`"fragment: "` + log if it is also broken), and the result is 0 with no `"link: "` text. A link failure appends `"link: "` + log. Messages from consecutive calls are concatenated without separators.
- [ ] After a successful link, both shader objects have been deleted (flagged) but stay attached.
- [ ] `Texture::createRgba(…, true)` generates mipmaps and uses `GL_LINEAR_MIPMAP_LINEAR` / `GL_LINEAR`; with `false`, min and mag are both `GL_LINEAR`. Wrap is `GL_CLAMP_TO_EDGE`, `GL_UNPACK_ALIGNMENT` is 4 afterwards, and `width`/`height` are set.
- [ ] `RenderTarget::ensure` called twice with the same arguments returns `true` the second time without any GL call. Changing only `withDepth` recreates the target. `ensure(0, 100, false)` destroys it and returns `false` with every field 0.
- [ ] After a (re)creating `ensure`, `GL_FRAMEBUFFER_BINDING` is 0. The colour attachment is `GL_RGBA8` with `GL_LINEAR` and clamp, and depth (if requested) is a `GL_DEPTH_COMPONENT24` renderbuffer. An incomplete framebuffer returns `false` and leaves the target empty.
- [ ] `glVersionString()` returns `"unknown"` when `glGetString(GL_VERSION)` returns null.

**GlyphAtlas**
- [ ] On a GPU whose maximum texture size is at least 2048, `init(2048)` leaves an R8 2048² texture with no swizzle, zero everywhere except the 4×4 block of 255 at (0, 0). It also gives `generation() == 1`, `fill() == 5/2048` and `whiteU() == whiteV() == 2/2048`. `init(4096)` with a maximum texture size of 2048 gives `size() == 2048`.
- [ ] Shelf rule after a reset:
  - A glyph 4 px tall (padded height 5) goes onto the white block's shelf at (5, 0).
  - A glyph 10 px tall (padded 11) opens a shelf at y = 5 that is 11 tall; `fill()` becomes 16/size.
  - An 8 px glyph (padded 9: 9 ≤ 11 ≤ 9 + 3 + 2) and a 6 px glyph (padded 7: 11 ≤ 7 + 2 + 2) join that shelf.
  - A 5 px glyph (padded 6: limit 10 < 11, and 5 < 6 for the first shelf) opens a new shelf.
  - Glyphs on one shelf are placed `w + 1` px apart.
- [ ] Among the shelves that fit, the lowest one wins (the earliest on ties). A glyph wider than the atlas, or one that needs a new shelf past the bottom, fails.
- [ ] Sizes 16.1 and 15.9 px share cache entries (`lround(64.4) == lround(63.6) == 64`); 16.13 px (65) does not. Different bins or faces never share entries.
- [ ] A glyph is rasterised at `sizeQ/4` px with `FT_LOAD_TARGET_LIGHT | FT_LOAD_NO_BITMAP` and `FT_RENDER_MODE_NORMAL`. Bin b translates the outline by `b*16` 26.6 units (b/4 px to the right) before rendering.
- [ ] An entry's UVs are exactly `(x/size, y/size)`–`((x+w)/size, (y+h)/size)`. `left`/`top` are FreeType's `bitmap_left`/`bitmap_top`.
- [ ] A space (empty bitmap) or a glyph FreeType fails on is cached with `w == h == 0` and never re-rasterised in the same generation.
- [ ] When a glyph does not fit, `get` returns `nullptr`, `overflowed()` becomes true and nothing is cached. Afterwards cache hits still succeed, while misses return `nullptr` without FreeType calls.
- [ ] `reset()` empties the cache and shelves, clears the overflow flag, increments `generation()` and re-uploads the white block, but does not clear the texture.

**Renderer2D**
- [ ] The vertex stride is 20 bytes, with attributes at offsets 0, 8 and 16; colour is four normalised unsigned bytes, R first.
- [ ] After `init` the index buffer holds 4096 quads (24 576 `GL_UNSIGNED_INT` indices, pattern `4q, 4q+1, 4q+2, 4q+2, 4q+3, 4q`). A batch of 5000 quads grows it to 8192 quads.
- [ ] All `rect`/`gradientH`/`gradientV`/`text` quads between two flushes are drawn by a single `glDrawElements` with `uMode = 0`, the atlas on unit 0 and `uGamma` = the current text gamma.
- [ ] `image()` flushes first, then draws one quad with `uMode` 1 (or 2 when `mono`) from texture unit 0. `setTextGamma` with a new value flushes; with the same value it does nothing. `begin()` discards unflushed quads.
- [ ] `begin()` sets the viewport to (0, 0, w, h), disables depth test and culling, enables blending and sets `glBlendFuncSeparate(SRC_ALPHA, ONE_MINUS_SRC_ALPHA, ONE, ONE_MINUS_SRC_ALPHA)`.
- [ ] `rect`/`gradient*` with `w <= 0` or `h <= 0` append nothing. `image` never skips.
- [ ] A solid rect samples the white block: its fragment alpha equals the colour's packed alpha/255 for any gamma.
- [ ] `gradientH(x, y, w, h, A, B)` has colour A on the left edge and B on the right edge, constant along y; `gradientV` has the top colour on the top edge and the bottom colour on the bottom edge, constant along x.
- [ ] In text mode, coverage c gives alpha `vColor.a · c^uGamma`.
- [ ] A mono image of a pure-red opaque texel with a white tint renders grey 0.299. A normal image renders texel × tint.
- [ ] `text` with baseline 100.5 puts the glyphs on baseline 101.
- [ ] Glyph bins by pen x: at 10.3 the quad starts at `10 + left` with bin 1; at 10.9 at `11 + left` with bin 0; at 10.125 bin 1; at 10.625 bin 3. Every glyph quad has integer corners and the bitmap's exact size.
- [ ] `drawText` returns `run.advance * size`; `textWidth` returns the same value for the same arguments without drawing.

**PageTurn**
- [ ] The mesh has 97 × 41 vertices with `aUV = (c/96, r/40)` and 23 040 indices of the form `{a, b, e, e, d, a}`. The under quad has 6 vertices: `{0,0, W,0, W,H, W,H, 0,H, 0,0}`.
- [ ] `draw` with `width <= 0` or `height <= 0` issues no GL call. `t` outside [0, 1] is clamped, and e(t) is the cubic ease-in-out (e(0.25) = 0.0625, e(0.75) = 0.9375).
- [ ] Single page, t = 0: no vertex is displaced (every d ≤ −2). The frame equals `sheetTex` 1:1, except for the fold darkening near the bottom-right corner, where d ≥ −1.2·max(R, 1). At the corner itself the factor is `1 − 0.18·(1 − 2/(1.2·R))`.
- [ ] Single page, t = 1: no sheet fragment is inside the viewport and the cast shadow is zero everywhere, so the frame equals `underTex` 1:1.
- [ ] Single page: θ = 0.16 rad and R = max(18, 0.085·min(W, H)) throughout. The bottom-right corner lifts first, and the page leaves to the left.
- [ ] Front-side light is `mix(0.78, 1, facing)` and back-side light is `mix(0.84, 1, −facing)`. The turned-over flat part has light 1.0. The fold darkening reaches 18 % at the fold line over a width of 1.2·max(R, 1).
- [ ] Single-page back side = `mix(paper, front texel at the same page position, backPrint)`. With `backPrint` 0, it is the plain paper colour times the back light.
- [ ] The cast shadow on the page underneath multiplies by 0.5 for d ≤ R and fades as `1 − 0.5·s²` over 2.5·max(R, 4) px. `shadows = false` removes it and the fold darkening.
- [ ] A spread is active only for 0 < spineX < W. The mesh covers [spineX, W], and r0 uses W − spineX. Left of the spine pass 1 shows `sheetTex` unshaded.
- [ ] Spread, e = 1: the fold line is the vertical line x = spineX with radius uniform 0. The sheet lies mirrored about the spine at z = −0.002, with its back sampling `underTex` at ((2·spineX − x)/W, v). The strip [spineX, spineX + 10) still carries the residual cast shadow.
- [ ] Camera: eye (W/2, H/2, −1.8H), centre (W/2, H/2, 0), up (0, −1, 0), fovy = 2·atan(1/3.6), aspect W/H, near 0.36H, far 5.4H.
- [ ] Pass 1 runs with depth test (and hence depth writes) off. Then the depth buffer is cleared, the depth test is enabled with `GL_LEQUAL` and the sheet is drawn without blending.
- [ ] After `draw`: depth test off, blending off, texture unit 1 unbound, unit 0 active and bound to `sheetTex`, VAO 0.
- [ ] Texture unit 0 = `sheetTex` (`uTexA`, `uFront`) and unit 1 = `underTex` (`uTexB`, `uBack`), in both passes.
