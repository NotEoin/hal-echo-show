/*
 * The device side of pairing (halecho/pairing.py has the PC side and the message list).
 * The device is the CPace initiator; its certificate is its associated data, and the PC's
 * certificate is the PC's, so a matching tag binds both certificates to the code.
 */
package io.github.noteoin.halecho.crypto

import com.goterl.lazysodium.interfaces.Ristretto255
import io.github.noteoin.halecho.net.Frames
import org.json.JSONObject
import java.io.DataInputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.security.SecureRandom

/** What the device keeps after pairing. */
data class Paired(
    val pcCertDer: ByteArray,
    val pcName: String,
    val deviceId: String,
    val mode: String,
    val host: String,
    val port: Int,
)

object Pairing {
    private const val PROTOCOL_VERSION = 1
    private const val SID_BYTES = 16
    private const val POINT_BYTES = 32
    private const val TAG_BYTES = 64
    private const val MAX_CERT_BYTES = 4096 // a P-256 certificate is under 1 KB
    private const val CONNECT_TIMEOUT_MS = 10_000

    // The person types the code on the PC between the hello and the reply
    private const val REPLY_TIMEOUT_MS = 300_000
    const val CODE_DIGITS = 6
    private const val CODE_RANGE = 1_000_000

    val CI: ByteArray = CPace.lvCat(
        "hal-echo-show device".toByteArray(Charsets.US_ASCII),
        "hal-echo-show pc".toByteArray(Charsets.US_ASCII),
    )

    /** A fresh code for the screen, from the platform's CSPRNG. */
    fun newCode(): String = "%06d".format(SecureRandom().nextInt(CODE_RANGE))

    /** Pairs with the PC at [host]:[port]; throws [PairingFailed] on a wrong code or refusal. */
    fun pair(
        sodium: Ristretto255.Native,
        host: String,
        port: Int,
        code: String,
        deviceName: String,
        certDer: ByteArray,
    ): Paired {
        Socket().use { socket ->
            socket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            socket.soTimeout = REPLY_TIMEOUT_MS
            val out = socket.getOutputStream()
            val input = DataInputStream(socket.getInputStream().buffered())
            val sid = ByteArray(SID_BYTES).also { SecureRandom().nextBytes(it) }
            val own = CPace(sodium, code.toByteArray(Charsets.US_ASCII), CI, sid, certDer)
            out.write(
                Frames.encodeJson(
                    JSONObject()
                        .put("type", "pair_hello")
                        .put("v", PROTOCOL_VERSION)
                        .put("sid", hex(sid))
                        .put("name", deviceName)
                        .put("cert", hex(certDer))
                        .put("y", hex(own.message)),
                ),
            )
            out.flush()
            val reply = Frames.read(input).json()
            when (reply.getString("type")) {
                "pair_failed" -> throw PairingFailed(reply.optString("reason", "refused"))
                "pair_reply" -> Unit
                else -> throw PairingFailed("unexpected '${reply.getString("type")}'")
            }
            val pcCert = field(reply, "cert", null, MAX_CERT_BYTES)
            val keys = own.finish(field(reply, "y", POINT_BYTES), pcCert, initiator = true)
            keys.check(field(reply, "tag", TAG_BYTES))
            out.write(Frames.encodeJson(JSONObject().put("type", "pair_confirm").put("tag", hex(keys.ownTag))))
            out.flush()
            val done = Frames.read(input).json()
            if (done.getString("type") != "pair_done") {
                throw PairingFailed(done.optString("reason", "the PC did not confirm"))
            }
            return Paired(
                pcCertDer = pcCert,
                pcName = reply.optString("name", host),
                deviceId = done.getString("id"),
                mode = done.getString("mode"),
                host = host,
                port = done.getInt("port"),
            )
        }
    }

    private fun field(msg: JSONObject, key: String, size: Int?, limit: Int = 64): ByteArray {
        val value = unhex(msg.optString(key)) ?: throw PairingFailed("missing or malformed '$key'")
        if ((size != null && value.size != size) || value.size > limit) {
            throw PairingFailed("'$key' has the wrong length")
        }
        return value
    }

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    fun unhex(text: String): ByteArray? {
        if (text.length % 2 != 0 || text.any { Character.digit(it, 16) < 0 }) return null
        return ByteArray(text.length / 2) { i -> text.substring(2 * i, 2 * i + 2).toInt(16).toByte() }
    }
}
