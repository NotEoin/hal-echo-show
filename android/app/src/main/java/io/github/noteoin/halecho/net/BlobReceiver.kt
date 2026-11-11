/*
 * Receives files the PC sends as BLOB frames (speech models and app updates): writes them to
 * a temporary file, checks the size and SHA-256 announced in `blob_begin`, and only then hands
 * the file on. A Vosk model arrives zipped and is unpacked, refusing paths that leave its folder.
 */
package io.github.noteoin.halecho.net

import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest
import java.util.zip.ZipInputStream

class BlobReceiver(private val dir: File, private val onComplete: (purpose: String, name: String, file: File) -> Unit) {
    private class Transfer(val purpose: String, val name: String, val size: Long, val sha256: String, val file: File) {
        val out = FileOutputStream(file)
        val digest: MessageDigest = MessageDigest.getInstance("SHA-256")
        var received = 0L
    }

    private val transfers = HashMap<Long, Transfer>()

    fun begin(msg: JSONObject) {
        dir.mkdirs()
        val id = msg.getLong("id")
        val name = msg.getString("name")
        require(SAFE_NAME.matches(name)) { "unsafe file name '$name'" }
        transfers[id] = Transfer(
            msg.getString("purpose"),
            name,
            msg.getLong("size"),
            msg.getString("sha256"),
            File(dir, "$name.part"),
        )
    }

    fun chunk(frame: Frames.Frame) {
        val t = transfers[frame.id()] ?: return
        val n = frame.payload.size - frame.blobOffset
        t.received += n
        if (t.received > t.size) throw IOException("${t.name} is larger than announced")
        t.digest.update(frame.payload, frame.blobOffset, n)
        t.out.write(frame.payload, frame.blobOffset, n)
    }

    fun end(msg: JSONObject) {
        val t = transfers.remove(msg.getLong("id")) ?: return
        t.out.close()
        val actual = t.digest.digest().joinToString("") { "%02x".format(it) }
        if (t.received != t.size || actual != t.sha256) {
            t.file.delete()
            throw IOException("${t.name} does not match its size and SHA-256")
        }
        onComplete(t.purpose, t.name, t.file)
    }

    companion object {
        private val SAFE_NAME = Regex("[A-Za-z0-9._-]{1,100}")

        /** Unpacks [zip] into [target], refusing entries whose path escapes it. */
        fun unzip(zip: File, target: File) {
            val root = target.canonicalFile
            ZipInputStream(zip.inputStream().buffered()).use { input ->
                while (true) {
                    val entry = input.nextEntry ?: break
                    val out = File(root, entry.name).canonicalFile
                    if (!out.path.startsWith(root.path + File.separator)) {
                        throw IOException("zip entry '${entry.name}' leaves the model folder")
                    }
                    if (entry.isDirectory) {
                        out.mkdirs()
                    } else {
                        out.parentFile?.mkdirs()
                        out.outputStream().use { input.copyTo(it) }
                    }
                }
            }
        }
    }
}
