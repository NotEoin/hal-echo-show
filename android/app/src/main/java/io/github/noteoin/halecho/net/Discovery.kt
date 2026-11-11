/*
 * Finds the PC's mDNS announcement (`_hal-echo._tcp`, from halecho/discovery.py). The answer is
 * only an address: the link still refuses any certificate but the pinned one.
 */
package io.github.noteoin.halecho.net

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.util.Log
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** One resolved announcement. */
data class Found(val name: String, val host: String, val port: Int, val fingerprintHint: String, val pairing: Boolean)

class Discovery(context: Context) {
    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager

    /** The first announcement that matches, waiting at most [timeoutMs]. */
    fun find(timeoutMs: Long, match: (Found) -> Boolean): Found? {
        val done = CountDownLatch(1)
        var result: Found? = null
        // NsdManager on Android 11 resolves one service at a time, so candidates queue here
        val pending = ArrayDeque<NsdServiceInfo>()
        var resolving = false

        fun resolveNext() {
            val next = synchronized(pending) {
                if (resolving || pending.isEmpty()) return
                resolving = true
                pending.removeFirst()
            }
            nsd.resolveService(next, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, error: Int) {
                    synchronized(pending) { resolving = false }
                    resolveNext()
                }

                override fun onServiceResolved(info: NsdServiceInfo) {
                    val attrs = info.attributes
                    val found = Found(
                        name = info.serviceName,
                        host = info.host.hostAddress ?: "",
                        port = info.port,
                        fingerprintHint = attrs["fp"]?.toString(Charsets.US_ASCII) ?: "",
                        pairing = attrs["pair"]?.toString(Charsets.US_ASCII) == "1",
                    )
                    if (result == null && match(found)) {
                        result = found
                        done.countDown()
                    }
                    synchronized(pending) { resolving = false }
                    resolveNext()
                }
            })
        }

        val listener = object : NsdManager.DiscoveryListener {
            override fun onServiceFound(info: NsdServiceInfo) {
                synchronized(pending) { pending.addLast(info) }
                resolveNext()
            }

            override fun onStartDiscoveryFailed(type: String, error: Int) {
                Log.w(TAG, "mDNS discovery failed to start: $error")
                done.countDown()
            }

            override fun onDiscoveryStarted(type: String) = Unit
            override fun onDiscoveryStopped(type: String) = Unit
            override fun onServiceLost(info: NsdServiceInfo) = Unit
            override fun onStopDiscoveryFailed(type: String, error: Int) = Unit
        }
        nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
        try {
            done.await(timeoutMs, TimeUnit.MILLISECONDS)
        } finally {
            runCatching { nsd.stopServiceDiscovery(listener) }
        }
        return result
    }

    companion object {
        const val SERVICE_TYPE = "_hal-echo._tcp."
        private const val TAG = "halecho-discovery"
    }
}
