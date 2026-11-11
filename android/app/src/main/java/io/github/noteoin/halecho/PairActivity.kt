/*
 * Pairing on the device: show a fresh six-digit code, find the PC running `hal-echo pair`
 * (through mDNS, or an address typed here), and run the exchange. The person types the code on
 * the PC. A wrong code gets a new one; the PC gives up after its own limit of attempts.
 */
package io.github.noteoin.halecho

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import com.goterl.lazysodium.LazySodiumAndroid
import com.goterl.lazysodium.SodiumAndroid
import io.github.noteoin.halecho.crypto.DeviceIdentity
import io.github.noteoin.halecho.crypto.Pairing
import io.github.noteoin.halecho.crypto.PairingFailed
import io.github.noteoin.halecho.net.Discovery
import java.io.IOException
import kotlin.concurrent.thread

class PairActivity : Activity() {
    private lateinit var codeView: TextView
    private lateinit var statusView: TextView
    private lateinit var addressInput: EditText
    @Volatile private var busy = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = Prefs(this)
        codeView = text(CODE_SIZE_SP).apply { letterSpacing = CODE_SPACING }
        statusView = text(STATUS_SIZE_SP)
        addressInput = EditText(this).apply {
            setHint(R.string.pair_address_hint)
            inputType = InputType.TYPE_CLASS_TEXT
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
        }
        val connect = Button(this).apply {
            setText(R.string.pair_connect)
            setOnClickListener { addressInput.text.toString().trim().takeIf { it.isNotEmpty() }?.let { attempt(prefs, it, PAIR_PORT) } }
        }
        setContentView(
            LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                setBackgroundColor(Color.BLACK)
                addView(text(TITLE_SIZE_SP).apply { setText(R.string.pair_title) })
                addView(codeView)
                addView(statusView)
                addView(LinearLayout(context).apply {
                    gravity = Gravity.CENTER
                    addView(addressInput)
                    addView(connect)
                })
            },
        )
        newCode()
        search(prefs)
    }

    private fun text(sizeSp: Float) = TextView(this).apply {
        textSize = sizeSp
        setTextColor(Color.WHITE)
        gravity = Gravity.CENTER
    }

    private fun newCode() {
        val code = Pairing.newCode()
        codeView.text = getString(R.string.pair_code, code.substring(0, 3), code.substring(3))
        codeView.tag = code
    }

    private fun search(prefs: Prefs) {
        statusView.setText(R.string.pair_looking)
        thread(name = "pair-discovery") {
            val found = Discovery(this).find(DISCOVERY_TIMEOUT_MS) { it.pairing }
            runOnUiThread {
                if (found == null) {
                    statusView.setText(R.string.pair_not_found)
                } else {
                    attempt(prefs, found.host, found.port)
                }
            }
        }
    }

    private fun attempt(prefs: Prefs, host: String, port: Int) {
        if (busy) return
        busy = true
        statusView.text = getString(R.string.pair_found, host)
        val code = codeView.tag as String
        thread(name = "pair") {
            val result = try {
                val sodium = LazySodiumAndroid(SodiumAndroid())
                val paired = Pairing.pair(sodium, host, port, code, prefs.deviceName, DeviceIdentity.certificate().encoded)
                prefs.save(paired)
                null
            } catch (e: PairingFailed) {
                e.message ?: getString(R.string.pair_failed)
            } catch (e: IOException) {
                getString(R.string.pair_unreachable, host, e.message)
            }
            runOnUiThread {
                busy = false
                if (result == null) {
                    HalService.start(this, HalService.ACTION_REPAIRED)
                    finish()
                } else {
                    statusView.text = getString(R.string.pair_retry, result)
                    newCode()
                    search(prefs)
                }
            }
        }
    }

    private companion object {
        const val PAIR_PORT = 47801 // halecho's server.pair_port
        const val DISCOVERY_TIMEOUT_MS = 15_000L
        const val TITLE_SIZE_SP = 22f
        const val CODE_SIZE_SP = 72f
        const val CODE_SPACING = 0.1f
        const val STATUS_SIZE_SP = 18f
    }
}
