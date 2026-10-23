# -*- coding: utf-8 -*-
"""
Kart okunmadiginda sunucudaki bekleme videosunu tam ekranda oynatir.
"""
from __future__ import annotations

import logging
import json
import os
import shlex
import shutil
import signal
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse, urlunparse

from config import BEKLEME_VIDEO_DONGU_SANIYE, BEKLEME_VIDEO_PATH
from config_store import oku_config

LOG = logging.getLogger(__name__)


def _video_kimlik_bilgisi() -> tuple[str, str]:
    kullanici = os.environ.get("TABBY_BEKLEME_VIDEO_KULLANICI")
    sifre = os.environ.get("TABBY_BEKLEME_VIDEO_SIFRE")
    if kullanici is not None:
        return (kullanici.strip(), "" if sifre is None else sifre)
    try:
        cfg = oku_config()
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    return (
        str(cfg.get("bekleme_video_kullanici", "")).strip(),
        str(cfg.get("bekleme_video_sifre", "")),
    )


def bekleme_video_url_uret(servis_url: str) -> str:
    parsed = urlparse(servis_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "10.85.100.8"
    path = BEKLEME_VIDEO_PATH
    if not path.startswith("/"):
        path = "/" + path
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = "[%s]" % host
    return urlunparse((scheme, "%s:3000" % netloc, path, "", "", ""))


def _url_log_maskele(url: str) -> str:
    parsed = urlparse(url)
    if "@" not in parsed.netloc:
        return url
    _, host = parsed.netloc.rsplit("@", 1)
    return urlunparse((parsed.scheme, "***:***@%s" % host, parsed.path, "", "", ""))


class _VideoProxy:
    def __init__(self) -> None:
        self._sunucu: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def durdur(self) -> None:
        sunucu = self._sunucu
        self._sunucu = None
        if sunucu is None:
            return
        try:
            sunucu.shutdown()
            sunucu.server_close()
        except Exception:
            pass

    def url_uret(self, video_url: str) -> str:
        kullanici, sifre = _video_kimlik_bilgisi()
        cerez = self._login_cerezi_al(video_url, kullanici, sifre) if kullanici else ""
        self.durdur()

        hedef = video_url
        hedef_parsed = urlparse(video_url)
        hedef_origin = urlunparse(
            (hedef_parsed.scheme, hedef_parsed.netloc, "", "", "", "")
        )
        ssl_context = ssl._create_unverified_context()

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path in ("", "/"):
                    self._html()
                else:
                    self._proxy()

            def do_HEAD(self) -> None:  # noqa: N802
                if self.path in ("", "/"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                else:
                    self._proxy(head_only=True)

            def _html(self) -> None:
                govde = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body { margin: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }
    video { width: 100vw; height: 100vh; object-fit: cover; background: #000; }
  </style>
</head>
<body>
  <video src="/video" autoplay loop playsinline></video>
  <script>
    const v = document.querySelector('video');
    function play() { v.play().catch(() => setTimeout(play, 1000)); }
    v.addEventListener('ended', play);
    v.addEventListener('error', () => setTimeout(() => { v.load(); play(); }, 3000));
    play();
  </script>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def _proxy(self, head_only: bool = False) -> None:
                try:
                    hedef_url = hedef if self.path.startswith("/video") else hedef_origin + self.path
                    req = urlrequest.Request(
                        hedef_url,
                        headers={
                            "Cookie": cerez,
                            "User-Agent": self.headers.get("User-Agent", "TabbyKiosk/1.0"),
                            "Accept": self.headers.get("Accept", "*/*"),
                        },
                        method="HEAD" if head_only else "GET",
                    )
                    range_header = self.headers.get("Range")
                    if range_header:
                        req.add_header("Range", range_header)
                    with urlrequest.urlopen(req, timeout=20, context=ssl_context) as resp:
                        self.send_response(resp.getcode())
                        for anahtar, deger in resp.headers.items():
                            if anahtar.lower() in (
                                "connection",
                                "transfer-encoding",
                                "content-security-policy",
                            ):
                                continue
                            self.send_header(anahtar, deger)
                        self.end_headers()
                        if not head_only:
                            shutil.copyfileobj(resp, self.wfile)
                except urlerror.HTTPError as e:
                    self.send_response(e.code)
                    self.end_headers()
                except Exception as e:
                    LOG.warning("Bekleme video proxy hatasi: %s", e)
                    self.send_response(502)
                    self.end_headers()

            def log_message(self, _fmt: str, *_args: object) -> None:
                return

        try:
            self._sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            port = int(self._sunucu.server_address[1])
            self._thread = threading.Thread(
                target=self._sunucu.serve_forever,
                name="bekleme-video-proxy",
                daemon=True,
            )
            self._thread.start()
            return "http://127.0.0.1:%s/" % port
        except Exception as e:
            LOG.warning("Bekleme video proxy baslatilamadi: %s", e)
            self.durdur()
            return video_url

    def _login_cerezi_al(self, video_url: str, kullanici: str, sifre: str) -> str:
        parsed = urlparse(video_url)
        host = parsed.hostname or "10.85.100.8"
        login_url = os.environ.get("TABBY_BEKLEME_VIDEO_LOGIN_URL", "").strip()
        if not login_url:
            try:
                cfg = oku_config()
            except Exception:
                cfg = {}
            if isinstance(cfg, dict):
                login_url = str(cfg.get("bekleme_video_login_url", "")).strip()
        if not login_url:
            login_url = "https://%s:8443/giris" % host
        body = json.dumps(
            {"personelRegNo": kullanici, "sifre": sifre},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urlrequest.Request(
            login_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            opener = urlrequest.build_opener(
                urlrequest.HTTPSHandler(context=ssl._create_unverified_context())
            )
            with opener.open(req, timeout=10) as resp:
                cerezler = resp.headers.get_all("Set-Cookie") or []
        except Exception as e:
            LOG.warning("Bekleme video login basarisiz: %s", e)
            return ""
        parcalar = []
        for cerez in cerezler:
            ilk = cerez.split(";", 1)[0].strip()
            if ilk:
                parcalar.append(ilk)
        if not parcalar:
            LOG.warning("Bekleme video login cerez dondurmedi.")
            return ""
        return "; ".join(parcalar)


class BeklemeVideoOynatici:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._acik = False
        self._proxy = _VideoProxy()
        self._chromium_profile_dir = os.path.join(
            tempfile.gettempdir(), "tabby-kiosk-chromium-video"
        )

    def calisiyor_mu(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def dustu_mu(self) -> bool:
        """Bayrak acik ama process olmus — beyaz ekran takilmasi."""
        return self._acik and not self.calisiyor_mu()

    def acik_mi(self) -> bool:
        """True yalnizca Chromium/process gercekten ayaktaysa."""
        if not self._acik:
            return False
        if self.calisiyor_mu():
            return True
        LOG.warning("Bekleme videosu process dustu; durum temizleniyor")
        self._process = None
        self._acik = False
        try:
            self._proxy.durdur()
        except Exception:
            pass
        self._chromium_kapat()
        return False

    def baslat(self, url: str) -> bool:
        if self.acik_mi():
            return True
        # Bayrak takili kalmissa once temizle
        if self._acik or self._process is not None:
            self.durdur()
        self._chromium_kapat()
        oynatma_url = self._proxy.url_uret(url)
        komut = self._komut_sec(oynatma_url)
        if not komut:
            LOG.warning("Bekleme videosu icin uygun oynatici/tarayici bulunamadi.")
            self._proxy.durdur()
            return False
        try:
            self._process = subprocess.Popen(
                komut,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=(sys.platform != "darwin"),
            )
        except Exception as e:
            LOG.warning("Bekleme videosu baslatilamadi: %s", e)
            self._process = None
            self._acik = False
            self._proxy.durdur()
            return False
        self._acik = True
        LOG.info(
            "Bekleme videosu acildi: %s (dongu %.1f sn)",
            _url_log_maskele(oynatma_url),
            BEKLEME_VIDEO_DONGU_SANIYE,
        )
        return True

    def _chromium_kapat(self) -> None:
        try:
            subprocess.run(
                ["pkill", "-f", self._chromium_profile_dir],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except Exception:
            pass
        try:
            shutil.rmtree(self._chromium_profile_dir, ignore_errors=True)
        except Exception:
            pass

    def durdur(self) -> None:
        self._acik = False
        p = self._process
        self._process = None
        self._proxy.durdur()
        if p is None or p.poll() is not None:
            self._chromium_kapat()
            return
        try:
            if sys.platform != "darwin":
                os.killpg(p.pid, signal.SIGTERM)
            else:
                p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                if sys.platform != "darwin":
                    os.killpg(p.pid, signal.SIGKILL)
                else:
                    p.kill()
            except Exception:
                pass
        self._chromium_kapat()

    def _komut_sec(self, url: str) -> list[str]:
        env_komut = os.environ.get("TABBY_BEKLEME_VIDEO_KOMUT", "").strip()
        if env_komut:
            parcalar = shlex.split(env_komut)
            if any("{url}" in p for p in parcalar):
                return [p.replace("{url}", url) for p in parcalar]
            return parcalar + [url]

        for ad in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
            exe = shutil.which(ad)
            if exe:
                return [
                    exe,
                    "--kiosk",
                    "--app=%s" % url,
                    "--user-data-dir=%s" % self._chromium_profile_dir,
                    "--no-first-run",
                    "--password-store=basic",
                    "--use-mock-keychain",
                    "--autoplay-policy=no-user-gesture-required",
                    "--noerrdialogs",
                    "--disable-infobars",
                    "--disable-restore-session-state",
                    "--check-for-update-interval=31536000",
                ]

        firefox = shutil.which("firefox")
        if firefox:
            return [firefox, "--kiosk", url]

        mpv = shutil.which("mpv")
        if mpv:
            return [mpv, "--fs", "--loop=inf", "--really-quiet", url]

        cvlc = shutil.which("cvlc")
        if cvlc:
            return [cvlc, "--fullscreen", "--loop", "--no-video-title-show", url]

        ffplay = shutil.which("ffplay")
        if ffplay:
            return [ffplay, "-fs", "-loop", "0", "-autoexit", "-loglevel", "quiet", url]

        if sys.platform == "darwin":
            return ["open", url]

        xdg_open = shutil.which("xdg-open")
        if xdg_open:
            return [xdg_open, url]

        return []
