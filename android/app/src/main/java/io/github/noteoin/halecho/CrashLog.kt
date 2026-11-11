/*
 * Keeps the stack trace of a crash so the PC can log it: with USB debugging off, as it should be
 * after setup, the device's own log is out of reach. The trace is written before Android's own
 * handler ends the process, and sent once on the next connection.
 */
package io.github.noteoin.halecho

import android.content.Context
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

object CrashLog {
    private const val FILE = "last-crash.txt"
    private const val MAX_CHARS = 8000 // the top of a trace says where; a JSON frame stays small

    /** Records uncaught exceptions to a file, then lets Android handle them as before. */
    fun install(context: Context) {
        val file = File(context.filesDir, FILE)
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                val trace = StringWriter().also { error.printStackTrace(PrintWriter(it)) }.toString()
                file.writeText("thread ${thread.name}, app ${BuildConfig.VERSION_NAME}\n${trace.take(MAX_CHARS)}")
            }
            previous?.uncaughtException(thread, error)
        }
    }

    /** The saved trace, once: it is deleted as it is read. */
    fun take(context: Context): String? {
        val file = File(context.filesDir, FILE)
        if (!file.exists()) return null
        return runCatching { file.readText() }.getOrNull().also { file.delete() }
    }
}
