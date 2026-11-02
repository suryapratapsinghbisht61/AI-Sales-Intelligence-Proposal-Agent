"""Fetch a prospect's own public website pages, politely: robots.txt honoured, same domain only, no private IPs."""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "SalesPilotResearchBot/0.1 (+https://salespilot.example/bot)"
PATHS = ["/", "/about", "/about-us", "/company", "/products", "/services", "/solutions", "/customers"]
MAX_PAGES = 5
MAX_BYTES = 2_000_000
MAX_TEXT = 20_000


class FetchError(Exception):
    pass


@dataclass
class Page:
    url: str
    title: str
    text: str


def normalize_domain(value: str) -> str:
    v = value.strip().lower()
    host = urlparse(v if "://" in v else "https://" + v).hostname or ""
    return host.removeprefix("www.")


# shortcut: DNS is checked before httpx resolves again (rebinding window); pin the resolved IP if exposed to hostile input at scale
def _assert_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError(f"Could not resolve {host}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError("Refusing to fetch a private or reserved address")


def _get(client: httpx.Client, url: str) -> httpx.Response | None:
    _assert_public(urlparse(url).hostname or "")
    # redirects are followed manually so every hop is re-checked against the SSRF guard and the domain
    for _ in range(4):
        r = client.get(url)
        if r.is_redirect:
            url = urljoin(url, r.headers["location"])
            _assert_public(urlparse(url).hostname or "")
            continue
        return r
    return None


def fetch_site(domain: str) -> list[Page]:
    domain = normalize_domain(domain)
    if not domain or "." not in domain:
        raise FetchError("A valid website domain is required for web research")
    base = f"https://{domain}"
    pages: list[Page] = []
    with httpx.Client(timeout=10, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
        robots = RobotFileParser()
        try:
            r = _get(client, base + "/robots.txt")
            robots.parse(r.text.splitlines() if r is not None and r.status_code == 200 else [])
        except httpx.HTTPError:
            robots.parse([])
        for path in PATHS:
            if len(pages) >= MAX_PAGES:
                break
            url = base + path
            if not robots.can_fetch(USER_AGENT, url):
                continue
            try:
                r = _get(client, url)
            except httpx.HTTPError:
                continue
            if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                continue
            if normalize_domain(str(r.url)) != domain or len(r.content) > MAX_BYTES:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ").split())[:MAX_TEXT]
            if len(text) > 200 and all(p.text != text for p in pages):
                pages.append(Page(url=str(r.url), title=(soup.title.string or "").strip()[:300] if soup.title else "", text=text))
    return pages
