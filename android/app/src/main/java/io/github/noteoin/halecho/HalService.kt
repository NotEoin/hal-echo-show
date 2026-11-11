/*
 * The always-on part of the app, a foreground service started at boot and by the home screen:
 * it owns the microphone, the speaker, the link to the PC and the speech models, and joins them
 * through Listener. The PC's `welcome` names the models; missing ones are fetched over the link
 * before listening starts.
 */
package io.github.noteoin.halecho

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import io.github.noteoin.halecho.audio.Capture
import io.github.noteoin.halecho.audio.Player
import io.github.noteoin.halecho.audio.levelDb
import io.github.noteoin.halecho.listen.Listener
import io.github.noteoin.halecho.listen.ListenerSettings
import io.github.noteoin.halecho.listen.ListenerUi
import io.github.noteoin.halecho.listen.Speaker
import io.github.noteoin.halecho.listen.Spotter
import io.github.noteoin.halecho.listen.Transcriber
import io.github.noteoin.halecho.net.BlobReceiver
import io.github.noteoin.halecho.net.Discovery
import io.github.noteoin.halecho.net.Frames
import io.github.noteoin.halecho.net.Link
import io.github.noteoin.halecho.stt.VoskSpotter
import io.github.noteoin.halecho.stt.Whisper
import io.github.noteoin.halecho.update.Updater
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.Executors

class HalService : Service(), Link.Handler {
    private lateinit var prefs: Prefs
    private lateinit var link: Link
    private lateinit var models: ModelStore
    private lateinit var blobs: BlobReceiver
    private val worker = Executors.newSingleThreadExecutor { Thread(it, "transcribe") }
    private val player = Player { UiState.level = it }
    private val capture = Capture(::onMicFrame)

    @Volatile private var listener: Listener? = null
    private var spotter: VoskSpotter? = null
    private var whisper: Whisper? = null
    private var welcome: JSONObject? = null
    private var sayRate = 0
    private var sayTurn = 0L
    @Volatile private var droppedTurn = -1L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        models = ModelStore(File(filesDir, "models"))
        blobs = BlobReceiver(File(cacheDir, "incoming"), ::onBlob)
        link = Link(prefs, Discovery(this), this, ::hello)
        Updater.report = { ok, message ->
            link.send(JSONObject().put("type", "update_result").put("ok", ok).put("message", message))
        }
        startForeground(NOTIFICATION_ID, notification())
        UiState.paired = prefs.paired
        UiState.status = if (prefs.paired) "Connecting to ${prefs.pcName}" else "Not paired"
        capture.start()
        link.start()
        Log.i(TAG, "whisper: ${Whisper.systemInfo()}")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_REPAIRED) {
            UiState.paired = prefs.paired
            link.stop()
            link = Link(prefs, Discovery(this), this, ::hello)
            link.start()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        capture.stop()
        link.stop()
        player.stop()
        worker.shutdownNow()
        spotter?.close()
        whisper?.close()
        super.onDestroy()
    }

    private fun hello(): JSONObject = JSONObject()
        .put("type", "hello")
        .put("app_version", BuildConfig.VERSION_NAME)
        .put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
        .put("muted", UiState.muted)

    private fun onMicFrame(frame: ShortArray) {
        val active = listener
        if (active != null) active.onFrame(frame) else UiState.micDb = levelDb(frame)
    }

    // -- the link ------------------------------------------------------------------
    override fun onConnected() {
        UiState.connected = true
        UiState.status = "Connected to ${prefs.pcName}"
    }

    override fun onDisconnected(reason: String) {
        UiState.connected = false
        UiState.thinking = false
        UiState.status = "Can't reach ${prefs.pcName}: $reason"
        player.stop()
        listener?.onDisconnected()
    }

    override fun onFrame(frame: Frames.Frame) {
        when (frame.kind) {
            Frames.AUDIO -> onAudio(frame)
            Frames.BLOB -> runCatching { blobs.chunk(frame) }.onFailure { Log.e(TAG, "transfer failed", it) }
            Frames.JSON -> onMessage(frame.json())
        }
    }

    private fun onAudio(frame: Frames.Frame) {
        val turn = frame.id()
        if (turn == droppedTurn || turn != sayTurn) return
        val pcm = Frames.samples(frame.payload, frame.audioOffset, frame.payload.size - frame.audioOffset)
        player.enqueue(sayRate, pcm)
        UiState.speaking = true
    }

    private fun onMessage(msg: JSONObject) {
        when (msg.getString("type")) {
            "welcome" -> onWelcome(msg)
            "state" -> UiState.thinking = msg.optString("state") == "thinking"
            "say" -> {
                sayTurn = msg.getLong("turn")
                sayRate = msg.getInt("sr")
                UiState.thinking = false
                UiState.caption = msg.optString("text")
            }
            "turn_end" -> UiState.thinking = false
            "blob_begin" -> runCatching { blobs.begin(msg) }.onFailure { Log.e(TAG, "transfer refused", it) }
            "blob_end" -> runCatching { blobs.end(msg) }.onFailure { Log.e(TAG, "transfer failed", it) }
            "error" -> Log.w(TAG, "the PC reports: ${msg.optString("message")}")
        }
        listener?.onMessage(msg)
    }

    private fun onWelcome(msg: JSONObject) {
        welcome = msg
        prefs.mode = msg.optString("mode")
        UiState.status = "${msg.optString("device_name")} (${msg.optString("mode")}) on ${msg.optString("server_name")}"
        listener?.configure(ListenerSettings.from(msg.optJSONObject("listener")))
        if (listener == null) prepareModels()
    }

    // -- models ----------------------------------------------------------------------
    private fun prepareModels() {
        val msg = welcome ?: return
        val wanted = msg.optJSONObject("models") ?: return
        val missing = wanted.keys().asSequence().filter { name ->
            models.ready(name, wanted.getJSONObject(name).getString("sha256")) == null
        }.toList()
        if (missing.isNotEmpty()) {
            UiState.modelsReady = false
            UiState.status = "Fetching speech models from the PC"
            missing.forEach { link.send(JSONObject().put("type", "need_model").put("name", it)) }
            return
        }
        worker.execute(::startListening)
    }

    private fun onBlob(purpose: String, name: String, file: File) {
        when (purpose) {
            "model" -> {
                val info = welcome?.optJSONObject("models")?.optJSONObject(name) ?: return
                models.install(name, info.getString("kind"), info.getString("sha256"), file)
                prepareModels()
            }
            "update" -> Updater.install(this, file)
        }
    }

    private fun startListening() {
        val msg = welcome ?: return
        val settings = msg.getJSONObject("listener")
        val wanted = msg.getJSONObject("models")
        fun path(key: String): File {
            val name = settings.getString(key)
            return models.ready(name, wanted.getJSONObject(name).getString("sha256"))
                ?: throw IOException("model $name is not installed")
        }
        val phrases = settings.optJSONArray("wake_phrases") ?: JSONArray()
        val newSpotter = VoskSpotter(path("wake_model"), List(phrases.length()) { phrases.getString(it) })
        val sttOnDevice = settings.optString("stt_location", "device") != "pc"
        val newWhisper = if (sttOnDevice) {
            Whisper(path("stt_model"), Runtime.getRuntime().availableProcessors(), settings.optInt("stt_audio_ctx", 0))
        } else {
            null
        }
        spotter = newSpotter
        whisper = newWhisper
        listener = Listener(
            spotter = newSpotter as Spotter,
            transcriber = newWhisper ?: Transcriber { "" },
            outbox = link,
            speaker = object : Speaker {
                override val playing: Boolean get() = player.playing
                override fun stop() {
                    droppedTurn = sayTurn
                    player.stop()
                }
            },
            ui = object : ListenerUi {
                override fun roomAwake(awake: Boolean) { UiState.roomAwake = awake }
                override fun muted(muted: Boolean) { UiState.muted = muted }
                override fun listening(active: Boolean) { UiState.listening = active }
                override fun heard(text: String) { if (text.isNotBlank()) UiState.caption = "\"$text\"" }
                override fun level(db: Double) {
                    UiState.micDb = db
                    UiState.speaking = player.playing
                }
            },
            worker = worker,
        ).also { it.configure(ListenerSettings.from(settings)) }
        UiState.modelsReady = true
        UiState.status = "Listening"
    }

    private fun notification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Hal", NotificationManager.IMPORTANCE_MIN))
        return Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.notification_title))
            .setSmallIcon(R.drawable.ic_eye)
            .build()
    }

    companion object {
        private const val TAG = "halecho-service"
        private const val CHANNEL = "hal"
        private const val NOTIFICATION_ID = 1
        const val ACTION_REPAIRED = "io.github.noteoin.halecho.REPAIRED"

        fun start(context: Context, action: String? = null) {
            context.startForegroundService(Intent(context, HalService::class.java).setAction(action))
        }
    }
}
