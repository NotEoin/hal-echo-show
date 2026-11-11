/*
 * The wire format shared with the PC (halecho/frames.py): length-prefixed frames.
 *
 *     frame = length (u32, big endian) | kind (u8) | payload
 *
 * JSON frames carry one message object, AUDIO frames a turn id, a sequence number and 16-bit
 * little-endian mono PCM, BLOB frames a transfer id and file bytes, TERM frames a terminal id and
 * the bytes of a terminal screen in either direction. FramesTest pins the bytes
 * against the Python tests.
 */
package io.github.noteoin.halecho.net

import org.json.JSONObject
import java.io.DataInputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder

object Frames {
    const val JSON = 1
    const val AUDIO = 2
    const val BLOB = 3
    const val TERM = 4
    const val HEADER_BYTES = 5
    const val ID_BYTES = 4

    /** 30 s of 16 kHz PCM16 is 960 KB, the longest utterance sent in one frame. */
    const val MAX_PAYLOAD = 1 shl 20

    /** A malformed frame, or one larger than [MAX_PAYLOAD]. */
    class FrameError(message: String) : IOException(message)

    /** One decoded frame. */
    class Frame(val kind: Int, val payload: ByteArray) {
        /** The message of a JSON frame. */
        fun json(): JSONObject {
            if (kind != JSON) throw FrameError("expected a JSON frame, got kind $kind")
            val msg = JSONObject(String(payload, Charsets.UTF_8))
            if (!msg.has("type")) throw FrameError("a JSON frame must have a 'type'")
            return msg
        }

        /** The turn id of an AUDIO frame, or the id of a BLOB or TERM frame. */
        fun id(): Long {
            if (payload.size < ID_BYTES) throw FrameError("frame too short for an id")
            return ByteBuffer.wrap(payload, 0, ID_BYTES).int.toLong() and 0xFFFF_FFFFL
        }

        /** Where the PCM of an AUDIO frame starts in [payload]. */
        val audioOffset: Int get() = 2 * ID_BYTES

        /** Where the bytes of a BLOB or TERM frame start in [payload]. */
        val blobOffset: Int get() = ID_BYTES
    }

    /** One frame, ready to write. */
    fun encode(kind: Int, payload: ByteArray): ByteArray {
        if (payload.size > MAX_PAYLOAD) throw FrameError("payload of ${payload.size} bytes")
        return ByteBuffer.allocate(HEADER_BYTES + payload.size)
            .order(ByteOrder.BIG_ENDIAN)
            .putInt(payload.size)
            .put(kind.toByte())
            .put(payload)
            .array()
    }

    /** A JSON frame. */
    fun encodeJson(msg: JSONObject): ByteArray = encode(JSON, msg.toString().toByteArray(Charsets.UTF_8))

    /** An AUDIO frame from 16-bit samples, written little endian. */
    fun encodeAudio(turn: Long, seq: Int, pcm: ShortArray): ByteArray {
        val body = ByteBuffer.allocate(2 * ID_BYTES + 2 * pcm.size)
        body.order(ByteOrder.BIG_ENDIAN).putInt(turn.toInt()).putInt(seq)
        body.order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().put(pcm)
        return encode(AUDIO, body.array())
    }

    /** A TERM frame: a terminal's id and some of its bytes. */
    fun encodeTerm(term: Long, data: ByteArray): ByteArray =
        encode(TERM, ByteBuffer.allocate(ID_BYTES + data.size).putInt(term.toInt()).put(data).array())

    /** Reads one frame; throws [java.io.EOFException] when the peer closes. */
    fun read(input: DataInputStream): Frame {
        val length = input.readInt()
        val kind = input.readUnsignedByte()
        if (kind !in JSON..TERM) throw FrameError("unknown frame kind $kind")
        if (length < 0 || length > MAX_PAYLOAD) throw FrameError("payload of $length bytes")
        val payload = ByteArray(length)
        input.readFully(payload)
        return Frame(kind, payload)
    }

    /** 16-bit little-endian PCM bytes as samples. */
    fun samples(bytes: ByteArray, offset: Int, length: Int): ShortArray {
        val out = ShortArray(length / 2)
        ByteBuffer.wrap(bytes, offset, length).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().get(out)
        return out
    }
}
