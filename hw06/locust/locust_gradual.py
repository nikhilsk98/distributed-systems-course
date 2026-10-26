from locust import LoadTestShape
from locustfile import SearchUser  # noqa: F401


class GradualRamp(LoadTestShape):
    """Ramp linearly from 0 to 200 users over 6 minutes."""
    peak_users = 200
    duration = 360

    def tick(self):
        t = self.get_run_time()
        if t >= self.duration:
            return None
        return max(1, round(self.peak_users * t / self.duration)), 20
