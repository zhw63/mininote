[app]

title = Mini Note
package.name = mininote
package.domain = com.zhw63.mininote
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,ttc,otf,txt,json
version = 1.0.0
requirements = python3,kivy
orientation = all
fullscreen = 0
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = False
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1