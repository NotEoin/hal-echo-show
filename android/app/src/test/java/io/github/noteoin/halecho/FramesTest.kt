/* The wire format: the same bytes tests/test_frames.py pins on the PC side. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.net.Frames
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.DataInputStream

class FramesTest {
    @Test
    fun audioFrameBytesMatchThePc() {
        val frame = Frames.encodeAudio(7, 2, shortArrayOf(0x0201))
        val expected = byteArrayOf(0, 0, 0, 10, 2, 0, 0, 0, 7, 0, 0, 0, 2, 1, 2)
        assertArrayEquals(expected, frame)
    }

    @Test
    fun jsonFrameRoundTrips() {
        val bytes = Frames.encodeJson(JSONObject().put("type", "ping").put("t", 1))
        val frame = Frames.read(DataInputStream(ByteArrayInputStream(bytes)))
        assertEquals(Frames.JSON, frame.kind)
        assertEquals(1, frame.json().getInt("t"))
    }

    @Test(expected = Frames.FrameError::class)
    fun oversizedFrameIsRefusedBeforeItsPayload() {
        val header = byteArrayOf(0, 0x10, 0, 1, Frames.JSON.toByte())
        Frames.read(DataInputStream(ByteArrayInputStream(header)))
    }

    @Test
    fun audioSamplesDecodeLittleEndian() {
        val frame = Frames.encodeAudio(1, 0, shortArrayOf(-2, 300))
        val parsed = Frames.read(DataInputStream(ByteArrayInputStream(frame)))
        val pcm = Frames.samples(parsed.payload, parsed.audioOffset, parsed.payload.size - parsed.audioOffset)
        assertArrayEquals(shortArrayOf(-2, 300), pcm)
        assertEquals(1L, parsed.id())
    }
}
