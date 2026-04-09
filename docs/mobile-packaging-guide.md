# HarBeat Web to Mobile Guide

## 1. Current architecture

The current `dev` branch already follows the right split for mobile:

- `web/` is the browser UI built with React + Vite.
- `app/` is the FastAPI backend.
- `app/main.py` serves both `/api/*` and the built web SPA.

That means the backend does not need to be packaged into a mobile app. The backend should stay deployed on your server and expose HTTP APIs for both the web page and the mobile app.

## 2. How to use the current web UI

Local development:

```powershell
cd D:\harbeatDev\harbeat-client
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```powershell
cd D:\harbeatDev\harbeat-client\web
npm install
npm run dev
```

Open:

- `http://localhost:5180` for the React dev UI
- `http://localhost:8000/docs` for the FastAPI Swagger API docs

Production deployment:

- Build the web bundle with `npm run build` inside `web/`
- Start the backend
- Let Nginx forward `/` and `/api/*` to the FastAPI container

## 3. Fastest way to get a mobile app now

The fastest route is a Flutter shell app that loads the deployed web site inside a WebView.

Why this is the best first step:

- You can reuse the current web UI immediately.
- Your backend stays unchanged.
- Packaging is fast and low risk.
- You can later replace individual pages with native Flutter screens.

The Flutter shell lives in `mobile/`.

## 4. Build the Android APK

Debug APK:

```powershell
cd D:\harbeatDev\harbeat-client\mobile
flutter pub get
flutter build apk --debug --dart-define=HARBEAT_BASE_URL=https://your-domain.com
```

Release APK:

```powershell
cd D:\harbeatDev\harbeat-client\mobile
flutter pub get
flutter build apk --release --dart-define=HARBEAT_BASE_URL=https://your-domain.com
```

Generated files:

- `mobile/build/app/outputs/flutter-apk/app-debug.apk`
- `mobile/build/app/outputs/flutter-apk/app-release.apk`

If your server is only available over plain HTTP during testing, Android is allowed because `usesCleartextTraffic="true"` is enabled in the manifest. For production, HTTPS is strongly recommended.

## 5. Should the backend be "packaged into APIs"?

Yes, for mobile, the backend should be treated as an API service.

Recommended shape:

- Web app calls `https://your-domain.com/api/...`
- Flutter app calls the same `https://your-domain.com/api/...`
- Authentication stays token-based, for example JWT bearer token
- Audio streams stay as URL endpoints such as `/api/stream/...`

Do not package the Python backend into the phone app. Keep it on the server.

## 6. Recommended migration path

Phase 1:

- Keep the current React web UI
- Improve responsive layout in web
- Ship the Flutter WebView shell

Phase 2:

- Extract stable backend contracts
- Document request and response formats in `/docs`
- Build native Flutter login, library, playlist, and player pages

Phase 3:

- Let Flutter call FastAPI directly
- Keep the web project as the admin or desktop interface if needed

## 7. API checklist before native Flutter pages

Before moving from WebView to native Flutter UI, make sure the server provides:

- login/register/me
- playlist list/detail/create/delete
- library list/search/upload/delete
- recommendation endpoints
- audio stream endpoints
- consistent JSON error format

This project already has most of those endpoints in `web/src/api/client.ts`.
