/*
 * Installs an app update the PC sent (already checked against its SHA-256). Android shows its
 * own confirmation screen, so an update always needs a tap on the device, and it refuses any
 * APK not signed with the key this app was signed with.
 */
package io.github.noteoin.halecho.update

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log
import java.io.File

object Updater {
    private const val TAG = "halecho-update"
    const val ACTION = "io.github.noteoin.halecho.UPDATE_STATUS"

    /** Called with each installer status message, for the PC's log. */
    @Volatile var report: (ok: Boolean, message: String) -> Unit = { _, _ -> }

    fun install(context: Context, apk: File) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(context.packageName)
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            session.openWrite("update.apk", 0, apk.length()).use { out ->
                apk.inputStream().use { it.copyTo(out) }
                session.fsync(out)
            }
            val intent = Intent(context, StatusReceiver::class.java).setAction(ACTION)
            val pending = PendingIntent.getBroadcast(
                context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            session.commit(pending.intentSender)
        }
        apk.delete()
    }

    /** Opens Android's confirmation screen, then reports the outcome. */
    class StatusReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
            val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""
            when (status) {
                PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                    @Suppress("DEPRECATION") // the typed overload is API 33; the device runs 30
                    val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                    context.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    report(true, "waiting for a tap on the device")
                }
                PackageInstaller.STATUS_SUCCESS -> report(true, "installed")
                else -> {
                    Log.w(TAG, "update failed: $status $message")
                    report(false, "failed ($status): $message")
                }
            }
        }
    }
}
