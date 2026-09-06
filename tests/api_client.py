"""Test browser that records the account returned by authentication responses."""

from fastapi.testclient import TestClient as BaseTestClient


class TestClient(BaseTestClient):
    __test__ = False

    def request(self, method, url, **kwargs):
        response = super().request(method, url, **kwargs)
        if method.upper() != "OPTIONS" and str(url).endswith(("/auth/sign_in", "/auth/sign_up", "/auth/session")) and response.is_success:
            session = response.json()
            if session.get("authenticated"):
                self.headers["X-Serenita-Account-ID"] = session["account_id"]
        return response
