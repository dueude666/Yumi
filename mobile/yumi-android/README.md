# Yumi Mobile (Android)

This is an Android app shell for Yumi. It loads your local Yumi UI URL in a WebView and supports file upload (notes/audio).

## 1. Prerequisites
- Android Studio (latest stable)
- Android SDK 35
- Phone and computer in same LAN/Wi-Fi

## 2. Open Project
1. Open Android Studio.
2. `File -> Open...` and select `mobile/yumi-android`.
3. Let Gradle sync complete.

## 3. Build APK
1. `Build -> Build Bundle(s) / APK(s) -> Build APK(s)`.
2. Install generated APK on phone.

## 4. Connect to Yumi Server
1. On your computer start:
```bash
python scripts/run_api.py
python scripts/run_ui.py
```
2. In app input URL like:
`http://192.168.x.x:8501`
3. Tap `Connect`.

## Notes
- This app works in LAN mode by default (HTTP cleartext allowed for local addresses).
- If you deploy Yumi over HTTPS later, input `https://...` directly.

