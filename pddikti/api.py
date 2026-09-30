"""HTTP transport and the composed PDDIKTI queries."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ORIGIN = "https://pddikti.kemdiktisaintek.go.id"
DEFAULT_BASE_URL = f"{ORIGIN}/api"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# The API answers 403 to anything that does not look like the site's own XHR. A browser
# user agent plus Origin is what gets 200. No key, no captcha, no session: the SPA sends
# an X-Recaptcha-Token that was absent from a successful real-browser search, so bot
# detection is the whole gate. Verified 2026-09-30 that user agent alone gets 403 and
# origin alone gets 403.
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Origin": ORIGIN,
    "Referer": f"{ORIGIN}/",
    "Accept": "application/json, text/plain, */*",
}

RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 3


class PddiktiError(Exception):
    """Anything the user needs to read, already phrased as a sentence."""


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return fallback


class Client:
    def __init__(self, base_url: str | None = None, timeout: float | None = None,
                 delay: float = 0.0) -> None:
        self.base_url = (base_url or os.environ.get("PDDIKTI_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else _env_float("PDDIKTI_TIMEOUT", 30.0)
        self.delay = delay
        self._opener = urllib.request.build_opener()

    def _url(self, path: str) -> str:
        # Some paths in the bundle are written without the leading slash.
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None) -> object:
        url = self._url(path)
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
        return self._send(urllib.request.Request(url, headers=HEADERS))

    def post(self, path: str, body: dict) -> object:
        request = urllib.request.Request(
            self._url(path), data=json.dumps(body).encode(), headers=HEADERS, method="POST"
        )
        return self._send(request)

    def get_bytes(self, path: str) -> bytes:
        return self._send(urllib.request.Request(self._url(path), headers=HEADERS), raw=True)

    def _send(self, request: urllib.request.Request, raw: bool = False) -> object:
        if self.delay:
            time.sleep(self.delay)
        last = ""
        for attempt in range(ATTEMPTS):
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                return body if raw else self._decode(body)
            except urllib.error.HTTPError as exc:
                detail = self._message(exc.read())
                if exc.code in RETRY_STATUS and attempt + 1 < ATTEMPTS:
                    time.sleep(2 ** attempt)
                    last = f"HTTP {exc.code}{detail}"
                    continue
                if exc.code == 403:
                    raise PddiktiError(
                        "the server answered 403, which means it rejected the request as a bot. "
                        "PDDIKTI filters non-browser clients, so the access gate may have changed."
                    ) from None
                raise PddiktiError(f"HTTP {exc.code}{detail}") from None
            except urllib.error.URLError as exc:
                if attempt + 1 < ATTEMPTS:
                    time.sleep(2 ** attempt)
                    continue
                raise PddiktiError(f"cannot reach {self.base_url}: {exc.reason}") from None
        raise PddiktiError(last or "request failed")

    def _decode(self, body: bytes) -> object:
        try:
            payload = json.loads(body)
        except ValueError:
            raise PddiktiError("the server answered with something that is not JSON") from None
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise PddiktiError(payload.get("message") or "the server reported an error")
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    @staticmethod
    def _message(body: bytes) -> str:
        try:
            payload = json.loads(body)
        except ValueError:
            return ""
        if isinstance(payload, dict) and payload.get("message"):
            return f": {payload['message']}"
        return ""

    def run_all(self, jobs: int, work, items) -> list:
        """Map over items, keeping the input order, never raising for one bad item."""
        if jobs <= 1 or len(items) <= 1:
            return [_capture(work, item) for item in items]
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            return list(pool.map(lambda item: _capture(work, item), items))


def _capture(work, item):
    try:
        return ("ok", work(item))
    except PddiktiError as exc:
        return ("error", str(exc))


def search(client: Client, kind: str, term: str) -> list:
    """The four search endpoints return up to 100 hits, with no pagination."""
    term = urllib.parse.quote(term, safe="")
    hits = client.get(f"/pencarian/{kind}/{term}") or []
    return hits if isinstance(hits, list) else []


def search_all(client: Client, term: str) -> dict:
    term = urllib.parse.quote(term, safe="")
    return client.get(f"/pencarian/enc/all/{term}") or {}


def pt_filter(client: Client, nama: str = "", limit: int = 15, page: int = 1,
              provinsi: str = "", akreditasi: str = "", jenis: str = "") -> dict:
    """Faceted university search. The only search endpoint that paginates for real."""
    result = client.get("/v2/pt/search/filter", {
        "limit": limit, "page": page, "nama": nama, "provinsi": provinsi,
        "akreditasi": akreditasi, "jenis": jenis,
    }) or {}
    if not result.get("data"):
        result["data"] = []
    return result


def pt_detail(client: Client, id_sp: str) -> dict:
    return client.get(f"/pt/detail/{id_sp}") or {}


def pt_counts(client: Client, id_sp: str) -> dict:
    counts = {}
    for key, path in (("mahasiswa", "jumlah-mahasiswa"), ("dosen", "jumlah-dosen"),
                      ("prodi", "jumlah-prodi")):
        data = client.get(f"/pt/{path}/{id_sp}")
        counts[key] = (data or {}).get(f"jumlah_{key}") if key != "prodi" else (data or {}).get("jumlah_prodi")
    return counts


def pt_stats(client: Client, id_sp: str) -> dict:
    """Everything the university page shows, in one call round."""
    stats = {"detail": pt_detail(client, id_sp)}
    stats["counts"] = pt_counts(client, id_sp)
    for key, path in (("rasio", "rasio"), ("graduation_rate", "graduation-rate"),
                      ("cost_range", "cost-range"), ("waktu_studi", "waktu-studi"),
                      ("name_histories", "name-histories"), ("kelulusan", "mahasiswa")):
        try:
            stats[key] = client.get(f"/pt/{path}/{id_sp}")
        except PddiktiError:
            stats[key] = None
    return stats


def pt_prodi(client: Client, id_sp: str, semester: str) -> list:
    data = client.get(f"/pt/prodi/{id_sp}/{semester}")
    return data if isinstance(data, list) else []


def prodi_detail(client: Client, id_sms: str) -> dict:
    detail = client.get(f"/prodi/detail/{id_sms}") or {}
    for key, path in (("desc", "desc"), ("cost_range", "cost-range"),
                      ("num_students_lecturers", "num-students-lecturers"),
                      ("name_histories", "name-histories"),
                      ("rasio", "rasio-dosen-mahasiswa")):
        try:
            detail[key] = client.get(f"/prodi/{path}/{id_sms}")
        except PddiktiError:
            detail[key] = None
    return detail


def prodi_dosen(client: Client, id_sms: str, semester: str) -> list:
    """Homebase lecturers. The server takes the program id in the body, not the path."""
    data = client.post(f"dosen/homebase?semester={semester}", {"id": id_sms})
    return data if isinstance(data, list) else []


def mhs_detail(client: Client, student_id: str) -> dict:
    return client.get(f"/detail/mhs/{student_id}") or {}


def dosen_detail(client: Client, dosen_id: str) -> dict:
    detail = client.get(f"/dosen/profile/{dosen_id}") or {}
    for key, path in (("study_history", "study-history"),
                      ("teaching_history", "teaching-history"),
                      ("penelitian", "portofolio/penelitian"),
                      ("pengabdian", "portofolio/pengabdian"),
                      ("karya", "portofolio/karya"),
                      ("paten", "portofolio/paten")):
        try:
            detail[key] = client.get(f"/dosen/{path}/{dosen_id}")
        except PddiktiError:
            detail[key] = None
    return detail


def beranda(client: Client, limit: int = 100) -> dict:
    return client.get("/beranda", {"content_limit": limit}) or {}


def pt_locations(client: Client) -> list:
    data = client.get("/pt/locations")
    return data if isinstance(data, list) else []
