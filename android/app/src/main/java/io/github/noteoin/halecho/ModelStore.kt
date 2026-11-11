/*
 * The speech models on the device, as the PC's welcome names them. A model is ready when its
 * folder holds the SHA-256 the PC announced; anything else is fetched again over the link.
 */
package io.github.noteoin.halecho

import io.github.noteoin.halecho.net.BlobReceiver
import java.io.File

class ModelStore(private val dir: File) {
    /** The model's file (Whisper) or folder (Vosk) when it is installed with this hash. */
    fun ready(name: String, sha256: String): File? {
        val folder = File(dir, name)
        val marker = File(folder, MARKER)
        if (!marker.exists() || marker.readText().trim() != sha256) return null
        return installed(folder)
    }

    /** Installs a verified download of [kind] `whisper` or `vosk`; returns its file or folder. */
    fun install(name: String, kind: String, sha256: String, download: File): File {
        val folder = File(dir, name)
        folder.deleteRecursively()
        folder.mkdirs()
        if (kind == "vosk") {
            BlobReceiver.unzip(download, folder)
            download.delete()
        } else {
            download.renameTo(File(folder, WHISPER_FILE))
        }
        File(folder, MARKER).writeText(sha256)
        return installed(folder)
    }

    private fun installed(folder: File): File {
        val whisper = File(folder, WHISPER_FILE)
        if (whisper.exists()) return whisper
        // a Vosk zip holds one top-level folder named after the model version
        return folder.listFiles()?.firstOrNull { it.isDirectory } ?: folder
    }

    private companion object {
        const val MARKER = ".sha256"
        const val WHISPER_FILE = "model.bin"
    }
}
