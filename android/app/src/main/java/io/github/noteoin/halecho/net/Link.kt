/*
 * The paired, encrypted connection to the PC. One thread connects, reads and reconnects:
 * the saved address first, then mDNS when that fails, with a growing pause between tries.
 * Writes come from any thread and are serialised. A ping every 20 s, and a read timeout of
 * three times that, notice a PC that vanished without closing the connection.
 */
package io.github.noteoin.halecho.net

import android.util.Log
import io.github.noteoin.halecho.Prefs
import io.github.noteoin.halecho.listen.Outbox
import org.json.JSONObject
import java.io.DataInputStream
import java.io.IOException
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.SocketTimeoutException
import javax.net.ssl.SSLSocket

class Link(
    private val prefs: Prefs,
    private val discovery: Discovery,
    private val handler: Handler,
    private val hello: () -> JSONObject,
) : Outbox {
    /** What the link delivers, on its own thread. */
    interface Handler {
        fun onConnected()
        fun onFrame(frame: Frames.Frame)
        fun onDisconnected(reason: String)
    }

    @Volatile private var running = false
    @Volatile private var socket: SSLSocket? = null
    @Volatile private var out: OutputStream? = null
    private var thread: Thread? = null
    private var pinger: Thread? = null

    override val connected: Boolean get() = out != null

    fun start() {
        if (running) return
        running = true
        thread = Thread(::run, "link").apply { start() }
        pinger = Thread(::ping, "link-ping").apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        runCatching { socket?.close() }
        thread?.interrupt()
        pinger?.interrupt()
    }

    override fun send(msg: JSONObject) = write(Frames.encodeJson(msg))

    override fun sendAudio(turn: Long, pcm: ShortArray) = write(Frames.encodeAudio(turn, 0, pcm))

    /** Keys and touches for a terminal screen. */
    fun sendTerm(term: Long, data: ByteArray) = write(Frames.encodeTerm(term, data))

    private fun write(frame: ByteArray) {
        val stream = out ?: return
        try {
            synchronized(stream) {
                stream.write(frame)
                stream.flush()
            }
        } catch (e: IOException) {
            Log.w(TAG, "send failed: ${e.message}")
            runCatching { socket?.close() }
        }
    }

    private fun run() {
        var backoff = MIN_BACKOFF_MS
        while (running) {
            val pin = prefs.pcFingerprint
            if (pin == null) {
                sleep(MIN_BACKOFF_MS)
                continue
            }
            val reason = try {
                session(pin, prefs.host, prefs.port)
                backoff = MIN_BACKOFF_MS
                "closed"
            } catch (e: IOException) {
                rediscover(pin)
                e.message ?: e.javaClass.simpleName
            }
            out = null
            handler.onDisconnected(reason)
            if (running) {
                sleep(backoff)
                backoff = minOf(backoff * 2, MAX_BACKOFF_MS)
            }
        }
    }

    private fun session(pin: String, host: String, port: Int) {
        val ssl = Pinning.context(pin).socketFactory.createSocket() as SSLSocket
        socket = ssl
        ssl.use {
            it.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            it.soTimeout = READ_TIMEOUT_MS
            it.enabledProtocols = arrayOf(Pinning.PROTOCOL)
            it.startHandshake()
            out = it.outputStream.buffered()
            Log.i(TAG, "connected to $host:$port")
            send(hello())
            handler.onConnected()
            val input = DataInputStream(it.inputStream.buffered())
            while (running) {
                try {
                    handler.onFrame(Frames.read(input))
                } catch (e: SocketTimeoutException) {
                    throw IOException("the PC stopped answering", e)
                }
            }
        }
    }

    private fun rediscover(pin: String) {
        val found = discovery.find(DISCOVERY_TIMEOUT_MS) { !it.pairing && pin.startsWith(it.fingerprintHint) }
        if (found != null && (found.host != prefs.host || found.port != prefs.port)) {
            Log.i(TAG, "the PC moved to ${found.host}:${found.port}")
            prefs.moved(found.host, found.port)
        }
    }

    private fun ping() {
        while (running) {
            sleep(PING_INTERVAL_MS)
            if (connected) send(JSONObject().put("type", "ping").put("t", System.currentTimeMillis()))
        }
    }

    private fun sleep(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }

    private companion object {
        const val TAG = "halecho-link"
        const val CONNECT_TIMEOUT_MS = 5_000
        const val PING_INTERVAL_MS = 20_000L
        const val READ_TIMEOUT_MS = 60_000
        const val DISCOVERY_TIMEOUT_MS = 5_000L
        const val MIN_BACKOFF_MS = 1_000L
        const val MAX_BACKOFF_MS = 30_000L
    }
}
