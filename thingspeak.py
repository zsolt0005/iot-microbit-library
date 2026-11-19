"""ThingSpeak cloud platform (https://thingspeak.com) over HTTP, using http.py."""
import http


def send(api_key, *values):
    """Write up to 8 values to fields 1-8 of a channel.

    Returns the new entry number, or 0 if the update was rejected (the free licence
    accepts one update per 15 s) or there was no response.
    """
    url = "http://api.thingspeak.com/update?api_key=" + api_key
    for i, v in enumerate(values[:8]):
        url += "&field%d=%s" % (i + 1, v)
    status, body = http.get(url)
    return int(body) if status == 200 and body.strip().isdigit() else 0
