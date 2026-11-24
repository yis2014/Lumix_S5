#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_HOME:-/tmp/android_build/sdk}"
JDK="${JAVA_HOME:-/tmp/android_build/jdk/Contents/Home}"
BT="$SDK/build-tools/34.0.0"
PLATFORM="$SDK/platforms/android-34/android.jar"
OUT="$SCRIPT_DIR/build"

rm -rf "$OUT"
mkdir -p "$OUT/res_flat" "$OUT/gen" "$OUT/classes" "$OUT/dex"

# 1. Compile XML resources
"$BT/aapt2" compile --dir "$SCRIPT_DIR/res" -o "$OUT/res.zip"

# 2. Link resources + manifest into base APK and generate R.java
"$BT/aapt2" link \
  -I "$PLATFORM" \
  --manifest "$SCRIPT_DIR/AndroidManifest.xml" \
  --java "$OUT/gen" \
  -o "$OUT/unaligned.apk" \
  "$OUT/res.zip"

# 3. Compile Java sources (Java 8 bytecode for universal Android compatibility)
"$JDK/bin/javac" \
  -source 1.8 -target 1.8 \
  -cp "$PLATFORM" \
  -d "$OUT/classes" \
  "$SCRIPT_DIR/src/com/s5mod/unlocker/MainActivity.java" \
  "$OUT/gen/com/s5mod/unlocker/R.java"

# 4. Convert .class -> classes.dex via d8
JAVA_HOME="$JDK" "$BT/d8" \
  --min-api 24 \
  --lib "$PLATFORM" \
  --output "$OUT/dex" \
  "$OUT/classes/com/s5mod/unlocker/"*.class

# 5. Add classes.dex to APK
(cd "$OUT/dex" && zip -q -u "$OUT/unaligned.apk" classes.dex)

# 6. Zipalign
"$BT/zipalign" -f 4 "$OUT/unaligned.apk" "$OUT/aligned.apk"

# 7. Generate signing keystore if not present
KEYSTORE="$SCRIPT_DIR/s5unlocker.keystore"
if [ ! -f "$KEYSTORE" ]; then
  "$JDK/bin/keytool" -genkeypair -v \
    -keystore "$KEYSTORE" \
    -storepass s5unlocker \
    -keypass s5unlocker \
    -alias s5unlocker \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=S5Unlocker, OU=S5Mod, O=Local, L=Local, ST=Local, C=US"
fi

# 8. Sign APK (v1 + v2 + v3 signatures for Android 7..16)
JAVA_HOME="$JDK" "$BT/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:s5unlocker \
  --key-pass pass:s5unlocker \
  --ks-key-alias s5unlocker \
  --out "$SCRIPT_DIR/S5Unlocker.apk" \
  "$OUT/aligned.apk"

# 9. Verify signature
JAVA_HOME="$JDK" "$BT/apksigner" verify --print-certs "$SCRIPT_DIR/S5Unlocker.apk"
ls -lh "$SCRIPT_DIR/S5Unlocker.apk"
