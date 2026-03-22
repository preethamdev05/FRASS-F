package com.fras.model

import android.content.Context
import androidx.room.*

@Dao
interface OfflineResultDao {
    @Query("SELECT * FROM offline_results WHERE synced = 0 ORDER BY timestamp ASC")
    suspend fun getPending(): List<OfflineResult>

    @Insert
    suspend fun insert(result: OfflineResult)

    @Query("UPDATE offline_results SET synced = 1 WHERE id = :id")
    suspend fun markSynced(id: Long)

    @Query("DELETE FROM offline_results WHERE synced = 1 AND timestamp < :cutoff")
    suspend fun deleteOld(cutoff: Long)

    @Query("SELECT COUNT(*) FROM offline_results WHERE synced = 0")
    suspend fun pendingCount(): Int
}

@Dao
interface AttendanceLogDao {
    @Query("SELECT * FROM attendance_log ORDER BY timestamp DESC LIMIT 100")
    suspend fun getRecent(): List<AttendanceLog>

    @Insert
    suspend fun insert(log: AttendanceLog)

    @Query("DELETE FROM attendance_log WHERE timestamp < :cutoff")
    suspend fun deleteOld(cutoff: Long)
}

@Database(entities = [OfflineResult::class, AttendanceLog::class], version = 1)
abstract class FrasDatabase : RoomDatabase() {
    abstract fun offlineResultDao(): OfflineResultDao
    abstract fun attendanceLogDao(): AttendanceLogDao

    companion object {
        @Volatile private var INSTANCE: FrasDatabase? = null

        fun getInstance(context: Context): FrasDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    FrasDatabase::class.java,
                    "fras.db"
                ).build().also { INSTANCE = it }
            }
        }
    }
}
