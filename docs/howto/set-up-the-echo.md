# Set up the Echo

This page installs the app on an unlocked Echo Show 5 running LineageOS 18.1, makes it the home
screen, pairs it with your PC and closes the USB debugging port again. It assumes the PC side is
installed (see the README) and the Echo is connected to the PC by USB.

Nothing here flashes, roots or repartitions the Echo. The app is an ordinary user app, and each
step says how to undo it.

## Steps

1. Reserve an address for the Echo, and for the PC, in your router's DHCP settings. Then the
   firewall rule in step 6 stays right, and the Echo finds the PC without waiting for mDNS.

2. Turn on USB debugging on the Echo: **Settings > About tablet**, tap **Build number** seven
   times, then **Settings > System > Developer options > USB debugging**. Accept the PC's key when
   the Echo asks.

   ```bash
   adb devices -l     # the Echo is listed as "device", not "unauthorized"
   ```

3. Read the Echo's details. These commands only read.

   ```bash
   adb shell getprop ro.product.cpu.abi          # arm64-v8a or armeabi-v7a: the build to use
   adb shell getprop ro.lineage.version          # the ROM build
   adb shell grep MemAvailable /proc/meminfo     # free memory for the speech models
   adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
   ```

   Note the last line the final command prints: it is the stock home screen, which "Undo" restores.

4. Time Whisper on the Echo and choose the speech model (optional, about ten minutes). Follow
   [Benchmark Whisper on the Echo](benchmark-whisper-on-the-echo.md). It installs nothing and
   removes its files when it finishes.

5. Install the app and give it the microphone. Granting the permission over adb saves a prompt on
   the screen.

   ```bash
   adb install android/app/build/outputs/apk/release/app-release.apk
   adb shell pm grant io.github.noteoin.halecho android.permission.RECORD_AUDIO
   adb shell appops set io.github.noteoin.halecho REQUEST_INSTALL_PACKAGES allow  # updates from the PC
   adb shell dumpsys deviceidle whitelist +io.github.noteoin.halecho              # never put to sleep
   ```

6. Let the Echo, and only the Echo, reach the bridge through the PC's firewall. `hal-echo firewall`
   prints the rules; run them yourself.

   ```bash
   hal-echo firewall --address 192.168.1.50     # the Echo's reserved address
   ```

7. Make the app the home screen, so the eye is what the Echo shows when it starts.

   ```bash
   adb shell cmd package set-home-activity io.github.noteoin.halecho/.HomeActivity
   ```

8. Pair. Start pairing on the PC, then on the Echo hold the eye for two seconds and tap
   **Pair with a PC**. Type the six digits the Echo shows.

   ```bash
   hal-echo pair --mode desk     # or personal, or home; see docs/user/modes.md
   ```

9. Start the bridge, then restart the Echo to check it comes back on its own.

   ```bash
   systemctl --user enable --now hal-echo.service
   adb reboot                    # the eye appears and connects; "Hey Hal" answers
   ```

10. Close the debugging port. On this ROM, USB debugging also opens ADB over the network, so turn
    it off: **Settings > System > Developer options > USB debugging** off, and turn **Developer
    options** off too. Unplug the cable.

    ```bash
    adb connect 192.168.1.50      # must fail: nothing on the network can reach the Echo's shell
    ```

## Undo

The following commands reverse the steps above. They need USB debugging on again.

```bash
adb shell cmd package set-home-activity STOCK_HOME   # the activity step 3 printed
adb uninstall io.github.noteoin.halecho     # removes the app, its key and its models
hal-echo unpair "Echo Show"                 # forget the device on the PC
```

Without a cable, choose another home app in **Settings > Apps & notifications > Default apps >
Home app**; the eye's menu opens Android's settings.

## Symptoms and fixes

| Symptom | Fix |
| --- | --- |
| `adb devices` lists nothing | USB debugging is off, or the Echo is in charge-only mode. Turn it on (step 2). |
| `adb devices` says `unauthorized` | Accept the key prompt on the Echo's screen. |
| The Echo says "Waiting for the PC" | Check `systemctl --user status hal-echo.service`, the firewall rules (step 6) and that both are on the same network. |
| Pairing finds no PC | `hal-echo pair` must be running; type the PC's address on the pairing screen if mDNS is blocked. |
| Pairing says the code does not match | Type the code shown now; the Echo shows a new code after each failed attempt. |
| The eye stays dark and says "Microphones off" | The privacy button is on: hold it until its red light goes out. |
| "Fetching speech models" never ends | The PC could not download a model: run `hal-echo models` and read its error. |
| Hal does not hear you across the room | The ROM thread notes quiet microphones; speak closer, and check `hal-echo devices` shows the Echo online. |
