package com.fras.camera

import android.content.Context
import android.graphics.Bitmap
import android.util.Size
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * CameraX-based camera manager with frame analysis.
 */
class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView
) {
    private var cameraProvider: ProcessCameraProvider? = null
    private var imageAnalyzer: ImageAnalysis? = null
    private var executor: ExecutorService = Executors.newSingleThreadExecutor()
    private var frameCallback: ((Bitmap) -> Unit)? = null
    private var isRunning = false

    fun start(callback: (Bitmap) -> Unit) {
        frameCallback = callback
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

        cameraProviderFuture.addListener({
            cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder()
                .setTargetResolution(Size(640, 480))
                .build()
                .also { it.setSurfaceProvider(previewView.surfaceProvider) }

            imageAnalyzer = ImageAnalysis.Builder()
                .setTargetResolution(Size(640, 480))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { analysis ->
                    analysis.setAnalyzer(executor) { imageProxy ->
                        processFrame(imageProxy)
                    }
                }

            val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

            try {
                cameraProvider?.unbindAll()
                cameraProvider?.bindToLifecycle(
                    lifecycleOwner, cameraSelector, preview, imageAnalyzer
                )
                isRunning = true
            } catch (e: Exception) {
                android.util.Log.e("CameraManager", "Camera binding failed", e)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun stop() {
        isRunning = false
        cameraProvider?.unbindAll()
    }

    fun release() {
        stop()
        executor.shutdown()
    }

    private fun processFrame(imageProxy: ImageProxy) {
        if (!isRunning || frameCallback == null) {
            imageProxy.close()
            return
        }

        try {
            // Convert YUV to Bitmap
            val bitmap = imageProxyToBitmap(imageProxy)
            if (bitmap != null) {
                frameCallback?.invoke(bitmap)
                bitmap.recycle()
            }
        } catch (e: Exception) {
            android.util.Log.w("CameraManager", "Frame processing error: ${e.message}")
        } finally {
            imageProxy.close()
        }
    }

    @androidx.camera.core.ExperimentalGetImage
    private fun imageProxyToBitmap(imageProxy: ImageProxy): Bitmap? {
        val image = imageProxy.image ?: return null

        // Convert YUV_420_888 to NV21 byte array
        val yBuffer = image.planes[0].buffer
        val uBuffer = image.planes[1].buffer
        val vBuffer = image.planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)

        yBuffer.get(nv21, 0, ySize)

        val uvPixelStride = image.planes[1].pixelStride
        val uvRowStride = image.planes[1].rowStride
        val uvWidth = image.width / 2

        var pos = ySize
        if (uvPixelStride == 2) {
            // Interleaved UV
            for (row in 0 until image.height / 2) {
                for (col in 0 until uvWidth) {
                    val vuIndex = row * uvRowStride + col * uvPixelStride
                    nv21[pos++] = vBuffer.get(vuIndex)
                    nv21[pos++] = uBuffer.get(vuIndex)
                }
            }
        } else {
            // Planar UV
            uBuffer.position(0)
            vBuffer.position(0)
            for (i in 0 until uSize) {
                nv21[pos++] = vBuffer.get()
                nv21[pos++] = uBuffer.get()
            }
        }

        // Convert NV21 to Bitmap
        val yuvImage = android.graphics.YuvImage(
            nv21, android.graphics.ImageFormat.NV21,
            image.width, image.height, null
        )

        val out = java.io.ByteArrayOutputStream()
        yuvImage.compressToJpeg(
            android.graphics.Rect(0, 0, image.width, image.height), 90, out
        )

        val bytes = out.toByteArray()
        return android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
}
