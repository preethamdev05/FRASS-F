# 📘 Operator Guide — Face Recognition Attendance System

Quick reference for anyone running the dashboard.

---

## Starting the System

**Windows:** Double-click `run.bat`
**Mac/Linux:** Open terminal → `bash run.sh`

First run takes ~2 minutes to install dependencies. After that, it starts instantly.

The server auto-restarts if it crashes.

## Opening the Dashboard

Open your browser to: **http://localhost:5000**

The dashboard shows:
- Total students registered
- Present / Late / Absent counts today
- Attendance rate percentage
- Department breakdown

---

## Step-by-Step Workflow

### 1. Register a Student

1. Click **Register** in the sidebar
2. Fill in Student ID (e.g., `CS2024001`), Name, Department
3. Click **Save Student**
4. Allow camera access when prompted
5. Take **3–5 photos** — look directly at the camera, good lighting, try slight angles
6. Minimum 3 photos required for reliable recognition

### 2. Run Live Attendance

1. Click **Attendance** in the sidebar
2. Adjust the **Tolerance** slider if needed (0.5 = default, lower = stricter)
3. Click **Start Attendance**
4. Position the camera to see students' faces
5. The system scans every 2 seconds and marks students automatically
6. Green box = recognized, Red box = unknown
7. Click **Stop Attendance** when done

### 3. Manual Mark (Override)

If a student wasn't recognized (bad lighting, hat, etc.):
1. Go to **Attendance** page
2. The system auto-marks via camera, but you can mark manually via the API or edit the database

### 4. View Reports

1. Click **Reports** in the sidebar
2. Set date range and optional student filter
3. Click **Load**
4. Click **Export CSV** to download

### 5. Manage Students

1. Click **Students** in the sidebar
2. Search by name, ID, or department
3. Click ✏️ to edit details
4. Click 🗑️ to delete (removes all face data and attendance)

---

## Tips for Best Recognition

| Do | Don't |
|---|---|
| Face the camera directly | Wear sunglasses or masks |
| Good, even lighting | Backlight (window behind you) |
| Capture 3–5 photos per student | Only take 1 photo |
| Try slight angle variations | Have multiple people in frame |

## Tolerance Settings

| Value | Behavior |
|---|---|
| 0.3 | Very strict — fewer false positives, more misses |
| 0.5 | **Default** — balanced |
| 0.7 | Loose — more matches, but more false positives |

Recommended: **0.5** for classrooms with good lighting.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "No face detected" | Improve lighting, face the camera directly |
| Camera not working | Check webcam connection, restart the app |
| Server won't start | Make sure port 5000 isn't used by another app |
| Deps won't install | Make sure Python 3.10+ is installed |
| Page won't load | Check the terminal — it shows the correct URL |

## Stopping the Server

Press **Ctrl+C** in the terminal where the server is running.

The server will auto-restart after 3 seconds. Close the terminal window to stop permanently.

---

## File Locations

| What | Where |
|---|---|
| Database | `attendance.db` (in the project folder) |
| Face photos | `face_data/` folder |
| CSV exports | Downloaded by your browser |

**Do not delete `attendance.db`** — it contains all student records and attendance history.
