# HarBeat Mobile

This directory contains a Flutter mobile scaffold derived from the `phoneui` visual system.

## Included

- Mobile-first dark theme based on the "Digital Cypher" language
- Login/Register shell
- Main tab shell with Library / Discover / Session / Profile
- Shared mini player
- API client prepared for the current FastAPI backend
- Token persistence with `SharedPreferences`

## Not included yet

- Generated `android/` and `ios/` folders
- Native audio playback integration
- File picker / upload integration

Flutter SDK is not installed on this machine, so native platform folders could not be generated with `flutter create`.

## After installing Flutter

```powershell
flutter --version
flutter doctor
cd D:\harbeatDev\harbeat-client\mobile
flutter create .
flutter pub get
flutter run
```

Set your LAN backend address in `lib/src/core/config/app_config.dart`.
