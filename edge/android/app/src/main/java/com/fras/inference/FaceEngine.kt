package com.fras.inference

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import ai.onnxruntime.*
import java.nio.FloatBuffer

/**
 * ONNX Runtime-based face detection and embedding engine.
 * Loads models from assets:
 *   - retinaface_mnet25.onnx  (face detection)
 *   - arcface_r100.onnx       (512-D face embedding)
 */
class FaceEngine(private val context: Context) {

    private var env: OrtEnvironment? = null
    private var detSession: OrtSession? = null
    private var embSession: OrtSession? = null
    private var loaded = false

    companion object {
        private const val TAG = "FaceEngine"
        private const val DET_MODEL = "retinaface_mnet25.onnx"
        private const val EMB_MODEL = "arcface_r100.onnx"
        private const val DET_SIZE = 640
        private const val EMB_SIZE = 112
        private const val EMBEDDING_DIM = 512
    }

    fun load() {
        if (loaded) return
        try {
            env = OrtEnvironment.getEnvironment()
            val opts = OrtSession.SessionOptions().apply {
                addNnapi()  // Use Android NNAPI for hardware acceleration
                setIntraOpNumThreads(4)
            }

            // Load detection model
            context.assets.open(DET_MODEL).use { stream ->
                val modelBytes = stream.readBytes()
                detSession = env!!.createSession(modelBytes, opts)
                Log.i(TAG, "Detection model loaded: ${modelBytes.size / 1024 / 1024}MB")
            }

            // Load embedding model
            context.assets.open(EMB_MODEL).use { stream ->
                val modelBytes = stream.readBytes()
                embSession = env!!.createSession(modelBytes, opts)
                Log.i(TAG, "Embedding model loaded: ${modelBytes.size / 1024 / 1024}MB")
            }

            loaded = true
            Log.i(TAG, "Face engine ready")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load models", e)
            throw e
        }
    }

    fun detectFaces(bitmap: Bitmap): List<DetectedFace> {
        if (!loaded) load()

        val resized = Bitmap.createScaledBitmap(bitmap, DET_SIZE, DET_SIZE, true)
        val input = preprocessDetection(resized)

        val inputName = detSession!!.inputNames.iterator().next()
        val tensor = OnnxTensor.createTensor(env, input, longArrayOf(1, 3, DET_SIZE.toLong(), DET_SIZE.toLong()))

        val results = detSession!!.run(mapOf(inputName to tensor))
        tensor.close()

        // Parse detection outputs (bbox + confidence + landmarks)
        val faces = parseDetectionResults(results, bitmap.width, bitmap.height)

        results.close()
        resized.recycle()

        return faces
    }

    fun getEmbedding(bitmap: Bitmap, face: DetectedFace): FloatArray? {
        if (!loaded) load()

        try {
            // Crop and align face
            val cropped = cropFace(bitmap, face)
            val aligned = Bitmap.createScaledBitmap(cropped, EMB_SIZE, EMB_SIZE, true)
            val input = preprocessEmbedding(aligned)

            val inputName = embSession!!.inputNames.iterator().next()
            val tensor = OnnxTensor.createTensor(env, input, longArrayOf(1, 3, EMB_SIZE.toLong(), EMB_SIZE.toLong()))

            val results = embSession!!.run(mapOf(inputName to tensor))
            tensor.close()

            val output = results[0].value as Array<FloatArray>
            val embedding = output[0]

            // L2 normalize
            val norm = kotlin.math.sqrt(embedding.sumOf { (it * it).toDouble() }).toFloat()
            val normalized = embedding.map { it / norm }.toFloatArray()

            results.close()
            cropped.recycle()
            aligned.recycle()

            return normalized
        } catch (e: Exception) {
            Log.e(TAG, "Embedding extraction failed", e)
            return null
        }
    }

    private fun preprocessDetection(bitmap: Bitmap): FloatBuffer {
        val pixels = IntArray(DET_SIZE * DET_SIZE)
        bitmap.getPixels(pixels, 0, DET_SIZE, 0, 0, DET_SIZE, DET_SIZE)

        val buffer = FloatBuffer.allocate(3 * DET_SIZE * DET_SIZE)
        val chw = FloatArray(3 * DET_SIZE * DET_SIZE)

        for (i in pixels.indices) {
            val pixel = pixels[i]
            chw[i] = ((pixel shr 16 and 0xFF) - 127.5f) / 128.0f                     // R
            chw[DET_SIZE * DET_SIZE + i] = ((pixel shr 8 and 0xFF) - 127.5f) / 128.0f // G
            chw[2 * DET_SIZE * DET_SIZE + i] = ((pixel and 0xFF) - 127.5f) / 128.0f   // B
        }

        buffer.put(chw)
        buffer.rewind()
        return buffer
    }

    private fun preprocessEmbedding(bitmap: Bitmap): FloatBuffer {
        val pixels = IntArray(EMB_SIZE * EMB_SIZE)
        bitmap.getPixels(pixels, 0, EMB_SIZE, 0, 0, EMB_SIZE, EMB_SIZE)

        val buffer = FloatBuffer.allocate(3 * EMB_SIZE * EMB_SIZE)
        val chw = FloatArray(3 * EMB_SIZE * EMB_SIZE)

        for (i in pixels.indices) {
            val pixel = pixels[i]
            chw[i] = ((pixel shr 16 and 0xFF) / 255.0f - 0.5f) / 0.5f                     // R
            chw[EMB_SIZE * EMB_SIZE + i] = ((pixel shr 8 and 0xFF) / 255.0f - 0.5f) / 0.5f // G
            chw[2 * EMB_SIZE * EMB_SIZE + i] = ((pixel and 0xFF) / 255.0f - 0.5f) / 0.5f   // B
        }

        buffer.put(chw)
        buffer.rewind()
        return buffer
    }

    private fun parseDetectionResults(results: OrtSession.Result, origW: Int, origH: Int): List<DetectedFace> {
        // Simplified parsing — actual output format depends on the ONNX model
        // This handles RetinaFace-style output: [batch, num_anchors, 5] (x1,y1,x2,y2,score)
        val faces = mutableListOf<DetectedFace>()
        try {
            val output = results[0].value as Array<Array<FloatArray>>
            val detections = output[0]

            val scaleX = origW.toFloat() / DET_SIZE
            val scaleY = origH.toFloat() / DET_SIZE

            for (det in detections) {
                if (det.size >= 5 && det[4] > 0.5f) { // confidence threshold
                    faces.add(DetectedFace(
                        x1 = (det[0] * scaleX).coerceIn(0f, origW.toFloat()),
                        y1 = (det[1] * scaleY).coerceIn(0f, origH.toFloat()),
                        x2 = (det[2] * scaleX).coerceIn(0f, origW.toFloat()),
                        y2 = (det[3] * scaleY).coerceIn(0f, origH.toFloat()),
                        confidence = det[4]
                    ))
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Detection parsing failed: ${e.message}")
        }
        return faces
    }

    private fun cropFace(bitmap: Bitmap, face: DetectedFace): Bitmap {
        val x = face.x1.toInt().coerceIn(0, bitmap.width - 1)
        val y = face.y1.toInt().coerceIn(0, bitmap.height - 1)
        val w = (face.x2 - face.x1).toInt().coerceIn(1, bitmap.width - x)
        val h = (face.y2 - face.y1).toInt().coerceIn(1, bitmap.height - y)
        return Bitmap.createBitmap(bitmap, x, y, w, h)
    }

    fun close() {
        detSession?.close()
        embSession?.close()
        env?.close()
        loaded = false
    }
}

data class DetectedFace(
    val x1: Float,
    val y1: Float,
    val x2: Float,
    val y2: Float,
    val confidence: Float
)
