# HarBeat iOS Packaging Guide

## Current status

The Flutter project now includes:

- iOS project skeleton under `mobile/ios/`
- App display name set to `HarBeat`
- App icon assets replaced with the new hiphop-styled logo set

Icon source file:

- `mobile/branding/harbeat-icon-master.png`

## App icon files updated

iOS:

- `mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/*`

Android:

- `mobile/android/app/src/main/res/mipmap-*/ic_launcher.png`

## Bundle identifier recommendation

Use one of these patterns in Xcode:

- `com.yourcompany.harbeat`
- `com.yourbrand.harbeat.mobile`

Avoid temporary IDs for release builds.

## Build requirements

You must complete iOS packaging on a Mac with:

- macOS
- Xcode
- an Apple Developer account
- valid signing certificates and provisioning profiles

Windows cannot produce the final signed iOS install package.

## Build steps on Mac

```bash
cd /path/to/harbeat-client/mobile
flutter pub get
flutter build ios --release --dart-define=HARBEAT_BASE_URL=https://your-domain.com
```

Then open:

- `mobile/ios/Runner.xcworkspace`

In Xcode:

1. Select `Runner`
2. Set your `Bundle Identifier`
3. Choose your `Team`
4. Confirm signing works on a real device
5. Run `Product > Archive`
6. Export or upload from Organizer

## Network requirement

For App Store style production builds, your backend should use HTTPS.

Recommended:

- `HARBEAT_BASE_URL=https://your-domain.com`

If you use plain HTTP on iOS, App Transport Security may block requests unless you add explicit exceptions in `Info.plist`.

## Permissions

Current Flutter features mainly use:

- network access
- file picking
- audio playback

At the moment, no extra iOS privacy strings were required for the current implemented features. If you later add microphone recording, photo library save, media library access, or camera scanning, you must add the corresponding `NS*UsageDescription` keys.

## Suggested release checklist

- Replace bundle identifier
- Set Apple team and signing
- Confirm `HARBEAT_BASE_URL`
- Test login, upload, search, playback, discover, session, profile, DJ tools on a real iPhone
- Archive in Xcode
