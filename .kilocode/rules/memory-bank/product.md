# Product Context: Xiaomi-FRAS (Face Recognition Attendance System)

## Why This Project Exists

Xiaomi-FRAS is a face recognition attendance system that automates attendance tracking using biometric face recognition. It replaces manual attendance methods with a secure, real-time system that uses face detection and liveness verification to prevent spoofing.

## Problems It Solves

1. **Manual Attendance Overhead**: Eliminates paper-based or manual digital attendance
2. **Identity Fraud**: Face recognition with liveness detection prevents buddy-punching
3. **Real-time Tracking**: Instant attendance logging with hardware integration
4. **Reporting**: Automated attendance reports and exports
5. **Administration**: Centralized admin panel for managing students, schedules, and attendance

## How It Should Work (User Flow)

1. Admin configures the system via admin panel
2. Students register with face data through the registration flow
3. Attendance is captured via face recognition at scheduled times
4. Liveness detection ensures real person presence
5. Reports are generated and can be exported
6. Hardware integration for camera and sensors

## Key User Experience Goals

- **Fast Recognition**: Quick face detection and matching
- **Security**: Liveness detection to prevent spoofing
- **Reliability**: Works with hardware integration
- **Clear Reporting**: Easy-to-read attendance reports

## Integration Points

- **Database**: SQLite/PostgreSQL for data persistence
- **Hardware**: Camera and sensor integration
- **WebSocket**: Real-time event streaming
- **Docker**: Containerized deployment
