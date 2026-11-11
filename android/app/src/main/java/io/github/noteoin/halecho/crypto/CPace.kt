/*
 * CPace over ristretto255 with SHA-512, the pairing exchange; the same steps as the PC's
 * halecho/cpace.py (draft-irtf-cfrg-cpace-21, initiator-responder transcript, section 10.4 key
 * confirmation). CPaceTest checks the draft's appendix B.3 vectors.
 *
 * The ristretto255 group operations come from libsodium through lazysodium; the
 * Ristretto255.Native interface lets the JVM tests use lazysodium-java instead.
 */
package io.github.noteoin.halecho.crypto

import com.goterl.lazysodium.interfaces.Ristretto255
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** The peer used another code, or sent a malformed or hostile message. */
class PairingFailed(message: String) : Exception(message)

/** The shared key and the confirmation tags each side sends. */
class Confirmed(val isk: ByteArray, val ownTag: ByteArray, private val peerTag: ByteArray) {
    /** Throws [PairingFailed] unless [tag] is the one the peer must send. */
    fun check(tag: ByteArray) {
        if (!MessageDigest.isEqual(tag, peerTag)) {
            throw PairingFailed("the confirmation tag does not match: wrong code")
        }
    }
}

/** One side of a CPace run; [scalar] is fixed only by the test vectors. */
class CPace(
    private val sodium: Ristretto255.Native,
    prs: ByteArray,
    ci: ByteArray,
    private val sid: ByteArray,
    private val ad: ByteArray,
    scalar: ByteArray? = null,
) {
    private val y: ByteArray = scalar ?: ByteArray(Ristretto255.RISTRETTO255_SCALAR_BYTES).also {
        sodium.cryptoCoreRistretto255ScalarRandom(it)
    }

    /** This side's message: y times the code's generator. */
    val message: ByteArray = scalarMult(y, generator(sodium, prs, ci, sid))
        ?: throw PairingFailed("the generator gave the identity element")

    /** Derives the key from the peer's message; throws [PairingFailed] on a bad point. */
    fun finish(peerMessage: ByteArray, peerAd: ByteArray, initiator: Boolean): Confirmed {
        if (peerMessage.size != Ristretto255.RISTRETTO255_BYTES ||
            !sodium.cryptoCoreRistretto255IsValidPoint(peerMessage)
        ) {
            throw PairingFailed("bad peer message")
        }
        val k = scalarMult(y, peerMessage) ?: throw PairingFailed("peer message gave the identity")
        val isk = if (initiator) {
            intermediateKey(sid, k, message, ad, peerMessage, peerAd)
        } else {
            intermediateKey(sid, k, peerMessage, peerAd, message, ad)
        }
        return Confirmed(isk, tag(isk, sid, message, ad), tag(isk, sid, peerMessage, peerAd))
    }

    private fun scalarMult(n: ByteArray, point: ByteArray): ByteArray? {
        val out = ByteArray(Ristretto255.RISTRETTO255_BYTES)
        // libsodium refuses (returns false) when the product is the identity element
        return if (sodium.cryptoScalarmultRistretto255(out, n, point)) out else null
    }

    companion object {
        val DSI = "CPaceRistretto255".toByteArray(Charsets.US_ASCII)
        private val DSI_ISK = DSI + "_ISK".toByteArray(Charsets.US_ASCII)
        private val MAC_LABEL = "CPaceMac".toByteArray(Charsets.US_ASCII)
        private const val HASH_BLOCK_BYTES = 128 // SHA-512 input block size

        /** [data] prefixed with its length in LEB128. */
        fun prependLen(data: ByteArray): ByteArray {
            val out = ByteArrayOutputStream()
            var length = data.size
            while (true) {
                if (length < 128) out.write(length) else out.write((length and 0x7F) + 0x80)
                length = length ushr 7
                if (length == 0) break
            }
            out.write(data)
            return out.toByteArray()
        }

        /** Each part length-prefixed, then concatenated. */
        fun lvCat(vararg parts: ByteArray): ByteArray {
            val out = ByteArrayOutputStream()
            for (part in parts) out.write(prependLen(part))
            return out.toByteArray()
        }

        /** The generator's hash input, zero-padded so the code ends the first hash block. */
        fun generatorString(prs: ByteArray, ci: ByteArray, sid: ByteArray): ByteArray {
            val zpad = maxOf(0, HASH_BLOCK_BYTES - 1 - prependLen(prs).size - prependLen(DSI).size)
            return lvCat(DSI, prs, ByteArray(zpad), ci, sid)
        }

        /** The code-derived generator. */
        fun generator(sodium: Ristretto255.Native, prs: ByteArray, ci: ByteArray, sid: ByteArray): ByteArray {
            val hash = sha512(generatorString(prs, ci, sid))
            val point = ByteArray(Ristretto255.RISTRETTO255_BYTES)
            if (!sodium.cryptoCoreRistretto255FromHash(point, hash)) {
                throw PairingFailed("ristretto255 from_hash failed")
            }
            return point
        }

        fun intermediateKey(
            sid: ByteArray, k: ByteArray, ya: ByteArray, ada: ByteArray, yb: ByteArray, adb: ByteArray,
        ): ByteArray = sha512(lvCat(DSI_ISK, sid, k) + lvCat(ya, ada) + lvCat(yb, adb))

        fun tag(isk: ByteArray, sid: ByteArray, y: ByteArray, ad: ByteArray): ByteArray {
            val mac = Mac.getInstance("HmacSHA512")
            mac.init(SecretKeySpec(sha512(MAC_LABEL + sid + isk), "HmacSHA512"))
            return mac.doFinal(lvCat(y, ad))
        }

        private fun sha512(data: ByteArray): ByteArray = MessageDigest.getInstance("SHA-512").digest(data)
    }
}
