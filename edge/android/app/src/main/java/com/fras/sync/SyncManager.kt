package com.fras.sync

import android.content.Context
import android.util.Log
import com.fras.model.*
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import kotlinx.coroutines.*
import java.util.UUID

/**
 * Handles sync between device and backend:
 * - Sends inference results via REST
 * - Queues offline when backend unreachable
 * - Flushes offline queue when reconnected
 * - Reports device health periodically
 */
class SyncManager(
    private val context: Context,
    private val baseUrl: String,
    private val apiKey: String,
    private val deviceId: String
) {

    companion object {
        private const val TAG = "SyncManager"
        private const val SYNC_INTERVAL_MS = 30_000L
        private const val HEALTH_INTERVAL_MS = 60_000L
    }

    private val db = FrasDatabase.getInstance(context)
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val gson = Gson()
    private var connected = false
    private var syncJob: Job? = null
    private var startTime = System.currentTimeMillis()
    private var markCount = 0

    fun start() {
        registerDevice()
        startPeriodicSync()
    }

    fun stop() {
        syncJob?.cancel()
        scope.cancel()
    }

    fun sendResult(result: FaceResult, callback: (AttendanceResult?) -> Unit) {
        scope.launch {
            try {
                val service = ApiClient.getService(baseUrl, apiKey)
                val body = JsonObject().apply {
                    addProperty("device_id", deviceId)
                    addProperty("nonce", "$deviceId:${System.currentTimeMillis()}:${UUID.randomUUID()}")
                    addProperty("timestamp", System.currentTimeMillis() / 1000.0)
                    add("embedding", gson.toJsonTree(result.embedding.toList()))
                    addProperty("liveness_score", result.livenessScore)
                    addProperty("is_live", result.isLive)
                }

                val response = service.sendResult(body)
                withContext(Dispatchers.Main) {
                    if (response.isSuccessful) {
                        connected = true
                        val attendance = response.body()
                        if (attendance != null && attendance.status == "marked") {
                            markCount++
                            callback(attendance)
                        } else {
                            callback(attendance)
                        }
                    } else {
                        queueOffline(result)
                        callback(null)
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Send failed, queuing offline: ${e.message}")
                queueOffline(result)
                withContext(Dispatchers.Main) { callback(null) }
            }
        }
    }

    private fun queueOffline(result: FaceResult) {
        scope.launch {
            try {
                db.offlineResultDao().insert(
                    OfflineResult(
                        deviceId = deviceId,
                        embeddingJson = gson.toJson(result.embedding.toList()),
                        livenessScore = result.livenessScore,
                        isLive = result.isLive,
                        nonce = "$deviceId:${System.currentTimeMillis()}:${UUID.randomUUID()}",
                        timestamp = System.currentTimeMillis()
                    )
                )
                Log.i(TAG, "Result queued offline")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to queue offline", e)
            }
        }
    }

    fun getOfflineCount(callback: (Int) -> Unit) {
        scope.launch {
            val count = db.offlineResultDao().pendingCount()
            withContext(Dispatchers.Main) { callback(count) }
        }
    }

    fun getMarkCount(): Int = markCount

    private fun startPeriodicSync() {
        syncJob = scope.launch {
            while (isActive) {
                delay(SYNC_INTERVAL_MS)
                flushOfflineQueue()
                reportHealth()
            }
        }
    }

    private fun flushOfflineQueue() {
        scope.launch {
            try {
                val pending = db.offlineResultDao().getPending()
                if (pending.isEmpty()) return@launch

                Log.i(TAG, "Flushing ${pending.size} offline results")
                val service = ApiClient.getService(baseUrl, apiKey)

                val results = JsonArray()
                for (item in pending) {
                    val obj = JsonObject().apply {
                        add("embedding", gson.fromJson(item.embeddingJson, JsonArray::class.java))
                        addProperty("liveness_score", item.livenessScore)
                        addProperty("is_live", item.isLive)
                        addProperty("nonce", item.nonce)
                        addProperty("timestamp", item.timestamp / 1000.0)
                    }
                    results.add(obj)
                }

                val batch = JsonObject().apply {
                    addProperty("device_id", deviceId)
                    add("results", results)
                }

                val response = service.syncBatch(batch)
                if (response.isSuccessful) {
                    val processed = response.body()?.get("processed")?.asInt ?: 0
                    Log.i(TAG, "Synced $processed offline results")
                    // Mark as synced
                    for (item in pending) {
                        db.offlineResultDao().markSynced(item.id)
                    }
                    connected = true
                }
            } catch (e: Exception) {
                Log.w(TAG, "Offline sync failed: ${e.message}")
            }
        }
    }

    private fun reportHealth() {
        scope.launch {
            try {
                val service = ApiClient.getService(baseUrl, apiKey)
                val body = JsonObject().apply {
                    addProperty("uptime", (System.currentTimeMillis() - startTime) / 1000)
                    addProperty("memory_mb", Runtime.getRuntime().totalMemory() / 1024 / 1024)
                    addProperty("fps", 0) // Updated by MainActivity
                    addProperty("queue_size", db.offlineResultDao().pendingCount())
                }
                service.reportHealth(deviceId, body)
                connected = true
            } catch (e: Exception) {
                connected = false
            }
        }
    }

    private fun registerDevice() {
        scope.launch {
            try {
                val service = ApiClient.getService(baseUrl, apiKey)
                val body = JsonObject().apply {
                    addProperty("device_id", deviceId)
                    addProperty("name", "Android-$deviceId")
                    addProperty("location", android.os.Build.MODEL)
                }
                val response = service.registerDevice(body)
                if (response.isSuccessful) {
                    connected = true
                    Log.i(TAG, "Device registered: $deviceId")
                }
            } catch (e: Exception) {
                Log.w(TAG, "Device registration failed: ${e.message}")
            }
        }
    }

    fun isConnected(): Boolean = connected
}
