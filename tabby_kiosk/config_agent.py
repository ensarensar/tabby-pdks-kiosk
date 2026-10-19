# -*- coding: utf-8 -*-
"""
Tabby network config agent.
Root olarak calisir, /tabby-config isteklerini alip network ayarlarini uygular.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from config_payload import kaydet_config_payload
from config_store import config_dosyasi, oku_config, yedek_config_dosyasi
from app_version import oku_uygulama_surumu
import personel_sync

LOG = logging.getLogger(__name__)

_CONFIG_DIR = os.environ.get("TABBY_CONFIG_DIR", "/home/tabby/.config/tabby-kiosk")
_CONFIG_FILE = config_dosyasi()
_YEDEK_CONFIG_FILE = yedek_config_dosyasi()
_APPLY_SCRIPT = os.environ.get(
    "TABBY_APPLY_SCRIPT", "/home/tabby/tabby_kiosk/scripts/apply_tabby_config.sh"
)
_UPDATE_SCRIPT = os.environ.get(
    "TABBY_UPDATE_SCRIPT", "/home/tabby/tabby_kiosk/scripts/apply_tabby_update.sh"
)
_INSTALL_DIR = os.environ.get("TABBY_INSTALL_DIR", "/home/tabby/tabby_kiosk")
_HOST = os.environ.get("TABBY_CONFIG_AGENT_HOST", "0.0.0.0").strip() or "0.0.0.0"
try:
    _PORT = int(os.environ.get("TABBY_CONFIG_AGENT_PORT", "8080"))
except ValueError:
    _PORT = 8080


def _apply_now() -> Tuple[bool, str]:
    if not os.path.isfile(_APPLY_SCRIPT):
        return (False, "apply script bulunamadi: %s" % _APPLY_SCRIPT)
    try:
        p = subprocess.run(
            ["/bin/bash", _APPLY_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as e:
        return (False, "apply exception: %s" % e)
    if p.returncode == 0:
        return (True, "")
    stderr = (p.stderr or "").strip().replace("\n", " | ")
    stdout = (p.stdout or "").strip().replace("\n", " | ")
    return (False, stderr or stdout or ("returncode=%s" % p.returncode))


def _restart_async() -> None:
    def _run() -> None:
        try:
            subprocess.run(["/usr/sbin/reboot"], check=False)
        except Exception:
            LOG.exception("reboot hatasi")

    threading.Thread(target=_run, name="config-agent-reboot", daemon=True).start()


def _token_dogrula(_j: Dict[str, Any], _headers: Any) -> Tuple[bool, str]:
    return (True, "")


_update_kilit = threading.Lock()
_update_hedef = ""


def _update_now(bundle_url: str, version: str, sha256: str) -> Tuple[bool, str]:
    script = _UPDATE_SCRIPT
    if not os.path.isfile(script):
        script = os.path.join(_INSTALL_DIR, "scripts", "apply_tabby_update.sh")
    if not os.path.isfile(script):
        return (False, "update script bulunamadi: %s" % _UPDATE_SCRIPT)
    try:
        p = subprocess.run(
            ["/bin/bash", script, bundle_url, version, sha256],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=900,
            check=False,
        )
    except Exception as e:
        return (False, "update exception: %s" % e)
    if p.returncode == 0:
        return (True, (p.stdout or "").strip())
    stderr = (p.stderr or "").strip().replace("\n", " | ")
    stdout = (p.stdout or "").strip().replace("\n", " | ")
    return (False, stderr or stdout or ("returncode=%s" % p.returncode))


def _update_async(bundle_url: str, version: str, sha256: str) -> bool:
    """True: baslatildi. False: ayni surum zaten calisiyor."""
    global _update_hedef
    with _update_kilit:
        if _update_hedef == version:
            return False
        _update_hedef = version

    def _run() -> None:
        global _update_hedef
        try:
            ok, detay = _update_now(bundle_url, version, sha256)
            if ok:
                LOG.info("Uygulama guncellemesi tamamlandi: v%s", version)
            else:
                LOG.error("Uygulama guncellemesi basarisiz: %s", detay)
        finally:
            with _update_kilit:
                if _update_hedef == version:
                    _update_hedef = ""

    threading.Thread(target=_run, name="config-agent-update", daemon=True).start()
    return True


def _config_oku_yanit() -> Dict[str, Any]:
    cfg = oku_config()
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "ok": True,
        "config_file": _CONFIG_FILE,
        "config_backup_file": _YEDEK_CONFIG_FILE,
        "config": cfg,
    }


class _Handler(BaseHTTPRequestHandler):
    def _json_oku(self) -> Dict[str, Any]:
        try:
            boyut = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            boyut = 0
        ham = self.rfile.read(max(0, boyut)).decode("utf-8", errors="ignore")
        try:
            j = json.loads(ham or "{}")
        except ValueError:
            return {}
        return j if isinstance(j, dict) else {}

    def _json_yanit(self, kod: int, veri: Dict[str, Any]) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(veri, ensure_ascii=False).encode("utf-8"))

    def _yol_temiz(self) -> str:
        return urlparse(self.path).path.rstrip("/") or "/"

    def do_GET(self) -> None:  # noqa: N802
        yol = self._yol_temiz()
        if yol == "/health":
            personel = personel_sync.personel_durum_yaniti()
            self._json_yanit(
                200,
                {
                    "ok": True,
                    "service": "tabby-config-agent",
                    "version": oku_uygulama_surumu(),
                    "config_file": _CONFIG_FILE,
                    "config_backup_file": _YEDEK_CONFIG_FILE,
                    "personel_sayisi": personel.get("personel_sayisi", 0),
                    "son_sync": personel.get("son_sync", ""),
                    "bekleyen_kuyruk": personel.get("bekleyen_kuyruk", 0),
                    "gonderilen_kuyruk": personel.get("gonderilen_kuyruk", 0),
                    "son_kuyruk_flush": personel.get("son_flush", ""),
                },
            )
            return
        if yol == "/personel-durum":
            self._json_yanit(200, personel_sync.personel_durum_yaniti())
            return
        if yol == "/tabby-config":
            self._json_yanit(200, _config_oku_yanit())
            return
        if yol == "/tabby-version":
            self._json_yanit(
                200,
                {
                    "ok": True,
                    "version": oku_uygulama_surumu(),
                    "install_dir": _INSTALL_DIR,
                },
            )
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        yol = self._yol_temiz()
        if yol == "/restart":
            j = self._json_oku()
            if str(j.get("message", "")).strip() != "tabby-restart":
                self._json_yanit(400, {"ok": False, "error": "gecersiz mesaj"})
                return
            self._json_yanit(200, {"ok": True, "message": "restart tetiklendi"})
            _restart_async()
            return
        if yol == "/tabby-update":
            self._update_handle()
            return
        if yol == "/personel-sync":
            j = self._json_oku()
            arka_plan = str(j.get("async", "true")).strip().lower() in ("1", "true", "yes", "on", "")
            tam_yenile = str(j.get("tam_yenile", "true")).strip().lower() not in ("0", "false", "no", "off")

            def _calistir() -> Dict[str, Any]:
                ok, hata, meta = personel_sync.personel_senkronize(tam_yenile=tam_yenile)
                if not ok:
                    return {"ok": False, "error": hata, **meta}
                return {"ok": True, "message": "personel sync tamamlandi", **meta}

            if arka_plan:
                def _thread() -> None:
                    sonuc = _calistir()
                    if sonuc.get("ok"):
                        LOG.info("Arka plan personel sync: %s kayit", sonuc.get("personel_sayisi"))
                    else:
                        LOG.warning("Arka plan personel sync basarisiz: %s", sonuc.get("error"))

                threading.Thread(target=_thread, name="personel-sync", daemon=True).start()
                self._json_yanit(202, {"ok": True, "message": "personel sync arka planda baslatildi"})
                return

            sonuc = _calistir()
            self._json_yanit(200 if sonuc.get("ok") else 500, sonuc)
            return
        if yol == "/personel-cache-temizle":
            j = self._json_oku()
            kuyruk = str(j.get("kart_kuyrugunu_temizle", "")).strip().lower() in ("1", "true", "yes", "on")
            self._json_yanit(200, personel_sync.cache_temizle(kart_kuyrugunu_temizle=kuyruk))
            return
        if yol == "/kuyruk-flush":
            j = self._json_oku()
            arka_plan = str(j.get("async", "false")).strip().lower() in ("1", "true", "yes", "on")

            def _calistir() -> Dict[str, Any]:
                import offline_db

                offline_db.meta_yaz("son_kuyruk_flush_neden", "uzaktan")
                ok, hata, meta = personel_sync.kuyruk_flush()
                if not ok:
                    return {"ok": False, "error": hata, **meta}
                return {"ok": True, "message": "kuyruk flush tamamlandi", **meta, **personel_sync.personel_durum_yaniti()}

            if arka_plan:
                def _thread() -> None:
                    sonuc = _calistir()
                    if sonuc.get("ok"):
                        LOG.info("Arka plan kuyruk flush: gonderilen=%s", sonuc.get("gonderilen"))
                    else:
                        LOG.warning("Arka plan kuyruk flush basarisiz: %s", sonuc.get("error"))

                threading.Thread(target=_thread, name="kuyruk-flush", daemon=True).start()
                self._json_yanit(202, {"ok": True, "message": "kuyruk flush arka planda baslatildi"})
                return

            sonuc = _calistir()
            self._json_yanit(200 if sonuc.get("ok") else 500, sonuc)
            return
        if yol != "/tabby-config":
            self.send_response(404)
            self.end_headers()
            return
        self._config_handle()

    def do_PUT(self) -> None:  # noqa: N802
        if self.path != "/tabby-config":
            self.send_response(404)
            self.end_headers()
            return
        self._config_handle()

    def _update_handle(self) -> None:
        j = self._json_oku()
        ok_token, hata_token = _token_dogrula(j, self.headers)
        if not ok_token:
            self._json_yanit(401, {"ok": False, "error": hata_token})
            return

        bundle_url = str(
            j.get("bundle_url") or j.get("bundleUrl") or j.get("paket_url") or ""
        ).strip()
        version = str(j.get("version") or j.get("surum") or "").strip()
        sha256 = str(j.get("sha256") or j.get("checksum") or "").strip().lower()
        async_mode = str(j.get("async", "1")).strip().lower() not in ("0", "false", "no")

        if not bundle_url or not version or not sha256:
            self._json_yanit(
                400,
                {"ok": False, "error": "bundle_url, version ve sha256 zorunludur."},
            )
            return
        parsed = urlparse(bundle_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._json_yanit(400, {"ok": False, "error": "bundle_url gecersiz"})
            return

        mevcut = oku_uygulama_surumu()
        if mevcut == version and not str(j.get("force", "")).strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            self._json_yanit(
                200,
                {
                    "ok": True,
                    "message": "Surum zaten guncel",
                    "version": mevcut,
                },
            )
            return

        if async_mode:
            basladi = _update_async(bundle_url, version, sha256)
            self._json_yanit(
                202,
                {
                    "ok": True,
                    "message": (
                        "Guncelleme arka planda baslatildi"
                        if basladi
                        else "Guncelleme zaten calisiyor"
                    ),
                    "version": version,
                    "current_version": mevcut,
                    "busy": not basladi,
                },
            )
            return

        ok, detay = _update_now(bundle_url, version, sha256)
        if not ok:
            self._json_yanit(500, {"ok": False, "error": "Guncelleme basarisiz", "detail": detay})
            return
        self._json_yanit(
            200,
            {
                "ok": True,
                "message": "Guncelleme tamamlandi",
                "version": version,
                "detail": detay,
            },
        )

    def _config_handle(self) -> None:
        j = self._json_oku()
        ok, hata, meta = kaydet_config_payload(j)
        if not ok:
            self._json_yanit(
                400,
                {"ok": False, "error": hata, **meta},
            )
            return
        ok, hata = _apply_now()
        if not ok:
            self._json_yanit(
                500,
                {
                    "ok": False,
                    "error": "config kaydedildi ama apply basarisiz",
                    "detail": hata,
                    "config_file": _CONFIG_FILE,
                    "config_backup_file": _YEDEK_CONFIG_FILE,
                    **meta,
                },
            )
            return
        self._json_yanit(
            200,
            {
                "ok": True,
                "message": "config kaydedildi ve uygulandi",
                "config_file": _CONFIG_FILE,
                "config_backup_file": _YEDEK_CONFIG_FILE,
                **meta,
            },
        )

    def log_message(self, _fmt: str, *_args: object) -> None:
        return


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(_YEDEK_CONFIG_FILE), exist_ok=True)
    sunucu = ThreadingHTTPServer((_HOST, _PORT), _Handler)
    LOG.info("Tabby config agent aktif: http://%s:%s", _HOST, _PORT)
    sunucu.serve_forever()


if __name__ == "__main__":
    main()
