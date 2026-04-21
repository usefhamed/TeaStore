import csv
import io
import logging
from datetime import datetime
from random import randint, choice

from locust import HttpUser, LoadTestShape, between, events, task

# logging
logging.getLogger().setLevel(logging.INFO)

# Track the last time each endpoint / failure was seen
_endpoint_ts = {}
_failure_ts = {}


@events.request.add_listener
def on_request(request_type, name, exception, **kwargs):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _endpoint_ts[f"{request_type},{name}"] = ts
    if exception:
        _failure_ts[f"{request_type},{name},{exception}"] = ts


@events.init.add_listener
def on_init(environment, **kwargs):
    if environment.web_ui:
        @environment.web_ui.app.after_request
        def add_timestamp(response):
            if "text/csv" not in response.content_type:
                return response

            data = response.get_data(as_text=True)
            reader = csv.reader(io.StringIO(data))
            buf = io.StringIO()
            writer = csv.writer(buf)
            content_disp = response.headers.get("Content-Disposition", "")
            is_failures = "failures" in content_disp.lower()

            for i, row in enumerate(reader):
                if i == 0:
                    writer.writerow(["Timestamp"] + row)
                    continue

                ts = ""
                if is_failures and len(row) >= 3:
                    ts = _failure_ts.get(f"{row[0]},{row[1]},{row[2]}", "")
                if not ts and len(row) >= 2 and row[1] != "Aggregated":
                    ts = _endpoint_ts.get(f"{row[0]},{row[1]}", "")
                if not ts and _endpoint_ts:
                    ts = max(_endpoint_ts.values())
                if not ts:
                    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                writer.writerow([ts] + row)

            response.set_data(buf.getvalue())
            return response


class UserBehavior(HttpUser):
    # TODO: PUT THE IP ADDRESS IN THE URL BELOW
    host = "http://{IP ADDRESS GOES HERE}:8080/tools.descartes.teastore.webui"
    # Real users pause between actions. Without this, each "user" is an
    # infinite request loop and 50 users saturates webui far past what
    # 50 humans would. Tune to taste — smaller range = more aggressive load.
    wait_time = between(1, 3)

    @task
    def load(self) -> None:
        """
        Simulates user behaviour.
        :return: None
        """
        logging.info("Starting user.")
        self.visit_home()
        self.login()
        self.browse()
        # 50/50 chance to buy
        choice_buy = choice([True, False])
        if choice_buy:
            self.buy()
        self.visit_profile()
        self.logout()
        logging.info("Completed user.")

    def visit_home(self) -> None:
        """
        Visits the landing page.
        :return: None
        """
        res = self.client.get("/")
        if res.ok:
            logging.info("Loaded landing page.")
        else:
            logging.error(f"Could not load landing page: {res.status_code}")

    def login(self) -> None:
        """
        User login w1ith random userid between 1 and 99.
        :return: None
        """
        res = self.client.get("/login")
        if res.ok:
            logging.info("Loaded login page.")
        else:
            logging.error(f"Could not load login page: {res.status_code}")

        user = randint(1, 99)
        login_request = self.client.post(
            "/loginAction",
            params={"username": f"user{user}", "password": "password"},
        )
        if login_request.ok:
            logging.info(f"Login with username: user{user}")
        else:
            logging.error(
                f"Could not login with username: user{user} - status: {login_request.status_code}"
            )

    def browse(self) -> None:
        """
        Simulates random browsing behaviour.
        :return: None
        """
        for _ in range(randint(2, 5)):
            category_id = randint(2, 6)
            page = randint(1, 5)
            category_request = self.client.get(
                "/category",
                params={"page": page, "category": category_id},
            )

            if category_request.ok:
                logging.info(f"Visited category {category_id} on page {page}")

                product_id = randint(7, 506)
                product_request = self.client.get("/product", params={"id": product_id})

                if product_request.ok:
                    logging.info(f"Visited product with id {product_id}.")
                    cart_request = self.client.post(
                        "/cartAction",
                        params={"addToCart": "", "productid": product_id},
                    )
                    if cart_request.ok:
                        logging.info(f"Added product {product_id} to cart.")
                    else:
                        logging.error(
                            f"Could not put product {product_id} in cart - status {cart_request.status_code}"
                        )
                else:
                    logging.error(
                        f"Could not visit product {product_id} - status {product_request.status_code}"
                    )
            else:
                logging.error(
                    f"Could not visit category {category_id} on page {page} - status {category_request.status_code}"
                )

    def buy(self) -> None:
        """
        Simulates buying products in the cart with sample user data.
        :return: None
        """
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
        buy_request = self.client.post("/cartAction", params=user_data)
        if buy_request.ok:
            logging.info("Bought products.")
        else:
            logging.error("Could not buy products.")

    def visit_profile(self) -> None:
        """
        Visits user profile.
        :return: None
        """
        profile_request = self.client.get("/profile")
        if profile_request.ok:
            logging.info("Visited profile page.")
        else:
            logging.error("Could not visit profile page.")

    def logout(self) -> None:
        """
        User logout.
        :return: None
        """
        logout_request = self.client.post("/loginAction", params={"logout": ""})
        if logout_request.ok:
            logging.info("Successful logout.")
        else:
            logging.error(f"Could not log out - status: {logout_request.status_code}")


class StepLoadShape(LoadTestShape):
    """
    Step through these target user counts:

    0s-60s    -> 50 users
    60s-120s  -> 100 users
    120s-180s -> 500 users
    180s-240s -> 1000 users

    Return None after the last stage to stop the test.
    """

    stages = [
        {"duration": 60, "users": 50, "spawn_rate": 10},
        {"duration": 120, "users": 100, "spawn_rate": 10},
        {"duration": 180, "users": 500, "spawn_rate": 20},
        {"duration": 240, "users": 1000, "spawn_rate": 50},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])

        return None
