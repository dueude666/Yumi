# Yumi Mobile (Android)

Yumi Mobile is an Android app shell that loads your local Yumi UI URL in WebView and supports note/audio upload.

## 1. One-time environment setup (Windows + PowerShell)

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\android_env.ps1
```

Create project-local SDK config:

```powershell
@"
sdk.dir=C:\\Users\\duedue666\\AppData\\Local\\Android\\Sdk
"@ | Out-File -Encoding ascii .\mobile\yumi-android\local.properties
```

## 2. Verify Gradle project

```powershell
cd .\mobile\yumi-android
.\gradlew.bat tasks --all
```

If first run fails with download timeout, run it again after your network is stable. The first run needs to fetch:
- Gradle distribution
- Android Gradle Plugin dependencies

## 3. Open in Android Studio

1. Open Android Studio.
2. `File -> Open...` and select `mobile/yumi-android`.
3. Wait for Gradle sync.

## 4. Build APK

1. `Build -> Build Bundle(s) / APK(s) -> Build APK(s)`.
2. Install generated APK on phone.

## 5. Connect app to Yumi service

1. On your computer:

```powershell
python .\scripts\run_api.py
python .\scripts\run_ui.py
```

2. In app, input URL like:

```text
http://192.168.x.x:8501
```

3. Tap `Connect`.

## Notes

- LAN mode is enabled by default (cleartext HTTP allowed for local addresses).
- For HTTPS deployment, use `https://...` directly.
