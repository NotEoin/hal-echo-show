# Update the app

This page sends a new build of the app from the PC to the paired Echos, without a cable or USB
debugging. Android installs it only after a tap on the Echo, and only if the new APK is signed with
the same key as the installed one.

## Steps

1. Build the new version. The build signs it with the key in `android/keystore/`.

   ```bash
   android/build.sh apk
   ```

2. Send it to one device, or to all connected devices.

   ```bash
   hal-echo push-update android/app/build/outputs/apk/release/app-release.apk --device Kitchen
   ```

3. On the Echo, tap **Update** on Android's confirmation screen. The bridge log records the result.

   ```bash
   journalctl --user -u hal-echo.service -n 20    # "update: installed"
   ```

## Symptoms and fixes

| Symptom | Fix |
| --- | --- |
| The Echo never asks | Allow installs from the app: step 5 of [Set up the Echo](set-up-the-echo.md). |
| "failed: ... signatures do not match" | The APK was signed with another key. Build with the original `android/keystore/`. |
| `no connected device matched` | The device is offline; check `hal-echo devices`. |
