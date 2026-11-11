/*
 * The TLS side of the link: TLS 1.3, the device's Keystore key as the client certificate, and
 * exactly one trusted server certificate, the PC's, pinned by SHA-256 at pairing. No
 * certificate authority, host name or date is consulted: the pin is the whole trust decision.
 */
package io.github.noteoin.halecho.net

import android.annotation.SuppressLint
import io.github.noteoin.halecho.crypto.DeviceIdentity
import java.net.Socket
import java.security.MessageDigest
import java.security.Principal
import java.security.PrivateKey
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLEngine
import javax.net.ssl.X509ExtendedKeyManager
import javax.net.ssl.X509TrustManager

object Pinning {
    const val PROTOCOL = "TLSv1.3"

    /** An SSLContext that presents the device identity and trusts only [pinnedSha256]. */
    fun context(pinnedSha256: String): SSLContext =
        SSLContext.getInstance(PROTOCOL).apply {
            init(arrayOf(KeystoreKeyManager()), arrayOf(PinnedTrustManager(pinnedSha256)), null)
        }

    /** Accepts a server whose leaf certificate hashes to the pin, and nothing else. */
    // Lint warns that custom trust managers often skip validation; this one is the pin check
    @SuppressLint("CustomX509TrustManager")
    class PinnedTrustManager(private val pinnedSha256: String) : X509TrustManager {
        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            val leaf = chain?.firstOrNull() ?: throw CertificateException("no server certificate")
            val actual = MessageDigest.getInstance("SHA-256").digest(leaf.encoded)
            val expected = pinnedSha256.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            if (!MessageDigest.isEqual(actual, expected)) {
                throw CertificateException("the PC's certificate is not the one paired with")
            }
        }

        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            throw CertificateException("this device never accepts client connections")
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }

    /** Presents the Keystore key and its certificate whenever the server asks. */
    private class KeystoreKeyManager : X509ExtendedKeyManager() {
        override fun chooseClientAlias(keyType: Array<out String>?, issuers: Array<out Principal>?, socket: Socket?) =
            DeviceIdentity.ALIAS

        override fun chooseEngineClientAlias(keyType: Array<out String>?, issuers: Array<out Principal>?, engine: SSLEngine?) =
            DeviceIdentity.ALIAS

        override fun getCertificateChain(alias: String?): Array<X509Certificate> =
            arrayOf(DeviceIdentity.certificate())

        override fun getPrivateKey(alias: String?): PrivateKey = DeviceIdentity.privateKey()

        override fun getClientAliases(keyType: String?, issuers: Array<out Principal>?) = arrayOf(DeviceIdentity.ALIAS)

        override fun getServerAliases(keyType: String?, issuers: Array<out Principal>?): Array<String>? = null

        override fun chooseServerAlias(keyType: String?, issuers: Array<out Principal>?, socket: Socket?): String? = null
    }
}
