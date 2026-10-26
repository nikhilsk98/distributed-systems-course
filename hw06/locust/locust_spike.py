from locust import LoadTestShape
from locustfile import SearchUser  # noqa: F401


class Spike(LoadTestShape):
    """20 users for 2 min, spike to 200 for 3 min, back to 20 for 2 min."""
    stages = [(120, 20), (300, 200), (420, 20)]

    def tick(self):
        t = self.get_run_time()
        for end, users in self.stages:
            if t < end:
                return users, 100
        return None
