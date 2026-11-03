# Android project (Gradle, manifest, resources, Java)

The Gradle project in android/. The SDL Java glue in android/app/src/main/java/org/libsdl/app/ is not listed: it is the unmodified android-project/app/src/main/java/org/libsdl/app/ folder of SDL 3.4.18 (see ai/spec/11-platform-and-android.md); only the licence file that sits next to it is listed here. The launcher PNGs come from tools/make_icon.py, the Gradle wrapper (gradlew, gradlew.bat, gradle-wrapper.jar) from `gradle wrapper`.

Reproduce every file below **byte for byte** at the path in its heading. The fenced block holds the complete content (the fences are not part of the file); the line under each heading gives what a block cannot show: encoding, line endings and whether the file ends with a newline. `ai/files/checksums.sha256` has the SHA-256 of each file for checking.

| File | Bytes | SHA-256 |
|---|---:|---|
| `android/settings.gradle` | 330 | `833144dd7b2a60f2…` |
| `android/build.gradle` | 73 | `350312fd6a380374…` |
| `android/gradle.properties` | 130 | `748f7a9e0472ae96…` |
| `android/gradle/wrapper/gradle-wrapper.properties` | 281 | `c67b97cdfe41822d…` |
| `android/app/build.gradle` | 3657 | `c465e1a467650528…` |
| `android/app/src/main/AndroidManifest.xml` | 3432 | `9c9714e4bc4f1ec0…` |
| `android/app/src/main/res/values/colors.xml` | 177 | `8d507e36dc70c238…` |
| `android/app/src/main/res/values/strings.xml` | 113 | `5e39e5236ee9e9d5…` |
| `android/app/src/main/res/values/styles.xml` | 563 | `405f3b6701d08110…` |
| `android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml` | 337 | `ddf8416ebdaaa45e…` |
| `android/app/src/main/java/app/lanternleaf/reader/LanternleafActivity.java` | 9670 | `588b02b6c3293b02…` |
| `android/app/src/main/java/app/lanternleaf/reader/LanternleafSurface.java` | 1290 | `3c09edbc6ad6be62…` |
| `android/app/src/main/java/org/libsdl/app/LICENSE.txt` | 884 | `1c040b8271b37e50…` |

## `android/settings.gradle`

ASCII, LF line endings, ends with a newline.

```groovy
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "Lanternleaf"
include ":app"
```

## `android/build.gradle`

ASCII, LF line endings, ends with a newline.

```groovy
plugins {
    id "com.android.application" version "9.3.2" apply false
}
```

## `android/gradle.properties`

ASCII, LF line endings, ends with a newline.

```properties
org.gradle.jvmargs=-Xmx3g -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
android.nonTransitiveRClass=true
```

## `android/gradle/wrapper/gradle-wrapper.properties`

ASCII, LF line endings, ends with a newline.

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.5.0-bin.zip
networkTimeout=10000
retries=0
retryBackOffMs=500
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

## `android/app/build.gradle`

ASCII, LF line endings, ends with a newline.

```groovy
plugins {
    id "com.android.application"
}

// Machine-specific paths (written by ../build-android.ps1, or by hand): sdk.dir, vcpkg.dir.
def localProps = new Properties()
def localFile = rootProject.file("local.properties")
if (localFile.exists()) {
    localFile.withInputStream { localProps.load(it) }
}
def vcpkgRoot = System.getenv("VCPKG_ROOT") ?: localProps.getProperty("vcpkg.dir")

// One version for every platform: the VERSION file at the repository root (e.g. 0.2.0 -> versionCode 200).
def appVersion = rootProject.file("../VERSION").text.trim()
def versionParts = appVersion.tokenize('.').collect { it as int }
def appVersionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]

// Release signing key (kept out of version control). Without it, release builds use the debug key.
def keystoreProps = new Properties()
def keystoreFile = rootProject.file("keystore.properties")
if (keystoreFile.exists()) {
    keystoreFile.withInputStream { keystoreProps.load(it) }
}

android {
    namespace = "app.lanternleaf.reader"
    compileSdk = 36
    compileSdkMinor = 1
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "app.lanternleaf.reader"
        // Android 9+: vcpkg's arm64-android / x64-android triplets build the libraries for API level 28
        // (SDL3 then uses libc's iconv and nl_langinfo, which older Android versions lack).
        minSdk = 28
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersion
        ndk {
            // Phones and tablets (arm64) plus the x86_64 emulator / Chromebooks.
            abiFilters "arm64-v8a", "x86_64"
        }
        externalNativeBuild {
            cmake {
                arguments "-DANDROID_STL=c++_static",
                          "-DLL_BUILD_TESTS=OFF"
                if (vcpkgRoot != null) {
                    arguments "-DVCPKG_ROOT=" + vcpkgRoot.replace('\\', '/')
                }
            }
        }
    }

    signingConfigs {
        release {
            if (keystoreFile.exists()) {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            minifyEnabled = false
            signingConfig = keystoreFile.exists() ? signingConfigs.release : signingConfigs.debug
        }
    }

    externalNativeBuild {
        cmake {
            // The same CMakeLists.txt as the Windows build; it builds libmain.so for Android.
            path = file("../../CMakeLists.txt")
            version = "3.22.1"
        }
    }

    sourceSets {
        main {
            // Fonts and hyphenation patterns are shared with the desktop build.
            assets.srcDirs = ["../../assets"]
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

// Every release build is copied to release/Android/Lanternleaf-<version>.apk (next to release/Windows/).
def stageReleaseApk = tasks.register("stageReleaseApk", Copy) {
    from(layout.buildDirectory.dir("outputs/apk/release")) {
        include "*.apk"
    }
    into(rootProject.file("../release/Android"))
    rename { "Lanternleaf-${appVersion}.apk" }
}
tasks.matching { it.name == "assembleRelease" }.configureEach {
    finalizedBy stageReleaseApk
}
```

## `android/app/src/main/AndroidManifest.xml`

ASCII, LF line endings, ends with a newline.

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools"
    android:installLocation="auto">

    <!-- The reader draws everything with OpenGL ES 3.0. -->
    <uses-feature android:glEsVersion="0x00030000" android:required="true" />
    <uses-feature android:name="android.hardware.touchscreen" android:required="false" />
    <uses-feature android:name="android.hardware.type.pc" android:required="false" />

    <!-- Finding books anywhere on the device (Downloads, Telegram, SD cards ...):
         Android 11+ needs "All files access", older versions the storage permission. -->
    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE"
        tools:ignore="ScopedStorage" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
        android:maxSdkVersion="32" />

    <application
        android:label="@string/app_name"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher"
        android:allowBackup="true"
        android:theme="@style/AppTheme"
        android:enableOnBackInvokedCallback="false"
        android:hardwareAccelerated="true"
        android:requestLegacyExternalStorage="true"
        android:appCategory="productivity"
        tools:targetApi="36">

        <activity
            android:name=".LanternleafActivity"
            android:label="@string/app_name"
            android:alwaysRetainTaskState="true"
            android:launchMode="singleInstance"
            android:screenOrientation="fullUser"
            android:configChanges="layoutDirection|locale|grammaticalGender|fontScale|fontWeightAdjustment|orientation|uiMode|screenLayout|screenSize|smallestScreenSize|keyboard|keyboardHidden|navigation"
            android:preferMinimalPostProcessing="true"
            android:windowSoftInputMode="stateAlwaysHidden|adjustNothing"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
            <!-- "Open with Lanternleaf" for FB2, TXT and zipped FB2 from file managers, browsers, messengers. -->
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <action android:name="android.intent.action.SEND" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="content" />
                <data android:scheme="file" />
                <data android:mimeType="application/x-fictionbook+xml" />
                <data android:mimeType="application/x-fictionbook" />
                <data android:mimeType="application/fb2" />
                <data android:mimeType="application/x-fb2" />
                <data android:mimeType="text/fb2+xml" />
                <data android:mimeType="text/plain" />
                <data android:mimeType="text/xml" />
                <data android:mimeType="application/xml" />
                <data android:mimeType="application/zip" />
                <data android:mimeType="application/x-zip-compressed" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

## `android/app/src/main/res/values/colors.xml`

ASCII, LF line endings, ends with a newline.

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="window_background">#FF16110D</color>
    <color name="ic_launcher_background">#FF16110D</color>
</resources>
```

## `android/app/src/main/res/values/strings.xml`

ASCII, LF line endings, ends with a newline.

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Lanternleaf</string>
</resources>
```

## `android/app/src/main/res/values/styles.xml`

ASCII, LF line endings, ends with a newline.

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- The whole UI is drawn with OpenGL: no action bar, a dark window behind the first frame. -->
    <style name="AppTheme" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@color/window_background</item>
        <item name="android:statusBarColor">@color/window_background</item>
        <item name="android:navigationBarColor">@color/window_background</item>
        <item name="android:windowLayoutInDisplayCutoutMode">shortEdges</item>
    </style>
</resources>
```

## `android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`

ASCII, LF line endings, ends with a newline.

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
```

## `android/app/src/main/java/app/lanternleaf/reader/LanternleafActivity.java`

ASCII, LF line endings, ends with a newline.

```java
package app.lanternleaf.reader;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.util.Log;
import android.view.WindowManager;

import org.libsdl.app.SDLActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Lanternleaf on Android: SDL3 runs the native reader (libmain.so); this class adds what only Java can do:
 * "Open with" from other apps, the storage permission, the list of storage volumes and the window's
 * screen brightness.
 */
public class LanternleafActivity extends SDLActivity {
    private static final String TAG = "Lanternleaf";
    private static LanternleafActivity sInstance;

    /** A book handed over by another app at start-up (already copied to a readable path). */
    private String mStartBook;

    @Override
    protected String[] getLibraries() {
        // SDL3 is linked statically into libmain.so.
        return new String[] { "main" };
    }

    @Override
    protected org.libsdl.app.SDLSurface createSDLSurface(android.content.Context context) {
        return new LanternleafSurface(context);  // safe area without the gesture zones
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        sInstance = this;
        mStartBook = takeBookFromIntent(getIntent());
        getExternalFilesDir(null);  // make sure the app's own folder on shared storage exists
        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        String book = takeBookFromIntent(intent);
        if (book != null) {
            SDLActivity.onNativeDropFile(book);  // arrives as SDL_EVENT_DROP_FILE
        }
    }

    @Override
    protected String[] getArguments() {
        List<String> args = new ArrayList<>();
        Intent intent = getIntent();
        // Automation: adb shell am start -n app.lanternleaf.reader/.LanternleafActivity --es args "--screenshot ..."
        String extra = intent != null ? intent.getStringExtra("args") : null;
        if (extra != null) {
            args.addAll(splitArguments(extra));
        }
        if (mStartBook != null) {
            args.add(mStartBook);
        }
        return args.toArray(new String[0]);
    }

    /**
     * Turns an ACTION_VIEW / ACTION_SEND intent into a file path the native code can read. content:// books
     * are copied into the app's private storage, so they can also be reopened after a restart. The intent's
     * data is cleared so SDL does not forward the raw URI path.
     */
    private String takeBookFromIntent(Intent intent) {
        if (intent == null) {
            return null;
        }
        Uri uri = intent.getData();
        if (uri == null && Intent.ACTION_SEND.equals(intent.getAction())) {
            uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        }
        if (uri == null) {
            return null;
        }
        intent.setData(null);
        try {
            if ("file".equals(uri.getScheme())) {
                return uri.getPath();
            }
            if ("content".equals(uri.getScheme())) {
                return copyToPrivateStorage(uri);
            }
        } catch (Exception e) {
            Log.w(TAG, "Cannot open " + uri, e);
        }
        return null;
    }

    private String copyToPrivateStorage(Uri uri) throws IOException {
        String name = null;
        try (Cursor c = getContentResolver().query(uri, new String[] { OpenableColumns.DISPLAY_NAME }, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                name = c.getString(0);
            }
        } catch (Exception ignored) {
        }
        if (name == null || name.isEmpty()) {
            name = "book";
        }
        name = name.replaceAll("[\\\\/:*?\"<>|]", "_");
        File dir = new File(getFilesDir(), "opened");
        if (!dir.exists() && !dir.mkdirs()) {
            throw new IOException("cannot create " + dir);
        }
        File out = new File(dir, name);
        try (InputStream in = getContentResolver().openInputStream(uri);
             OutputStream os = new FileOutputStream(out)) {
            if (in == null) {
                throw new IOException("no data");
            }
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) {
                os.write(buf, 0, n);
            }
        }
        return out.getAbsolutePath();
    }

    private static List<String> splitArguments(String s) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean quoted = false;
        boolean any = false;
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == '"') {
                quoted = !quoted;
                any = true;
            } else if (Character.isWhitespace(ch) && !quoted) {
                if (any) {
                    out.add(cur.toString());
                    cur.setLength(0);
                    any = false;
                }
            } else {
                cur.append(ch);
                any = true;
            }
        }
        if (any) {
            out.add(cur.toString());
        }
        return out;
    }

    // ---- called from native code (src/platform/Platform.cpp) ---------------------------------

    /** May the reader open books anywhere on the shared storage? */
    public static boolean hasAllFilesAccess() {
        LanternleafActivity a = sInstance;
        if (a == null) {
            return false;
        }
        if (Build.VERSION.SDK_INT >= 30) {
            return Environment.isExternalStorageManager();
        }
        return a.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED;
    }

    /**
     * Asks for access to the books on the shared storage: Android 11+ opens the system "All files access"
     * screen for this app (falling back to the list of all apps, then to the app's info page, which some
     * device makers use instead); older versions show the storage permission dialog.
     */
    public static void requestAllFilesAccess() {
        final LanternleafActivity a = sInstance;
        if (a == null) {
            return;
        }
        a.runOnUiThread(() -> {
            if (Build.VERSION.SDK_INT < 30) {
                a.requestPermissions(new String[] { Manifest.permission.READ_EXTERNAL_STORAGE }, 4711);
                return;
            }
            Uri pkg = Uri.parse("package:" + a.getPackageName());
            Intent[] attempts = {
                new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, pkg),
                new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION),
                new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, pkg),
            };
            for (Intent i : attempts) {
                try {
                    a.startActivity(i);
                    return;
                } catch (Exception e) {
                    Log.w(TAG, "Cannot open " + i.getAction(), e);
                }
            }
        });
    }


    /** The system's screen brightness, 0..1 (linear), where a brightness swipe starts from. */
    public static float systemScreenBrightness() {
        LanternleafActivity a = sInstance;
        if (a == null) {
            return 0.5f;
        }
        try {
            int v = Settings.System.getInt(a.getContentResolver(), Settings.System.SCREEN_BRIGHTNESS);
            return Math.max(0f, Math.min(1f, v / 255f));
        } catch (Exception e) {
            return 0.5f;
        }
    }

    /**
     * Sets the brightness of this app's window only (no permission needed; other apps and the system setting
     * are left alone): 0 (darkest) .. 1, or a negative value to follow the system again.
     */
    public static void setScreenBrightness(final float value) {
        final LanternleafActivity a = sInstance;
        if (a == null) {
            return;
        }
        a.runOnUiThread(() -> {
            WindowManager.LayoutParams lp = a.getWindow().getAttributes();
            lp.screenBrightness = value < 0 ? WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
                                            : Math.max(0f, Math.min(1f, value));
            a.getWindow().setAttributes(lp);
        });
    }

    /** Roots of all mounted storage volumes, one per line: the device storage first, then SD cards. */
    public static String storageRoots() {
        LanternleafActivity a = sInstance;
        StringBuilder sb = new StringBuilder();
        if (a != null) {
            for (File f : a.getExternalFilesDirs(null)) {
                if (f == null) {
                    continue;
                }
                String p = f.getAbsolutePath();
                int k = p.indexOf("/Android/data/");
                if (k > 0) {
                    if (sb.length() > 0) {
                        sb.append('\n');
                    }
                    sb.append(p, 0, k);
                }
            }
        }
        if (sb.length() == 0) {
            sb.append(Environment.getExternalStorageDirectory().getAbsolutePath());
        }
        return sb.toString();
    }
}
```

## `android/app/src/main/java/app/lanternleaf/reader/LanternleafSurface.java`

ASCII, LF line endings, ends with a newline.

```java
package app.lanternleaf.reader;

import android.content.Context;
import android.graphics.Insets;
import android.os.Build;
import android.view.View;
import android.view.WindowInsets;

import org.libsdl.app.SDLActivity;
import org.libsdl.app.SDLSurface;

/**
 * SDL's surface, with a reader's idea of the safe area.
 *
 * SDL reports a safe area that also avoids the system gesture zones (30 dp at the left and right edges with
 * gesture navigation), which suits on-screen game controls. Text, the toolbar and the panels only need to avoid
 * what actually covers them: the system bars, when visible, and the display cutout. Everything else (keyboard
 * tracking, input) stays SDL's.
 */
final class LanternleafSurface extends SDLSurface {
    LanternleafSurface(Context context) {
        super(context);
    }

    @Override
    public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
        WindowInsets result = super.onApplyWindowInsets(v, insets);
        if (Build.VERSION.SDK_INT >= 30 /* Android 11 */) {
            Insets content = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            SDLActivity.onNativeInsetsChanged(content.left, content.right, content.top, content.bottom);
        }
        return result;
    }
}
```

## `android/app/src/main/java/org/libsdl/app/LICENSE.txt`

ASCII, LF line endings, ends with a newline.

```text
Copyright (C) 1997-2026 Sam Lantinga <slouken@libsdl.org>
  
This software is provided 'as-is', without any express or implied
warranty.  In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:
  
1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required. 
2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.
3. This notice may not be removed or altered from any source distribution.

```
