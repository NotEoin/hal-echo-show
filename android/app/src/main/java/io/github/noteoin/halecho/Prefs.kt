/*
 * What the device remembers between boots: the paired PC (its pinned certificate, name and
 * last address) and this device's name. Nothing here is secret; the private key stays in
 * Android Keystore.
 */
package io.github.noteoin.halecho

import android.content.Context
import io.github.noteoin.halecho.crypto.DeviceIdentity
import io.github.noteoin.halecho.crypto.Paired
import io.github.noteoin.halecho.crypto.Pairing

class Prefs(context: Context) {
    private val prefs = context.getSharedPreferences("hal-echo", Context.MODE_PRIVATE)

    val paired: Boolean get() = prefs.contains(PC_CERT)

    /** The pinned PC certificate's SHA-256, lowercase hex. */
    val pcFingerprint: String?
        get() = prefs.getString(PC_CERT, null)?.let { Pairing.unhex(it) }?.let(DeviceIdentity::fingerprint)

    val pcName: String get() = prefs.getString(PC_NAME, "") ?: ""
    val host: String get() = prefs.getString(HOST, "") ?: ""
    val port: Int get() = prefs.getInt(PORT, DEFAULT_PORT)

    var deviceName: String
        get() = prefs.getString(DEVICE_NAME, "Echo Show") ?: "Echo Show"
        set(value) = prefs.edit().putString(DEVICE_NAME, value).apply()

    var mode: String
        get() = prefs.getString(MODE, "") ?: ""
        set(value) = prefs.edit().putString(MODE, value).apply()

    fun save(paired: Paired) {
        prefs.edit()
            .putString(PC_CERT, Pairing.hex(paired.pcCertDer))
            .putString(PC_NAME, paired.pcName)
            .putString(HOST, paired.host)
            .putInt(PORT, paired.port)
            .putString(MODE, paired.mode)
            .apply()
    }

    /** Records the address the PC last answered on, found through mDNS. */
    fun moved(host: String, port: Int) {
        prefs.edit().putString(HOST, host).putInt(PORT, port).apply()
    }

    fun forget() {
        prefs.edit().remove(PC_CERT).remove(PC_NAME).remove(HOST).remove(PORT).remove(MODE).apply()
    }

    private companion object {
        const val PC_CERT = "pc_cert"
        const val PC_NAME = "pc_name"
        const val HOST = "host"
        const val PORT = "port"
        const val MODE = "mode"
        const val DEVICE_NAME = "device_name"
        const val DEFAULT_PORT = 47800 // halecho's server.port
    }
}
