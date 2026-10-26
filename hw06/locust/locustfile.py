import random
from locust import FastHttpUser, task, constant

TERMS = ["electro", "books", "home", "alpha", "omega", "garden", "toys", "product"]

class SearchUser(FastHttpUser):
    wait_time = constant(0)

    @task
    def search(self):
        self.client.get(f"/products/search?q={random.choice(TERMS)}", name="/products/search")