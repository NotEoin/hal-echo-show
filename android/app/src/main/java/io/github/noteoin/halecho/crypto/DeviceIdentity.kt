/*
 * The device's long-term identity: an ECDSA P-256 key in Android Keystore and the self-signed
 * certificate Keystore makes for it. The private key never leaves Keystore; TLS signs with it
 * through Pinning.kt's key manager. The PC pins this certificate's SHA-256 at pairing.
 *
 * The LineageOS build for this device runs SELinux permissive, so Keystore here protects the
 * key from other apps less than it would on a locked-down phone; see SECURITY.md.
 */
package io.github.noteoin.halecho.crypto

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.math.BigInteger
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec
import java.util.Date
import java.util.concurrent.TimeUnit
import javax.security.auth.x500.X500Principal

object DeviceIdentity {
    const val ALIAS = "hal-echo-device"
    private const val KEYSTORE = "AndroidKeyStore"
    private const val SERIAL_BITS = 64

    // The pin is the trust, not the dates; a long life avoids an expiry nobody would notice
    private val VALIDITY_MS = TimeUnit.DAYS.toMillis(3650)

    private fun keyStore(): KeyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }

    /** The certificate, creating the key on first use. */
    @Synchronized
    fun certificate(): X509Certificate {
        val ks = keyStore()
        if (!ks.containsAlias(ALIAS)) generate()
        return ks.getCertificate(ALIAS) as X509Certificate
    }

    /** The Keystore handle to the private key. */
    fun privateKey(): PrivateKey {
        certificate()
        return keyStore().getKey(ALIAS, null) as PrivateKey
    }

    /** SHA-256 of a DER certificate, lowercase hex, as the PC computes it. */
    fun fingerprint(der: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(der).joinToString("") { "%02x".format(it) }

    private fun generate() {
        val now = System.currentTimeMillis()
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(
                KeyProperties.DIGEST_NONE,
                KeyProperties.DIGEST_SHA256,
                KeyProperties.DIGEST_SHA384,
                KeyProperties.DIGEST_SHA512,
            )
            .setCertificateSubject(X500Principal("CN=hal-echo-show device"))
            .setCertificateSerialNumber(BigInteger(SERIAL_BITS, SecureRandom()))
            .setCertificateNotBefore(Date(now - TimeUnit.MINUTES.toMillis(5)))
            .setCertificateNotAfter(Date(now + VALIDITY_MS))
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, KEYSTORE).apply {
            initialize(spec)
            generateKeyPair()
        }
    }
}
