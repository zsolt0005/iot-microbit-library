"""HTTP client (http:// only) over the Wi-Fi module, using wifi.py."""
import wifi
from microbit import uart


def request(method, url, body="", timeout=10000, limit=512):
    """Send an HTTP request. Returns (status, body); status 0 means no response.

    Only http:// is supported. The response body is cut to limit bytes.
    """
    if not url.startswith("http://"):
        return 0, ""
    host, path = (url[7:].split("/", 1) + [""])[:2]
    port = "80"
    if ":" in host:
        host, port = host.split(":", 1)
    r = wifi.at('AT+CIPSTART="TCP","%s",%s' % (host, port), timeout)
    if b"CONNECT" not in r:
        return 0, ""
    head = "%s /%s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n" % (method, path, host)
    if body:
        head += "Content-Type: application/json\r\nContent-Length: %d\r\n" % len(body)
    data = (head + "\r\n" + body).encode()
    if b">" not in wifi.at("AT+CIPSEND=%d" % len(data), 2000, (b">", b"ERROR")):
        wifi.at("AT+CIPCLOSE")
        return 0, ""
    uart.write(data)
    r = wifi.wait((b"CLOSED",), timeout)
    # The answer arrives in blocks "+IPD,<length>:<data>"
    resp = b""
    i = r.find(b"+IPD,")
    while i >= 0:
        c = r.find(b":", i)
        n = int(r[i + 5:c])
        resp += r[c + 1:c + 1 + n]
        i = r.find(b"+IPD,", c + 1 + n)
    if not resp.startswith(b"HTTP/"):
        return 0, ""
    status = int(resp[9:12])
    b = resp.find(b"\r\n\r\n")
    return status, resp[b + 4:b + 4 + limit].decode() if b >= 0 else ""


def get(url, timeout=10000):
    """HTTP GET. Returns (status, body)."""
    return request("GET", url, "", timeout)


def post(url, body, timeout=10000):
    """HTTP POST with a JSON body (string). Returns (status, body)."""
    return request("POST", url, body, timeout)
