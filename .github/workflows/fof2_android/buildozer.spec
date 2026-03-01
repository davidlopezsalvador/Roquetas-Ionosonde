[app]
title = foF2 Monitor
package.name = fof2monitor
package.domain = org.roquetes
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0

requirements = python3,kivy==2.3.0,requests

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.ndk_api = 21
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True
android.accept_sdk_license = True

# Notificaciones
android.gradle_dependencies = androidx.core:core:1.6.0

[buildozer]
log_level = 2
warn_on_root = 1
