/*
 * Starts the service when the device finishes booting, so Hal listens even before the home
 * screen draws. Without the microphone permission it waits for the home screen to ask.
 */
package io.github.noteoin.halecho

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            HalService.start(context)
        }
    }
}
