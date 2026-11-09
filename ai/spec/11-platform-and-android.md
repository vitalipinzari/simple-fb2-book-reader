# 11 — Platform layer and the Android build

Scope: what differs between Windows, Android and other systems — the platform layer (`src/platform/Platform.cpp`,
verbatim), the Android Gradle project, manifest and resources (verbatim), the two Java classes (verbatim), SDL's
Java glue (upstream, unmodified), the Gradle wrapper, the release signing key, `build-android.ps1`, and how to run
and drive the app on an emulator or device. Everything native is the same C++ code as on Windows; the only
compile-time switches are `_WIN32`, `__ANDROID__` / `LL_USE_GLES` (GLES headers, see `src/render/Gl.h`) and the
`#ifdef __ANDROID__` defaults in `Settings.h`.

## 1. Platform layer (`src/platform/Platform.{h,cpp}`, verbatim)

| Function | Windows | Android | Other (generic fallback) |
|---|---|---|---|
| `isTouchFirst()` | false | true (also iOS) | false |
| `assetsDir()` | `SDL_GetBasePath()` + `assets/` | `""` (SDL reads APK assets by relative path) | as Windows |
| `prefDir()` | `SDL_GetPrefPath("", "Lanternleaf")` = `%APPDATA%\Lanternleaf\` | the same call = internal files dir | same call |
| `defaultSearchRoots()` | SDL user folders Downloads, Documents, Desktop that exist (trailing separators stripped) | on the primary volume: `Download`, `Documents`, `Books`, `Telegram`, `Android/media/org.telegram.messenger/Telegram/Telegram Documents` that exist; else `<primary>/Download` | as Windows |
| `driveRoots()` | `GetLogicalDrives()`: fixed, removable and RAM disks as `X:\` | `storageRoots()` from Java (device storage first, then SD cards; fallback `/storage/emulated/0`) | `/` |
| `readingFonts()` | Georgia, Palatino Linotype, Cambria (`cambria.ttc`), Constantia, Times New Roman, Segoe UI, Calibri, Verdana from `%WINDIR%\Fonts` (regular must exist) | Noto Serif from `/system/fonts/` | none |
| `fallbackFontFiles()` | `segoeui.ttf`, `seguisym.ttf`, `arial.ttf` | `Roboto-Regular.ttf`, `NotoSansSymbols-Regular-Subsetted.ttf`, `NotoSansSymbols-Regular-Subsetted2.ttf` | DejaVuSans |
| `hasStorageAccess()` / `requestStorageAccess()` | true / no-op | JNI `hasAllFilesAccess()` / `requestAllFilesAccess()` | true / no-op |
| brightness | `canSetScreenBrightness()` false, `systemScreenBrightness()` 1.0, set is a no-op | true; JNI `systemScreenBrightness()` (fallback 0.5) and `setScreenBrightness(float)` | as Windows |
| `isCloudPlaceholder()` | attributes `OFFLINE`, `RECALL_ON_DATA_ACCESS` (0x00400000) or `RECALL_ON_OPEN` (0x00040000) | false | false |
| `canRevealFiles()` / `revealInFileManager()` | true / `explorer.exe /select,"<path>"` | false / no-op | true / `SDL_OpenURL("file://<dir>")` |
| `loadAsset()` | `SDL_LoadFile(assetsDir() + rel)` | same (APK assets) | same |
| `systemDescription()` | `SDL_GetPlatform()` + ` x64` / ` arm64` … | `Android (API <n>)` + ` arm64` / ` x64` … | as Windows |

JNI: a small RAII helper takes `SDL_GetAndroidJNIEnv()` and `SDL_GetAndroidActivity()`, looks up **static**
methods of the activity's class, calls them and clears/describes any Java exception. The Java side therefore
needs exactly these static methods of `app.lanternleaf.reader.LanternleafActivity`:

| Java method | JNI signature | Used for |
|---|---|---|
| `boolean hasAllFilesAccess()` | `()Z` | storage access state (re-checked by the app about every second while it matters, spec 09/10) |
| `void requestAllFilesAccess()` | `()V` | the *Allow access* buttons and the first-start prompt |
| `float systemScreenBrightness()` | `()F` | where a brightness swipe starts when the app follows the system |
| `void setScreenBrightness(float)` | `(F)V` | the window's own brightness (negative = follow the system) |
| `String storageRoots()` | `()Ljava/lang/String;` | storage volumes, one per line |

## 2. The Android project (verbatim files in `ai/files/03-android-project.md`)

- **Gradle**: `settings.gradle` (repositories google/mavenCentral/gradlePluginPortal, `FAIL_ON_PROJECT_REPOS`,
  root project "Lanternleaf", module `:app`), root `build.gradle` (AGP `com.android.application` 9.3.2, `apply
  false`), `gradle.properties` (`-Xmx3g -Dfile.encoding=UTF-8`, parallel, caching, non-transitive R classes),
  `gradle/wrapper/gradle-wrapper.properties` (Gradle 9.5.0 bin distribution).
- **`app/build.gradle`**: reads `local.properties` (`vcpkg.dir`) unless `VCPKG_ROOT` is set; reads `../VERSION`
  for `versionName` and `versionCode = major·10000 + minor·100 + patch`; optional `keystore.properties` for the
  release signing config (falls back to the debug key when missing); `namespace`/`applicationId`
  `app.lanternleaf.reader`, `compileSdk 36` + `compileSdkMinor 1`, `ndkVersion "28.2.13676358"`, `minSdk 28`
  (vcpkg's Android triplets build for API 28; SDL3 then uses libc's iconv and nl_langinfo), `targetSdk 36`, ABIs
  `arm64-v8a` and `x86_64`, CMake arguments `-DANDROID_STL=c++_static -DLL_BUILD_TESTS=OFF` (+
  `-DVCPKG_ROOT=<path with forward slashes>`), `externalNativeBuild.cmake.path = ../../CMakeLists.txt` with CMake
  `3.22.1`, `assets.srcDirs = ["../../assets"]` (the shared asset folder), Java 17, lint never aborts, release
  not minified; the `stageReleaseApk` copy task (spec 02 § 5).
- **`AndroidManifest.xml`**: `installLocation auto`; requires GLES 3.0 (`glEsVersion 0x00030000`); touchscreen and
  PC features optional; permissions `MANAGE_EXTERNAL_STORAGE` (Android 11+ *All files access*) and
  `READ_EXTERNAL_STORAGE` up to API 32; application label/icon/round icon, backup allowed, `AppTheme`,
  `enableOnBackInvokedCallback false` (the Back key reaches SDL as `SDLK_AC_BACK`), hardware acceleration,
  legacy external storage, category productivity. One activity `.LanternleafActivity`: `singleInstance`, retains
  task state, `screenOrientation fullUser`, handles all configuration changes itself (layout direction, locale,
  grammatical gender, font scale/weight, orientation, UI mode, screen layout/size, smallest size, keyboard,
  keyboard hidden, navigation), minimal post-processing, soft input `stateAlwaysHidden|adjustNothing`, exported;
  intent filters MAIN/LAUNCHER and VIEW/SEND (DEFAULT + BROWSABLE) for `content:` and `file:` schemes with the
  FB2/TXT/XML/ZIP/PDF MIME types listed in the file.
- **Resources**: `values/strings.xml` (`app_name` "Lanternleaf"), `values/colors.xml` (`window_background` and
  `ic_launcher_background` `#FF16110D`), `values/styles.xml` (`AppTheme` = `android:Theme.Material.NoActionBar`
  with that colour for the window, status bar and navigation bar, cutout mode `shortEdges`),
  `mipmap-anydpi-v26/ic_launcher.xml` (adaptive icon: colour background, PNG foreground, the foreground also as
  monochrome layer), launcher PNGs in five densities (spec 12).

## 3. Java

**`LanternleafActivity extends SDLActivity`** (verbatim): `getLibraries()` returns only `"main"` (SDL3 is linked
statically into `libmain.so`); `createSDLSurface()` returns a `LanternleafSurface`; `onCreate()` stores the
singleton, turns the start intent into a book path (before `super.onCreate`, so the path can be appended to the
arguments) and creates the app's external files folder; `onNewIntent()` turns a later intent into a path and
hands it to native code with `SDLActivity.onNativeDropFile()` (arrives as `SDL_EVENT_DROP_FILE`);
`getArguments()` splits the intent extra `args` (double quotes group, white space separates; no escape
characters) and appends the start book. `takeBookFromIntent()` takes `getData()` or, for `ACTION_SEND`,
`EXTRA_STREAM`, clears the intent's data (so SDL does not forward a raw URI), returns `file:` paths directly and
copies `content:` URIs to `<filesDir>/opened/<display name>` (name from `OpenableColumns.DISPLAY_NAME`, default
"book", characters `\/:*?"<>|` replaced by `_`, 64 KiB copy buffer) so they can be reopened after a restart. The
static helpers of § 1: `hasAllFilesAccess()` (API ≥ 30: `Environment.isExternalStorageManager()`, else the
`READ_EXTERNAL_STORAGE` grant), `requestAllFilesAccess()` (on the UI thread: API < 30 requests the permission
with request code 4711; otherwise tries `ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION` for the package, then
`ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION`, then `ACTION_APPLICATION_DETAILS_SETTINGS`, first that starts wins),
`systemScreenBrightness()` (`Settings.System.SCREEN_BRIGHTNESS / 255`, clamped 0…1, fallback 0.5),
`setScreenBrightness(v)` (on the UI thread: the window's `screenBrightness`, `BRIGHTNESS_OVERRIDE_NONE` for
v < 0, else clamped 0…1), `storageRoots()` (the part before `/Android/data/` of every `getExternalFilesDirs(null)`
entry, newline-separated; fallback `Environment.getExternalStorageDirectory()`).

**`LanternleafSurface extends SDLSurface`** (verbatim): on API ≥ 30 reports as safe area only the system bars and
the display cutout (`onNativeInsetsChanged(left, right, top, bottom)` after SDL's own handling) — SDL's default
safe area also excludes the 30 dp back-gesture zones at both edges, which a reader does not need to avoid.

**SDL's Java glue** — the twelve files `HIDDevice.java`, `HIDDeviceBLESteamController.java`,
`HIDDeviceManager.java`, `HIDDeviceUSB.java`, `SDL.java`, `SDLActivity.java`, `SDLAudioManager.java`,
`SDLControllerManager.java`, `SDLDummyEdit.java`, `SDLInputConnection.java`, `SDLSensorManager.java`,
`SDLSurface.java` are copied **unmodified** from SDL **3.4.18**'s `android-project/app/src/main/java/org/libsdl/app/`
into `android/app/src/main/java/org/libsdl/app/`; next to them sits SDL's `LICENSE.txt` (verbatim in files/03).
Take them from the release archive `https://github.com/libsdl-org/SDL/archive/refs/tags/release-3.4.18.tar.gz`
(vcpkg keeps the same archive as `libsdl-org-SDL-release-3.4.18.tar.gz` in its download cache, e.g.
`%LOCALAPPDATA%\vcpkg\downloads`). The version must equal the vcpkg `sdl3` port: `SDLActivity.java` declares
`SDL_MAJOR_VERSION = 3`, `SDL_MINOR_VERSION = 4`, `SDL_MICRO_VERSION = 18` and refuses to run against a different
native SDL.

## 4. Gradle wrapper

`gradlew`, `gradlew.bat` and `gradle/wrapper/gradle-wrapper.jar` are the standard Gradle 9.5.0 wrapper files.
Generate them in `android/` with a Gradle 9.5.0 distribution (`https://services.gradle.org/distributions/gradle-9.5.0-bin.zip`,
unpacked to a temp folder outside the repository): `<gradle-9.5.0>\bin\gradle.bat wrapper --gradle-version 9.5.0
--distribution-type bin`, then write the verbatim `gradle/wrapper/gradle-wrapper.properties` over the generated
one (`unpack_files.py` does). The reference files were 8 654 (`gradlew`), 2 846 (`gradlew.bat`) and 48 462 bytes
(`gradle-wrapper.jar`, Implementation-Title "Gradle Wrapper").

## 5. Release signing

Release APKs are signed with `android/keystore/lanternleaf-release.jks`, described by `android/keystore.properties`
(both git-ignored; back them up — updates of an installed app must be signed with the same key; without them
Gradle signs release builds with the debug key). The original key is private, so create your own with the JDK's
`keytool` (Android Studio's `jbr\bin\keytool.exe`):

```powershell
New-Item -ItemType Directory -Force android\keystore | Out-Null
& "<Android Studio>\jbr\bin\keytool.exe" -genkeypair -v -storetype PKCS12 `
  -keystore android\keystore\lanternleaf-release.jks -alias lanternleaf `
  -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Lanternleaf, O=<your name>"
```

`android/keystore.properties` (ASCII; paths relative to `android/`):

```properties
# Release signing key for Lanternleaf (do not commit, do not lose: updates must be signed with the same key)
storeFile=keystore/lanternleaf-release.jks
storePassword=<the store password>
keyAlias=lanternleaf
keyPassword=<the key password; for PKCS12 the same as the store password>
```

An APK signed with a new key cannot update an installation of the original APK on the same device (uninstall
that first); that is the only observable consequence.

## 6. `build-android.ps1` (verbatim)

`./build-android.ps1 [-Config Release|Debug] [-Install] [-Run] [-Clean]`:

1. Finds the SDK (`ANDROID_HOME`, `ANDROID_SDK_ROOT`, `%LOCALAPPDATA%\Android\Sdk`), requires
   `ndk\28.2.13676358`, finds a JDK (`JAVA_HOME`, then `D:\Program Files\Android Studio\jbr`,
   `C:\Program Files\Android\Android Studio\jbr`, `%LOCALAPPDATA%\Programs\Android Studio\jbr`), finds vcpkg
   (`VCPKG_ROOT` or Visual Studio's `VC\vcpkg` through vswhere) and puts Visual Studio's Git on `PATH`; exports
   `JAVA_HOME`, `ANDROID_HOME`, `ANDROID_NDK_HOME`, `VCPKG_ROOT`.
2. `vcpkg install --triplet arm64-android` and `x64-android` into `build\vcpkg_android\<triplet>` (manifest mode,
   `--no-print-usage`). HarfBuzz is not in these trees (vcpkg's Meson build rejects Windows paths when
   cross-compiling); CMake builds it from `harfbuzz.cc` instead (`cmake/HarfBuzzAmalgamated.cmake`: uses
   `build/downloads/harfbuzz-14.6.0.tar.gz` or vcpkg's cached `harfbuzz-harfbuzz-14.6.0.tar.gz` if its SHA-256
   matches, else downloads `https://github.com/harfbuzz/harfbuzz/archive/14.6.0.tar.gz` with the hash check;
   extracts only `src/`; static, PIC, `HAVE_PTHREAD=1`; alias `harfbuzz::harfbuzz`).
3. Writes `android\local.properties` (`sdk.dir=…`, `vcpkg.dir=…`, backslashes doubled, ASCII).
4. Runs `gradlew.bat assemble<Config> --console=plain` in `android\` (after `clean` with `-Clean`); Gradle builds
   `libmain.so` for both ABIs through the root `CMakeLists.txt`, packages `assets/`, signs, and `stageReleaseApk`
   copies the APK to `release\Android\Lanternleaf-<version>.apk` (Debug: `android\app\build\outputs\apk\debug\app-debug.apk`).
5. `-Install` / `-Run`: `adb install -r <apk>`, `adb shell am start -n app.lanternleaf.reader/.LanternleafActivity`.

With `android/local.properties` written once, the `android` folder also opens in Android Studio.

## 7. Running and driving the app on an emulator or device

These are the procedures the device checks in spec 13 use (reference: a Pixel 8a AVD, Android 14, 1080×2400,
GLES 3.1 on the host GPU).

- Start headless: `emulator -avd <avd> -no-snapshot -no-window -no-audio -gpu host -port 5580` (serial
  `emulator-5580`). If the AVD holds someone's own data, add `-read-only` so nothing persists. Stop with
  `adb -s emulator-5580 emu kill`.
- After `adb install`, wait about 8 s before starting the app: late package processing otherwise kills the
  freshly started process (looks like a black screen / "activity finished").
- Release APKs are not debuggable (`run-as` does not work). Use a shared-storage settings folder so settings, the
  log and screenshots are readable with adb:
  `adb shell am start -n app.lanternleaf.reader/.LanternleafActivity --es args '--settings-dir
  /sdcard/Android/data/app.lanternleaf.reader/files/test/ --screenshot /sdcard/Android/data/app.lanternleaf.reader/files/test/x.png …'`.
  Do not create that folder with adb (a shell-created folder is not writable by the app); delete it and let the
  app create it. Paths with spaces break the argument split.
- Storage permission without tapping: `adb shell appops set --uid app.lanternleaf.reader MANAGE_EXTERNAL_STORAGE allow`.
- Right after boot, `adb push` to `/sdcard` can fail with "Operation not permitted" until storage is mounted;
  retry a few seconds later.
- Screenshots: `adb shell screencap -p /sdcard/<name>.png` then `adb pull` (redirecting `exec-out screencap` in
  PowerShell corrupts the PNG).
- Landscape: `adb shell cmd window user-rotation lock 1` (`lock 0` = portrait); after install/start check that
  `adb shell dumpsys window displays` shows `cur=2400x1080` before tapping by coordinates.
- Two-finger pinch: shell `sendevent` is blocked by SELinux; use the emulator console (TCP `127.0.0.1:5580`,
  `auth <token from ~/.emulator_console_auth_token>`, then `event send EV_ABS:ABS_MT_SLOT:0 …` sequences ending
  in `EV_SYN:0:0`; the axes run 0…32767, not pixels).
- Typing: tap the on-screen keyboard keys with `adb shell input tap` (`adb shell input text` races Gboard); number
  fields get the number pad, where `input keyevent` 7…16 (digits) and 66 (Enter) work once the field is focused.
- Leaving with Back (`adb shell input keyevent 4`) saves the position; the log's last line then reports the
  instant page turns (spec 09).

## Checklist

- `./build-android.ps1` produces `release/Android/Lanternleaf-0.7.0.apk`; `aapt2 dump badging` (or Android
  Studio's APK analyser) shows package `app.lanternleaf.reader`, versionCode 700, versionName 0.7.0, minSdk 28,
  targetSdk 36, native code `arm64-v8a` and `x86_64`, and the assets `fonts/…`, `hyphenation/…`, `licenses/…`.
- `apksigner verify --print-certs` shows your release certificate (not the debug key) when
  `keystore.properties` exists.
- The app starts in immersive full screen on the Day theme with the welcome text, asks once for *All files
  access*, and its About panel shows `Android (API <n>) arm64` or `… x64`.
- "Open with Lanternleaf" from a file manager opens an FB2, a `.fb2.zip` and a TXT; the book reopens after the
  app is closed and started again (it was copied to `files/opened/`).
- Brightness swipes on the left part of the page change only Lanternleaf's window brightness.
