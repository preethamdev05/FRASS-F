from datetime import datetime, timedelta

from locust import HttpUser, between, task


class FRASUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "loadtest@example.com", "password": "loadtest123"},
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 200:
            self.token = response.cookies.get("token")
        else:
            self.environment.runner.quit()

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        return headers

    @task(3)
    def view_dashboard(self):
        self.client.get(
            "/api/attendance/dashboard",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )

    @task(3)
    def get_attendance_stats(self):
        self.client.get(
            "/api/attendance/stats",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )

    @task(2)
    def list_students(self):
        self.client.get(
            "/api/students",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )

    @task(2)
    def list_schedules(self):
        self.client.get(
            "/api/schedules",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )

    @task(1)
    def get_today_attendance(self):
        self.client.get(
            "/api/attendance/today",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )

    @task(1)
    def export_csv(self):
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        self.client.get(
            f"/api/reports/export/csv?start={start}&end={end}",
            headers=self._headers(),
            cookies={"token": self.token} if self.token else None,
        )
