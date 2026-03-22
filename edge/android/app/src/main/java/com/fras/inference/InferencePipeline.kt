package com.fras.inference

import android.graphics.Bitmap
import com.fras.model.FaceResult

/**
 * End-to-end inference pipeline: detect → quality check → embed → liveness.
 */
class InferencePipeline(
    private val engine: FaceEngine,
    private val liveness: LivenessChecker
) {

    fun process(frame: Bitmap): FaceResult? {
        val startTime = System.currentTimeMillis()

        // 1. Detect faces
        val faces = engine.detectFaces(frame)
        if (faces.isEmpty()) return null

        // 2. Process largest face
        val face = faces.maxByOrNull { (it.x2 - it.x1) * (it.y2 - it.y1) } ?: return null

        // 3. Quality check
        val cropped = cropBitmap(frame, face)
        val quality = checkQuality(cropped)

        // 4. Get embedding
        val embedding = engine.getEmbedding(frame, face)
        if (embedding == null) {
            cropped.recycle()
            return null
        }

        // 5. Liveness check
        val livenessResult = liveness.analyze(cropped)

        val latency = System.currentTimeMillis() - startTime

        cropped.recycle()

        return FaceResult(
            boundingBox = floatArrayOf(face.x1, face.y1, face.x2, face.y2),
            embedding = embedding,
            landmarks = null,
            livenessScore = livenessResult.score,
            isLive = livenessResult.isLive,
            qualityScore = quality,
            qualityPass = quality > 0.5f,
            latencyMs = latency
        )
    }

    private fun cropBitmap(bitmap: Bitmap, face: DetectedFace): Bitmap {
        val x = face.x1.toInt().coerceIn(0, bitmap.width - 1)
        val y = face.y1.toInt().coerceIn(0, bitmap.height - 1)
        val w = (face.x2 - face.x1).toInt().coerceIn(1, bitmap.width - x)
        val h = (face.y2 - face.y1).toInt().coerceIn(1, bitmap.height - y)
        return Bitmap.createBitmap(bitmap, x, y, w, h)
    }

    private fun checkQuality(bitmap: Bitmap): Float {
        val w = bitmap.width
        val h = bitmap.height
        if (w < 80 || h < 80) return 0.2f
        return 0.8f  // Simplified — full implementation in LivenessChecker
    }
}
