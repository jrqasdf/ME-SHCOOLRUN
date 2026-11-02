#!/usr/bin/env bash
# 组装 Android 构建目录并调用 Buildozer 打包 APK。
# 需要：Linux / WSL / macOS + JDK17 + Android SDK（buildozer 会自动下载）
# 用法：bash mobile/build_apk.sh
set -e
MOBILE_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL_DIR="$(dirname "$MOBILE_DIR")"
BUILD="$MOBILE_DIR/.build"

echo "[1/3] 组装构建目录: $BUILD"
rm -rf "$BUILD"
mkdir -p "$BUILD"
cp "$MOBILE_DIR/main.py" "$MOBILE_DIR/buildozer.spec" "$BUILD"/
cp -r "$TOOL_DIR/core" "$TOOL_DIR/assets" "$BUILD"/
cp "$TOOL_DIR/campus_profile.json" "$BUILD"/

echo "[2/3] 检查 buildozer"
if ! command -v buildozer >/dev/null 2>&1; then
  python3 -m pip install --user buildozer cython
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[3/3] 开始打包（首次会下载 Android SDK/NDK，比较久）"
cd "$BUILD"
buildozer -v android debug

mkdir -p dist
cp bin/*.apk dist/ 2>/dev/null || true
echo
echo "APK 输出: $BUILD/dist/*.apk"
