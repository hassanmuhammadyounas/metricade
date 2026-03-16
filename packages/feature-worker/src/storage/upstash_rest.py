"""
Thin Upstash REST API client that mimics the redis-py interface for the commands we use.
Uses HTTPS (port 443) — works on networks that block port 6380.
"""
import httpx


class UpstashRestClient:
    def __init__(self, url: str, token: str):
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = httpx.Client(timeout=30.0)

    def _cmd(self, *args):
        resp = self._http.post(
            f"{self._url}/pipeline",
            headers=self._headers,
            json=[list(args)],
        )
        resp.raise_for_status()
        result = resp.json()
        if isinstance(result, list) and len(result) == 1:
            r = result[0]
            if isinstance(r, dict) and "error" in r:
                raise Exception(r["error"])
            return r.get("result") if isinstance(r, dict) else r
        return result

    # ── Key ops ───────────────────────────────────────────────────────────────

    def get(self, key: str):
        return self._cmd("GET", key)

    def setex(self, key: str, ttl: int, value):
        v = value.decode() if isinstance(value, bytes) else value
        return self._cmd("SETEX", key, ttl, v)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def scan(self, cursor, match: str = None, count: int = 100):
        args = ["SCAN", str(cursor)]
        if match:
            args += ["MATCH", match]
        args += ["COUNT", str(count)]
        result = self._cmd(*args)
        return int(result[0]), result[1]

    # ── Stream ops ────────────────────────────────────────────────────────────

    def xadd(self, stream: str, fields: dict, id: str = "*"):
        args = ["XADD", stream, id]
        for k, v in fields.items():
            args.append(k.decode() if isinstance(k, bytes) else k)
            v = v.decode() if isinstance(v, bytes) else v
            args.append(str(v))
        return self._cmd(*args)

    def xlen(self, stream: str) -> int:
        return int(self._cmd("XLEN", stream) or 0)

    def xread(self, streams: dict, count: int = None):
        """Poll streams from given IDs. streams = {stream_key: last_id}"""
        args = ["XREAD"]
        if count is not None:
            args += ["COUNT", str(count)]
        args.append("STREAMS")
        stream_keys = list(streams.keys())
        stream_ids = list(streams.values())
        args += stream_keys + stream_ids

        result = self._cmd(*args)
        if not result:
            return []
        # result: [[stream_name, [[entry_id, [f1, v1, ...]], ...]], ...]
        out = []
        for stream_data in result:
            stream_name = stream_data[0]
            entries = []
            for entry in stream_data[1]:
                entry_id = entry[0]
                flat = entry[1]
                fields = {}
                for i in range(0, len(flat), 2):
                    fields[flat[i]] = flat[i + 1]
                entries.append((entry_id, fields))
            out.append((stream_name, entries))
        return out
