package com.fras.sync

import com.fras.model.AttendanceResult
import com.fras.model.DeviceConfig
import com.google.gson.JsonObject
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @GET("api/health")
    suspend fun healthCheck(): Response<JsonObject>

    @POST("api/devices/register")
    suspend fun registerDevice(@Body body: JsonObject): Response<JsonObject>

    @GET("api/devices/{deviceId}/config")
    suspend fun getDeviceConfig(@Path("deviceId") deviceId: String): Response<DeviceConfig>

    @PUT("api/devices/{deviceId}/config")
    suspend fun updateDeviceConfig(
        @Path("deviceId") deviceId: String,
        @Body config: JsonObject
    ): Response<JsonObject>

    @POST("api/devices/{deviceId}/health")
    suspend fun reportHealth(
        @Path("deviceId") deviceId: String,
        @Body health: JsonObject
    ): Response<JsonObject>

    @POST("api/edge/result")
    suspend fun sendResult(@Body result: JsonObject): Response<AttendanceResult>

    @POST("api/edge/sync")
    suspend fun syncBatch(@Body batch: JsonObject): Response<JsonObject>
}

// Retrofit singleton
object ApiClient {
    private var service: ApiService? = null

    fun getService(baseUrl: String, apiKey: String): ApiService {
        if (service == null) {
            val client = okhttp3.OkHttpClient.Builder()
                .addInterceptor { chain ->
                    val request = chain.request().newBuilder()
                        .addHeader("X-API-Key", apiKey)
                        .addHeader("Content-Type", "application/json")
                        .build()
                    chain.proceed(request)
                }
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
                .build()

            service = retrofit2.Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(client)
                .addConverterFactory(retrofit2.converter.gson.GsonConverterFactory.create())
                .build()
                .create(ApiService::class.java)
        }
        return service!!
    }

    fun reset() { service = null }
}
