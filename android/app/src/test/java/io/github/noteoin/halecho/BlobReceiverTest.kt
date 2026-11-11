/* Files from the PC: hash checking and the zip unpacking used for Vosk models. */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.net.BlobReceiver
import io.github.noteoin.halecho.net.Frames
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class BlobReceiverTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun blob(id: Int, data: ByteArray) =
        Frames.Frame(Frames.BLOB, ByteBuffer.allocate(4 + data.size).putInt(id).put(data).array())

    private fun sha(data: ByteArray) = MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }

    private fun begin(id: Int, name: String, data: ByteArray, sha256: String = sha(data)) = JSONObject()
        .put("type", "blob_begin").put("id", id).put("purpose", "model").put("name", name)
        .put("size", data.size).put("sha256", sha256)

    @Test
    fun matchingFileIsHandedOn() {
        var got: File? = null
        val rx = BlobReceiver(tmp.newFolder()) { _, _, f -> got = f }
        val data = "weights".toByteArray()
        rx.begin(begin(1, "m", data))
        rx.chunk(blob(1, data))
        rx.end(JSONObject().put("id", 1))
        assertEquals("weights", got!!.readText())
    }

    @Test(expected = IOException::class)
    fun wrongHashIsRefused() {
        val rx = BlobReceiver(tmp.newFolder()) { _, _, _ -> }
        val data = "weights".toByteArray()
        rx.begin(begin(1, "m", data, "0".repeat(64)))
        rx.chunk(blob(1, data))
        rx.end(JSONObject().put("id", 1))
    }

    @Test(expected = IllegalArgumentException::class)
    fun pathInTheNameIsRefused() {
        BlobReceiver(tmp.newFolder()) { _, _, _ -> }.begin(begin(1, "../evil", ByteArray(1)))
    }

    private fun zip(vararg entries: String): File {
        val file = tmp.newFile()
        ZipOutputStream(file.outputStream()).use { zip ->
            for (name in entries) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(1)
                zip.closeEntry()
            }
        }
        return file
    }

    @Test
    fun zipUnpacksInsideTheTarget() {
        val target = tmp.newFolder()
        BlobReceiver.unzip(zip("model/am/final.mdl"), target)
        assertTrue(File(target, "model/am/final.mdl").exists())
    }

    @Test(expected = IOException::class)
    fun zipEntryLeavingTheTargetIsRefused() {
        BlobReceiver.unzip(zip("../../escaped"), tmp.newFolder())
    }
}
