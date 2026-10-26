from locust import HttpUser, FastHttpUser, between


def read_product(user):
    with user.client.get(
        "/products/1",
        name="/products/{productId}",
        catch_response=True,
        timeout=10,
    ) as response:
        if response.status_code != 200:
            response.failure(f"Expected 200, got {response.status_code}; error={getattr(response, 'error', None)!r}")


def update_product(user):
    product = {
        "product_id": 1,
        "sku": "LAPTOP-001",
        "manufacturer": "Dell",
        "category_id": 10,
        "weight": 1500,
        "some_other_id": 100,
    }

    with user.client.post(
        "/products/1/details",
        json=product,
        name="/products/{productId}/details",
        catch_response=True,
        timeout=10,
    ) as response:
        if response.status_code != 204:
            response.failure(f"Expected 204, got {response.status_code}; error={getattr(response, 'error', None)!r}")


class ProductHttpUser(HttpUser):
    wait_time = between(0.1, 0.5)
    tasks = {read_product: 4, update_product: 1}


class ProductFastHttpUser(FastHttpUser):
    wait_time = between(0.1, 0.5)
    tasks = {read_product: 4, update_product: 1}
