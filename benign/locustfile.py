"""
Normal web traffic for the testbed: fast, complete HTTP requests.
Run with:  locust -f locustfile.py --headless -u 60 -r 10 -H http://victim:80 -t 3m
Locust is also the tool we use to measure legitimate-user success rate and
p95 latency *during* an attack, which is the key availability metric.
"""
from locust import HttpUser, task, between


class NormalUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(5)
    def home(self):
        self.client.get("/")

    @task(1)
    def status(self):
        self.client.get("/server-status?auto", name="/server-status")
