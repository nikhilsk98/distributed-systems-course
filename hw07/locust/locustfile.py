"""Flash-sale load test. Select the endpoint with ORDER_ENDPOINT=sync|async."""
import os
import random

from locust import HttpUser, between, task

ENDPOINT = os.environ.get("ORDER_ENDPOINT", "async")
PRODUCTS = [f"prod-{i:03d}" for i in range(1, 51)]


def random_order():
    return {
        "customer_id": random.randint(1, 10000),
        "items": [
            {
                "product_id": random.choice(PRODUCTS),
                "quantity": random.randint(1, 3),
                "price": round(random.uniform(5, 200), 2),
            }
            for _ in range(random.randint(1, 3))
        ],
    }


class OrderUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def place_order(self):
        path = f"/orders/{ENDPOINT}"
        expected = 202 if ENDPOINT == "async" else 200
        with self.client.post(path, json=random_order(), name=path, catch_response=True) as r:
            if r.status_code != expected:
                r.failure(f"HTTP {r.status_code}")
