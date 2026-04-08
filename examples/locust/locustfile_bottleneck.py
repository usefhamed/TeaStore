"""
Bottleneck-identification locustfile for TeaStore.

Differences from locustfile.py:
  * Each request is tagged with name="<SERVICE>:<action>" so that Locust's
    per-request stats can be grouped by the microservice the call exercises.
    Tags used: WEBUI, AUTH, PERSIST, IMAGE, RECOMMENDER, ORDER.
  * Ships with a StepLoadShape that ramps users 50 -> 1500 over ~12 minutes
    so you can watch for the load level at which throughput plateaus or
    p95 latency knees upward.

Run headless with CSV export:

  locust -f examples/locust/locustfile_bottleneck.py \
         --host http://localhost:8080/tools.descartes.teastore.webui \
         --headless --csv results/run1

Pair with the docker-stats logger (scripts/log_docker_stats.sh) so resource
metrics line up on the same timeline.
"""

import logging
from random import randint, choice

from locust import HttpUser, LoadTestShape, task

logging.getLogger().setLevel(logging.INFO)


class UserBehavior(HttpUser):

    @task
    def load(self) -> None:
        # NOTE: login/logout intentionally skipped for the bottleneck
        # experiment. BCrypt password hashing in the auth service dominates
        # the cold-start latency and prevents users from ever reaching the
        # browse/cart/profile paths. Skipping it isolates the *system*
        # bottleneck (persistence / image / recommender) instead of the
        # auth-on-cold-start one.
        self.visit_home()
        self.browse()
        if choice([True, False]):
            self.buy()
        self.visit_profile()

    # ---- WEBUI ---------------------------------------------------------
    def visit_home(self) -> None:
        self.client.get("/", name="WEBUI:home")

    # ---- AUTH ----------------------------------------------------------
    def login(self) -> None:
        self.client.get("/login", name="WEBUI:login_page")
        user = randint(1, 99)
        self.client.post(
            "/loginAction",
            params={"username": user, "password": "password"},
            name="AUTH:login",
        )

    def logout(self) -> None:
        self.client.post(
            "/loginAction",
            params={"logout": ""},
            name="AUTH:logout",
        )

    # ---- PERSIST + IMAGE + ORDER --------------------------------------
    def browse(self) -> None:
        for _ in range(randint(2, 5)):
            category_id = randint(2, 6)
            page = randint(1, 5)
            # category listing -> hits persistence (DB) heavily
            self.client.get(
                "/category",
                params={"page": page, "category": category_id},
                name="PERSIST:category",
            )
            product_id = randint(7, 506)
            # product detail page -> renders product image (image service)
            self.client.get(
                "/product",
                params={"id": product_id},
                name="IMAGE:product",
            )
            # add to cart -> exercises the ordering/cart path
            self.client.post(
                "/cartAction",
                params={"addToCart": "", "productid": product_id},
                name="ORDER:add_to_cart",
            )

    def buy(self) -> None:
        user_data = {
            "firstname": "User",
            "lastname": "User",
            "adress1": "Road",
            "adress2": "City",
            "cardtype": "volvo",
            "cardnumber": "314159265359",
            "expirydate": "12/2050",
            "confirm": "Confirm",
        }
        # checkout -> ordering service writes the order via persistence
        self.client.post(
            "/cartAction",
            params=user_data,
            name="ORDER:checkout",
        )

    # ---- RECOMMENDER ---------------------------------------------------
    def visit_profile(self) -> None:
        # profile page pulls personalized recommendations
        self.client.get("/profile", name="RECOMMENDER:profile")


class StepLoadShape(LoadTestShape):
    """
    Ramp the system until something gives.

      0-120s    : 50  users  (warmup, baseline)
      120-240s  : 150 users
      240-360s  : 300 users
      360-480s  : 600 users
      480-600s  : 1000 users
      600-720s  : 1500 users (expected saturation)
    """

    stages = [
        {"duration": 120, "users": 50, "spawn_rate": 10},
        {"duration": 240, "users": 150, "spawn_rate": 15},
        {"duration": 360, "users": 300, "spawn_rate": 20},
        {"duration": 480, "users": 600, "spawn_rate": 30},
        {"duration": 600, "users": 1000, "spawn_rate": 40},
        {"duration": 720, "users": 1500, "spawn_rate": 50},
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None
