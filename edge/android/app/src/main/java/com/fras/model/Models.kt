package com.fras.model

import androidx.room.Entity
import androidx.room.PrimaryKey

// Face detection result
data class FaceResult(
    val boundingBox: FloatArray,  // [x1, y1, x2, y2]
    val embedding: FloatArray,    // 512-dim
    val landmarks: FloatArray?,   // 5-point landmarks
    val livenessScore: Float,
    val isLive: Boolean,
    val qualityScore: Float,
    val qualityPass: Boolean,
    val latencyMs: Long
) {
    fun toMap(): Map<String, Any> {
        return mapOf(
            "embedding" to embedding.toList(),
            "liveness_score" to livenessScore,
            "is_live" to isLive,
            "quality" to mapOf(
                "pass" to qualityPass,
                "score" to qualityScore
            ),
            "latency_ms" to latencyMs
        )
    }
}

// Attendance result from server
data class AttendanceResult(
    val status: String,      // marked, unknown, duplicate, rejected
    val userId: Int?,
    val name: String?,
    val confidence: Float?,
    val attendanceStatus: String?
)

// Server response wrapper
data class ApiResponse<T>(
    val status: String,
    val data: T?,
    val error: String?
)

// Device config from server
data class DeviceConfig(
    val recognitionThreshold: Float = 0.65f,
    val livenessThreshold: Float = 0.65f,
    val dedupCooldown: Int = 300,
    val minEmbeddingQuality: Float = 0.85f,
    val cameraFps: Int = 15,
    val frameSkip: Int = 2
)

// Room entity for offline queue
@Entity(tableName = "offline_results")
data class OfflineResult(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val deviceId: String,
    val embeddingJson: String,   // serialized embedding as JSON array
    val livenessScore: Float,
    val isLive: Boolean,
    val nonce: String,
    val timestamp: Long,         // unix epoch ms
    val synced: Boolean = false
)

// Room entity for attendance log (local cache)
@Entity(tableName = "attendance_log")
data class AttendanceLog(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val userId: Int,
    val name: String,
    val studentId: String,
    val confidence: Float,
    val livenessScore: Float,
    val status: String,
    val timestamp: Long
)
