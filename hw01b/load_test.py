
import requests
import time
import matplotlib.pyplot as plt
import numpy as np

# Your AWS Go-Gin server
EC2_URL = "http://18.205.161.235:8080/albums"

# Run the test for 60 seconds
DURATION = 300

response_times = []
request_times = []
failed_requests = 0

start_time = time.time()
end_time = start_time + DURATION

print("Starting AWS load test for 60 seconds...")

# Continuously send requests to AWS
while time.time() < end_time:
    try:
        request_start = time.time()

        response = requests.get(EC2_URL, timeout=5)

        request_end = time.time()

        # Calculate response time in milliseconds
        response_time = (request_end - request_start) * 1000

        if response.status_code == 200:
            response_times.append(response_time)
            request_times.append(request_end - start_time)
        else:
            failed_requests += 1

    except requests.exceptions.RequestException:
        failed_requests += 1


# Display performance statistics
print("\n----- PERFORMANCE RESULTS -----")

print(f"Total requests: {len(response_times) + failed_requests}")
print(f"Successful requests: {len(response_times)}")
print(f"Failed requests: {failed_requests}")

if response_times:

    print(f"Average response time: {np.mean(response_times):.2f} ms")
    print(f"Median response time: {np.median(response_times):.2f} ms")
    print(f"95th percentile: {np.percentile(response_times, 95):.2f} ms")
    print(f"99th percentile: {np.percentile(response_times, 99):.2f} ms")
    print(f"Maximum response time: {max(response_times):.2f} ms")

    # Graph 1: Histogram
    plt.figure(figsize=(10, 5))
    plt.hist(response_times, bins=50)
    plt.xlabel("Response Time (ms)")
    plt.ylabel("Number of Requests")
    plt.title("Distribution of AWS Response Times")

    plt.savefig("histogram.png")
    plt.show()

    # Graph 2: Scatter plot
    plt.figure(figsize=(10, 5))
    plt.scatter(request_times, response_times, s=10)
    plt.xlabel("Time Since Test Started (seconds)")
    plt.ylabel("Response Time (ms)")
    plt.title("AWS Response Times Over Time")

    plt.savefig("scatter_plot.png")
    plt.show()

else:
    print("No successful requests recorded.")
