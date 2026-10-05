from locust import FastHttpUser, task, between


class AlbumUser(FastHttpUser):

    wait_time = between(1, 2)

    @task(3)
    def get_albums(self):
        self.client.get("/albums")

    @task(1)
    def post_album(self):
        self.client.post(
            "/albums",
            json={
                "id": "99",
                "title": "Locust Test Album",
                "artist": "Locust",
                "price": 25.99
            }
        )