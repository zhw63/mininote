[app]
title = 精简记事本
package.name = mininote
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,ttc,otf
source.include_patterns = *.ttf,*.ttc,*.otf
version = 1.17
requirements = python3,kivy,hostpython3
orientation = all
fullscreen = 0
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a,armeabi-v7a
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.logcat_filters = *:S python:D

# 先备份
Copy-Item buildozer.spec buildozer.spec.bak

# 在 [app] 区域添加 accept_sdk_license
(Get-Content buildozer.spec) -replace '^\[app\]', "[app]`nandroid.accept_sdk_license = True" | Set-Content -Encoding UTF8 buildozer.spec

[buildozer]
log_level = 2
warn_on_root = 1