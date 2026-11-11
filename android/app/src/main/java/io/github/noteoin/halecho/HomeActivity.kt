/*
 * The home screen: Hal's eye, full screen, from boot. Holding the eye for two seconds opens a
 * menu to pair, rename the device, see the link's status, or open Android's settings (the way
 * back to the stock launcher). The screen dims while the room is asleep.
 */
package io.github.noteoin.halecho

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.EditText
import io.github.noteoin.halecho.crypto.DeviceIdentity
import io.github.noteoin.halecho.ui.EyeView

class HomeActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private val openMenu = Runnable { showMenu() }
    private val dimmer = object : Runnable {
        override fun run() {
            val params = window.attributes
            val target = if (UiState.eye == UiState.Eye.ASLEEP) ASLEEP_BRIGHTNESS else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
            if (params.screenBrightness != target) {
                params.screenBrightness = target
                window.attributes = params
            }
            handler.postDelayed(this, DIM_CHECK_MS)
        }
    }

    // onEyeTouch calls performClick on release; lint cannot see that through the lambda
    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The eye is the device's face: it shows over the swipe lock screen and wakes the panel
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val eye = EyeView(this)
        eye.setOnTouchListener { view, event -> onEyeTouch(view, event) }
        setContentView(eye)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            HalService.start(this)
        } else {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MIC_REQUEST)
        }
    }

    override fun onResume() {
        super.onResume()
        window.insetsController?.let {
            it.hide(WindowInsets.Type.systemBars())
            it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        handler.post(dimmer)
    }

    override fun onPause() {
        handler.removeCallbacks(dimmer)
        super.onPause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        if (requestCode == MIC_REQUEST && results.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            HalService.start(this)
        } else {
            UiState.status = getString(R.string.needs_microphone)
        }
    }

    // The eye answers a two-second hold, not a tap; a tap is passed on as a click
    private fun onEyeTouch(view: View, event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> handler.postDelayed(openMenu, HOLD_MS)
            MotionEvent.ACTION_UP -> {
                handler.removeCallbacks(openMenu)
                view.performClick()
            }
            MotionEvent.ACTION_CANCEL -> handler.removeCallbacks(openMenu)
        }
        return true
    }

    private fun showMenu() {
        val prefs = Prefs(this)
        val items = arrayOf(R.string.menu_pair, R.string.menu_rename, R.string.menu_status, R.string.menu_settings)
            .map(::getString).toTypedArray()
        AlertDialog.Builder(this)
            .setTitle(prefs.deviceName)
            .setItems(items) { _, which ->
                when (which) {
                    0 -> startActivity(Intent(this, PairActivity::class.java))
                    1 -> rename(prefs)
                    2 -> showStatus(prefs)
                    3 -> startActivity(Intent(Settings.ACTION_SETTINGS))
                }
            }
            .show()
    }

    private fun rename(prefs: Prefs) {
        val input = EditText(this).apply { setText(prefs.deviceName) }
        AlertDialog.Builder(this)
            .setTitle(R.string.rename_title)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ -> prefs.deviceName = input.text.toString().trim().ifEmpty { "Echo Show" } }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun showStatus(prefs: Prefs) {
        val device = runCatching { DeviceIdentity.fingerprint(DeviceIdentity.certificate().encoded) }
            .getOrDefault("unavailable")
        val message = getString(
            R.string.status_body,
            UiState.status,
            prefs.pcName.ifEmpty { getString(R.string.not_paired) },
            prefs.host,
            prefs.port,
            prefs.mode.ifEmpty { "-" },
            prefs.pcFingerprint?.take(FINGERPRINT_CHARS) ?: "-",
            device.take(FINGERPRINT_CHARS),
            BuildConfig.VERSION_NAME,
        )
        AlertDialog.Builder(this).setTitle(R.string.status_title).setMessage(message).setPositiveButton(R.string.ok, null).show()
    }

    private companion object {
        const val MIC_REQUEST = 1
        const val HOLD_MS = 2000L
        const val DIM_CHECK_MS = 1000L
        const val ASLEEP_BRIGHTNESS = 0.05f
        const val FINGERPRINT_CHARS = 16 // the length `hal-echo devices` and mDNS show
    }
}
