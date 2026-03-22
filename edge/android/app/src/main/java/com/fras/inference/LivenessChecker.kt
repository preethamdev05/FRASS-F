package com.fras.inference

import android.graphics.Bitmap
import android.graphics.Color
import kotlin.math.sqrt

/**
 * On-device liveness detection using heuristic signals.
 * Checks: texture variance, skin color distribution, face size, brightness.
 */
class LivenessChecker(private val threshold: Float = 0.5f) {

    data class LivenessResult(
        val score: Float,
        val isLive: Boolean,
        val textureScore: Float,
        val skinScore: Float,
        val qualityScore: Float
    )

    fun analyze(bitmap: Bitmap): LivenessResult {
        val texture = checkTexture(bitmap)
        val skin = checkSkinColor(bitmap)
        val quality = checkQuality(bitmap)

        val score = 0.4f * texture + 0.3f * skin + 0.3f * quality
        val isLive = score >= threshold

        return LivenessResult(
            score = score,
            isLive = isLive,
            textureScore = texture,
            skinScore = skin,
            qualityScore = quality
        )
    }

    private fun checkTexture(bitmap: Bitmap): Float {
        // Block variance — real faces have micro-texture
        val size = 64
        val resized = Bitmap.createScaledBitmap(bitmap, size, size, true)
        val pixels = IntArray(size * size)
        resized.getPixels(pixels, 0, size, 0, 0, size, size)

        val blockSize = 8
        val variances = mutableListOf<Float>()

        for (by in 0 until size step blockSize) {
            for (bx in 0 until size step blockSize) {
                val block = mutableListOf<Float>()
                for (y in by until (by + blockSize).coerceAtMost(size)) {
                    for (x in bx until (bx + blockSize).coerceAtMost(size)) {
                        val pixel = pixels[y * size + x]
                        val gray = (Color.red(pixel) * 0.299f + Color.green(pixel) * 0.587f + Color.blue(pixel) * 0.114f)
                        block.add(gray)
                    }
                }
                if (block.isNotEmpty()) {
                    val mean = block.sum() / block.size
                    val variance = block.map { (it - mean) * (it - mean) }.sum() / block.size
                    variances.add(variance)
                }
            }
        }

        resized.recycle()

        if (variances.isEmpty()) return 0.5f
        val meanVar = variances.sum() / variances.size
        return (meanVar / 200.0f).coerceIn(0f, 1f)
    }

    private fun checkSkinColor(bitmap: Bitmap): Float {
        // YCrCb skin detection
        val size = 64
        val resized = Bitmap.createScaledBitmap(bitmap, size, size, true)
        val pixels = IntArray(size * size)
        resized.getPixels(pixels, 0, size, 0, 0, size, size)

        var skinPixels = 0
        for (pixel in pixels) {
            val r = Color.red(pixel)
            val g = Color.green(pixel)
            val b = Color.blue(pixel)

            // RGB to YCrCb
            val y = 0.299f * r + 0.587f * g + 0.114f * b
            val cr = 128 + 0.5f * r - 0.4187f * g - 0.0813f * b
            val cb = 128 - 0.1687f * r - 0.3313f * g + 0.5f * b

            if (cr in 133f..173f && cb in 77f..127f) {
                skinPixels++
            }
        }

        resized.recycle()

        val ratio = skinPixels.toFloat() / (size * size)
        return if (ratio in 0.15f..0.75f) 0.8f else 0.4f
    }

    private fun checkQuality(bitmap: Bitmap): Float {
        // Brightness + resolution check
        val w = bitmap.width
        val h = bitmap.height

        if (w < 80 || h < 80) return 0.2f

        val pixels = IntArray((w * h).coerceAtMost(10000))
        val step = if (w * h > 10000) (w * h) / 10000 else 1
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)

        var totalBrightness = 0.0
        val sampled = if (step > 1) pixels.size else pixels.size
        for (i in pixels.indices step step) {
            val pixel = pixels[i]
            totalBrightness += Color.red(pixel) * 0.299 + Color.green(pixel) * 0.587 + Color.blue(pixel) * 0.114
        }
        val avgBrightness = totalBrightness / (sampled / step)

        return when {
            avgBrightness < 40 -> 0.2f
            avgBrightness > 220 -> 0.3f
            else -> 0.8f
        }
    }
}
