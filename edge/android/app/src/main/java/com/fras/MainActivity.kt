package com.fras

import android.Manifest
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.fras.camera.CameraManager
import com.fras.inference.*
import com.fras.model.AttendanceResult
import com.fras.sync.SyncManager
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {

    private lateinit var cameraPreview: PreviewView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var configButton: ImageButton
    private lateinit var statusText: TextView
    private lateinit var connectionDot: View
    private lateinit var fpsText: TextView
    private lateinit var resultPanel: LinearLayout
    private lateinit var resultName: TextView
    private lateinit var resultDetails: TextView
    private lateinit var markCountText: TextView
    private lateinit var offlineCountText: TextView

    private lateinit var prefs: SharedPreferences
    private lateinit var cameraManager: CameraManager
    private lateinit var faceEngine: FaceEngine
    private lateinit var livenessChecker: LivenessChecker
    private lateinit var pipeline: InferencePipeline
    private lateinit var syncManager: SyncManager

    private var isActive = false
    private var frameCount = 0
    private var lastFpsTime = System.currentTimeMillis()
    private var fps = 0

    companion object {
        private const val CAMERA_PERMISSION_CODE = 100
        private const val PREFS_NAME = "fras_prefs"
        private const val KEY_BACKEND_URL = "backend_url"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_API_KEY = "api_key"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        initPrefs()
        initEngine()

        startButton.setOnClickListener { startAttendance() }
        stopButton.setOnClickListener { stopAttendance() }
        configButton.setOnClickListener { showConfigDialog() }

        checkCameraPermission()
    }

    private fun initViews() {
        cameraPreview = findViewById(R.id.cameraPreview)
        startButton = findViewById(R.id.startButton)
        stopButton = findViewById(R.id.stopButton)
        configButton = findViewById(R.id.configButton)
        statusText = findViewById(R.id.statusText)
        connectionDot = findViewById(R.id.connectionDot)
        fpsText = findViewById(R.id.fpsText)
        resultPanel = findViewById(R.id.resultPanel)
        resultName = findViewById(R.id.resultName)
        resultDetails = findViewById(R.id.resultDetails)
        markCountText = findViewById(R.id.markCountText)
        offlineCountText = findViewById(R.id.offlineCountText)
    }

    private fun initPrefs() {
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
    }

    private fun initEngine() {
        faceEngine = FaceEngine(this)
        livenessChecker = LivenessChecker()

        // Load models in background
        CoroutineScope(Dispatchers.IO).launch {
            try {
                faceEngine.load()
                withContext(Dispatchers.Main) {
                    statusText.text = "Ready"
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    statusText.text = "Model load failed"
                    Toast.makeText(this@MainActivity, "Failed to load ML models: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }

        pipeline = InferencePipeline(faceEngine, livenessChecker)
    }

    private fun initSync() {
        val baseUrl = prefs.getString(KEY_BACKEND_URL, "http://192.168.1.100:8000") ?: "http://192.168.1.100:8000"
        val deviceId = prefs.getString(KEY_DEVICE_ID, "android-001") ?: "android-001"
        val apiKey = prefs.getString(KEY_API_KEY, "") ?: ""

        syncManager = SyncManager(this, baseUrl, apiKey, deviceId)
        syncManager.start()

        updateConnectionStatus()
    }

    private fun checkCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_PERMISSION_CODE)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_CODE && grantResults.isNotEmpty()
            && grantResults[0] != PackageManager.PERMISSION_GRANTED
        ) {
            Toast.makeText(this, R.string.camera_permission_required, Toast.LENGTH_LONG).show()
        }
    }

    private fun startAttendance() {
        if (!::syncManager.isInitialized) initSync()

        cameraManager = CameraManager(this, this, cameraPreview)
        cameraManager.start { bitmap ->
            processFrame(bitmap)
        }

        isActive = true
        startButton.visibility = View.GONE
        stopButton.visibility = View.VISIBLE
        statusText.text = "Scanning..."
        resultPanel.visibility = View.GONE
    }

    private fun stopAttendance() {
        isActive = false
        cameraManager.stop()
        startButton.visibility = View.VISIBLE
        stopButton.visibility = View.GONE
        statusText.text = "Stopped"
    }

    private fun processFrame(bitmap: android.graphics.Bitmap) {
        if (!isActive) return

        // Frame skipping for performance
        frameCount++
        if (frameCount % 2 != 0) return

        // FPS counter
        val now = System.currentTimeMillis()
        if (now - lastFpsTime >= 1000) {
            fps = frameCount
            frameCount = 0
            lastFpsTime = now
            runOnUiThread { fpsText.text = "$fps FPS" }
        }

        // Run inference
        val result = pipeline.process(bitmap) ?: return

        if (!result.qualityPass) return

        // Send to backend
        if (::syncManager.isInitialized) {
            syncManager.sendResult(result) { attendance ->
                handleAttendanceResult(attendance)
            }
        }

        // Update offline count
        if (::syncManager.isInitialized) {
            syncManager.getOfflineCount { count ->
                runOnUiThread {
                    offlineCountText.text = if (count > 0) " ($count offline)" else ""
                }
            }
        }
    }

    private fun handleAttendanceResult(result: AttendanceResult?) {
        runOnUiThread {
            if (result == null) {
                resultPanel.visibility = View.GONE
                return@runOnUiThread
            }

            resultPanel.visibility = View.VISIBLE

            when (result.status) {
                "marked" -> {
                    resultName.text = result.name ?: "Unknown"
                    resultName.setTextColor(Color.parseColor("#00C853"))
                    resultDetails.text = "${result.confidence?.toInt()}% confidence • ${result.attendanceStatus}"
                    markCountText.text = syncManager.getMarkCount().toString()
                }
                "unknown" -> {
                    resultName.text = getString(R.string.unknown_person)
                    resultName.setTextColor(Color.WHITE)
                    resultDetails.text = "${result.confidence?.toInt()}% confidence"
                }
                "duplicate" -> {
                    resultName.text = result.name ?: "Unknown"
                    resultName.setTextColor(Color.parseColor("#FFA000"))
                    resultDetails.text = "Already marked"
                }
                "rejected" -> {
                    resultPanel.visibility = View.GONE
                }
            }
        }
    }

    private fun updateConnectionStatus() {
        CoroutineScope(Dispatchers.Main).launch {
            while (isActive) {
                val connected = ::syncManager.isInitialized && syncManager.isConnected()
                connectionDot.setBackgroundResource(
                    if (connected) R.drawable.circle_green else R.drawable.circle_red
                )
                statusText.text = if (connected) getString(R.string.connected) else getString(R.string.disconnected)
                delay(5000)
            }
        }
    }

    private fun showConfigDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_config, null)
        val urlInput = dialogView.findViewById<TextInputEditText>(R.id.urlInput)
        val deviceIdInput = dialogView.findViewById<TextInputEditText>(R.id.deviceIdInput)
        val apiKeyInput = dialogView.findViewById<TextInputEditText>(R.id.apiKeyInput)

        urlInput.setText(prefs.getString(KEY_BACKEND_URL, "http://192.168.1.100:8000"))
        deviceIdInput.setText(prefs.getString(KEY_DEVICE_ID, "android-001"))
        apiKeyInput.setText(prefs.getString(KEY_API_KEY, ""))

        AlertDialog.Builder(this)
            .setTitle(R.string.config)
            .setView(dialogView)
            .setPositiveButton(R.string.save) { _, _ ->
                prefs.edit()
                    .putString(KEY_BACKEND_URL, urlInput.text.toString().trim())
                    .putString(KEY_DEVICE_ID, deviceIdInput.text.toString().trim())
                    .putString(KEY_API_KEY, apiKeyInput.text.toString().trim())
                    .apply()

                // Reset sync with new config
                if (::syncManager.isInitialized) syncManager.stop()
                ApiClient.reset()
                initSync()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isActive) cameraManager.release()
        if (::syncManager.isInitialized) syncManager.stop()
        if (::faceEngine.isInitialized) faceEngine.close()
    }
}
