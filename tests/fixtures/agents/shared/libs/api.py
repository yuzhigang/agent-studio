import json
import urllib.error
import urllib.request

from src.runtime.lib.decorator import lib_function


class ApiClient:
    def __init__(self):
        self.base_url = "https://api.example.com"
        self.timeout = 30

    @lib_function(name="echo", namespace="shared", readonly=True)
    def echo(self, args: dict) -> dict:
        return {"message": args.get("message", "")}

    def _http_request(self, method: str, args: dict) -> dict:
        url = args.get("url", "")
        headers = args.get("headers", {})
        body = args.get("body")
        params = args.get("params", {})

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        data = None
        if body is not None:
            if isinstance(body, dict):
                data = json.dumps(body).encode("utf-8")
                headers = {**headers, "Content-Type": "application/json"}
            else:
                data = str(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method)
        for key, value in headers.items():
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                try:
                    resp_data = json.loads(resp_body)
                except json.JSONDecodeError:
                    resp_data = {"raw": resp_body}
                return {
                    "method": method,
                    "url": url,
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "data": resp_data,
                }
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body}
            return {
                "method": method,
                "url": url,
                "status": e.code,
                "headers": dict(e.headers),
                "data": data,
                "error": e.reason,
            }
        except urllib.error.URLError as e:
            return {
                "method": method,
                "url": url,
                "status": None,
                "error": str(e.reason),
            }
        except Exception as e:
            return {
                "method": method,
                "url": url,
                "status": None,
                "error": str(e),
            }

    @lib_function(name="httpGet", namespace="shared", readonly=True)
    def http_get(self, args: dict) -> dict:
        return self._http_request("GET", args)
