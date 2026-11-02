[app]
title = 校园跑路线规划器
package.name = campusroute
package.domain = org.campusroute

# 构建目录由 build_apk.sh 组装（main.py + core/ + assets/ + campus_profile.json）
source.dir = .
source.include_exts = py,png,jpg,jpeg,txt,json,ttf,ttc
source.include_patterns = core/*,assets/*

version = 1.0
requirements = python3==3.11.9,kivy==2.3.0,pillow==10.3.0,numpy==1.26.4

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES
android.archs = arm64-v8a, armeabi-v7a
android.minapi = 24
android.api = 33
android.allow_backup = True

orientation = portrait
fullscreen = 0
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
