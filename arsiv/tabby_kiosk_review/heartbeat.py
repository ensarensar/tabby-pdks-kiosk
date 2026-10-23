# -*- coding: utf-8 -*-
"""
Tabby cihaz heartbeat gonderimi.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from config_store import oku_config
from app_version import oku_uygulama_surumu

LOG = logging.getLogger(__name__)

_VARSAYILAN_INTERVAL_S = 30.0
_VARSAYILAN_TIMEOUT_S = 120.0
_PASIF_KONTROL_S = 5.0
_HTTP_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class HeartbeatAyari:
    aktif: bool
    url: str
    interval_s: float
    timeout_s: float
    ethernet_interface: str
    wifi_interface: str


def _metin(deger: Any, varsayilan: str = "") -> str:
    if deger is None:
        return varsayilan
    return str(deger).strip()


def _bool_deger(deger: Any, varsayilan: bool = False) -> bool:
    if isinstance(deger, bool):
        return deger
    if isinstance(deger, (int, float)):
        return deger != 0
    if isinstance(deger, str):
        v = deger.strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off", ""):
            return False
    return varsayilan


def _float_deger(deger: Any, varsayilan: float) -> float:
    if deger in (None, ""):
        return varsayilan
    try:
        sonuc = float(deger)
    except (TypeError, ValueError):
        return varsayilan
    if sonuc <= 0:
        return varsayilan
    return sonuc


def _ayar_oku() -> HeartbeatAyari:
    cfg = oku_config()
    if not isinstance(cfg, dict):
        cfg = {}
    return HeartbeatAyari(
        aktif=_bool_deger(cfg.get("heartbeat_aktif"), False),
        url=_metin(cfg.get("heartbeat_url")),
        interval_s=_float_deger(cfg.get("heartbeat_interval_s"), _VARSAYILAN_INTERVAL_S),
        timeout_s=_float_deger(cfg.get("heartbeat_timeout_s"), _VARSAYILAN_TIMEOUT_S),
        ethernet_interface=_metin(cfg.get("ethernet_interface"), "eth0") or "eth0",
        wifi_interface=_metin(cfg.get("wifi_interface"), "wlan0") or "wlan0",
    )


def _komut_cikti(komut: list[str], timeout_s: float = 2.0) -> str:
    try:
        p = subprocess.run(
            komut,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    return p.stdout or ""


def _sysfs_oku(arayuz: str, dosya: str) -> str:
    if not arayuz:
        return ""
    yol = "/sys/class/net/%s/%s" % (arayuz, dosya)
    if not os.path.isfile(yol):
        return ""
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _arayuz_ip(arayuz: str) -> str:
    if not arayuz:
        return ""
    cikti = _komut_cikti(["ip", "-4", "-o", "addr", "show", "dev", arayuz])
    for satir in cikti.splitlines():
        parcali = satir.split()
        if "inet" not in parcali:
            continue
        try:
            cidr = parcali[parcali.index("inet") + 1]
        except Exception:
            continue
        ip = cidr.split("/")[0].strip()
        if ip:
            return ip
    return ""


def _arayuz_mac(arayuz: str) -> str:
    mac = _sysfs_oku(arayuz, "address")
    return mac.upper() if mac else ""


def _arayuz_carrier_var_mi(arayuz: str) -> bool:
    return _sysfs_oku(arayuz, "carrier") == "1"


def _arayuz_aktif_mi(arayuz: str) -> bool:
    """Gerçekten bagli say: Ethernet icin kablo (carrier) + IP; WiFi icin IP veya baglantı."""
    if not arayuz:
        return False
    if not os.path.isdir("/sys/class/net/%s" % arayuz):
        return False
    ip = _arayuz_ip(arayuz)
    tip = _sysfs_oku(arayuz, "type").strip()
    # 1 = ethernet, wireless tiplerde carrier olmadan IP yeterli
    if tip == "1":
        return _arayuz_carrier_var_mi(arayuz) and bool(ip)
    if _arayuz_carrier_var_mi(arayuz) and ip:
        return True
    operstate = _sysfs_oku(arayuz, "operstate").lower()
    if operstate in ("up", "unknown") and ip:
        return True
    return False


def _varsayilan_route_arayuzu() -> str:
    cikti = _komut_cikti(["ip", "route", "show", "default"])
    for satir in cikti.splitlines():
        parcali = satir.split()
        if "dev" not in parcali:
            continue
        try:
            arayuz = parcali[parcali.index("dev") + 1].strip()
        except Exception:
            continue
        if arayuz:
            return arayuz
    return ""


def _arayuz_baglanti_adi(arayuz: str) -> str:
    if not arayuz:
        return ""
    cikti = _komut_cikti(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", arayuz])
    ad = cikti.strip()
    if not ad or ad == "--":
        return ""
    return ad


def _ipv4_method_dhcp_mi(method: str) -> Optional[bool]:
    yontem = method.strip().lower()
    if not yontem:
        return None
    if yontem in ("auto", "dhcp"):
        return True
    if yontem in ("manual", "shared", "link-local", "disabled"):
        return False
    return None


def _arayuz_dhcp_mi(arayuz: str) -> Optional[bool]:
    if not arayuz or not os.path.isdir("/sys/class/net/%s" % arayuz):
        return None

    method = _komut_cikti(["nmcli", "-g", "IP4.METHOD", "device", "show", arayuz])
    dhcp = _ipv4_method_dhcp_mi(method)
    if dhcp is not None:
        return dhcp

    baglanti = _arayuz_baglanti_adi(arayuz)
    if not baglanti:
        return None
    method = _komut_cikti(["nmcli", "-g", "ipv4.method", "connection", "show", baglanti])
    return _ipv4_method_dhcp_mi(method)


def _arayuz_ozeti(arayuz: str) -> Dict[str, Any]:
    if not arayuz or not os.path.isdir("/sys/class/net/%s" % arayuz):
        return {
            "interface": arayuz or "",
            "ip": "",
            "mac": "",
            "dhcp": None,
            "active": False,
        }
    ip = _arayuz_ip(arayuz)
    return {
        "interface": arayuz,
        "ip": ip,
        "mac": _arayuz_mac(arayuz),
        "dhcp": _arayuz_dhcp_mi(arayuz),
        "active": _arayuz_aktif_mi(arayuz) or bool(ip),
    }


def _wifi_bilgisi(arayuz: str) -> tuple[str, Optional[int]]:
    ssid = ""
    rssi: Optional[int] = None

    iw = _komut_cikti(["iw", "dev", arayuz, "link"])
    for satir in iw.splitlines():
        s = satir.strip()
        if s.startswith("SSID:"):
            ssid = s.split("SSID:", 1)[1].strip()
        elif s.startswith("signal:"):
            m = re.search(r"(-?\d+)", s)
            if m:
                try:
                    rssi = int(m.group(1))
                except ValueError:
                    rssi = None
    if ssid or rssi is not None:
        return (ssid, rssi)

    iwconfig = _komut_cikti(["iwconfig", arayuz])
    m_ssid = re.search(r'ESSID:"([^"]*)"', iwconfig)
    if m_ssid:
        ssid = m_ssid.group(1).strip()
    m_rssi = re.search(r"Signal level=(-?\d+)", iwconfig)
    if m_rssi:
        try:
            rssi = int(m_rssi.group(1))
        except ValueError:
            rssi = None
    return (ssid, rssi)


def heartbeat_payload_uret(ayar: Optional[HeartbeatAyari] = None) -> Dict[str, Any]:
    ayar = ayar or _ayar_oku()
    eth_if = ayar.ethernet_interface
    wifi_if = ayar.wifi_interface
    default_if = _varsayilan_route_arayuzu()
    eth_aktif = _arayuz_aktif_mi(eth_if)
    wifi_aktif = _arayuz_aktif_mi(wifi_if)

    baglanti_tipi = "unknown"
    arayuz = ""
    # Oncelik: gercekten aktif eth/wifi. Default route eth'e isaret etse bile
    # kablo yoksa ethernet sayma (stale IP/route tuzağı).
    if eth_aktif:
        baglanti_tipi = "ethernet"
        arayuz = eth_if
    elif wifi_aktif:
        baglanti_tipi = "wifi"
        arayuz = wifi_if
    elif default_if == wifi_if and _arayuz_ip(wifi_if):
        baglanti_tipi = "wifi"
        arayuz = wifi_if
    elif default_if == eth_if and eth_aktif:
        baglanti_tipi = "ethernet"
        arayuz = eth_if
    elif not eth_aktif and not wifi_aktif:
        baglanti_tipi = "none"
        arayuz = eth_if if os.path.isdir("/sys/class/net/%s" % eth_if) else wifi_if

    ssid = ""
    rssi: Optional[int] = None
    if baglanti_tipi == "wifi":
        arayuz = wifi_if
        ssid, rssi = _wifi_bilgisi(wifi_if)

    ip = _arayuz_ip(arayuz) if arayuz and baglanti_tipi not in ("none",) else ""
    if baglanti_tipi == "ethernet":
        ip = _arayuz_ip(eth_if)
    elif baglanti_tipi == "wifi":
        ip = _arayuz_ip(wifi_if)
    elif baglanti_tipi == "none":
        ip = ""

    mac = _arayuz_mac(arayuz) if arayuz else ""
    if not mac:
        mac = _arayuz_mac(eth_if) or _arayuz_mac(wifi_if)

    eth = _arayuz_ozeti(eth_if)
    wifi = _arayuz_ozeti(wifi_if)
    # active alanini da carrier+IP ile hizala
    eth["active"] = eth_aktif
    wifi["active"] = wifi_aktif

    payload = {
        "connection_type": baglanti_tipi,
        "ip": ip,
        "mac": mac,
        "ssid": ssid,
        "rssi": rssi,
        "ethernet_ip": eth["ip"],
        "ethernet_mac": eth["mac"],
        "ethernet_dhcp": eth["dhcp"],
        "ethernet_active": eth["active"],
        "wifi_ip": wifi["ip"],
        "wifi_mac": wifi["mac"],
        "wifi_dhcp": wifi["dhcp"],
        "wifi_active": wifi["active"],
        "app_version": oku_uygulama_surumu(),
    }
    try:
        import offline_db

        ozet = offline_db.durum_ozeti()
        payload["bekleyen_kuyruk"] = ozet["bekleyen_kuyruk"]
        payload["gonderilen_kuyruk_toplam"] = ozet["gonderilen_kuyruk"]
        payload["son_kuyruk_flush"] = ozet["son_flush"]
        payload["son_kuyruk_gonderilen"] = ozet["son_flush_gonderilen"]
        payload["son_kuyruk_kalan"] = ozet["son_flush_kalan"]
        payload["son_kuyruk_flush_neden"] = ozet["son_flush_neden"]
    except Exception:
        pass
    return payload


def _bekleyen_guncellemeyi_isle(yanit: Dict[str, Any]) -> None:
    pending = yanit.get("pending_update") or yanit.get("pendingUpdate")
    if not isinstance(pending, dict):
        return
    bundle_url = str(pending.get("bundle_url") or pending.get("bundleUrl") or "").strip()
    version = str(pending.get("version") or "").strip()
    sha256 = str(pending.get("sha256") or pending.get("checksum") or "").strip().lower()
    if not bundle_url or not version or not sha256:
        return
    if oku_uygulama_surumu() == version:
        return

    def _calistir() -> None:
        try:
            from config_agent import _update_now  # noqa: WPS433

            ok, detay = _update_now(bundle_url, version, sha256)
            if ok:
                LOG.info("Heartbeat guncellemesi tamamlandi: v%s", version)
            else:
                LOG.warning("Heartbeat guncellemesi basarisiz: %s", detay)
        except Exception as e:
            LOG.warning("Heartbeat guncellemesi tetiklenemedi: %s", e)

    threading.Thread(target=_calistir, name="tabby-heartbeat-update", daemon=True).start()


def _heartbeat_gonder(ayar: HeartbeatAyari) -> None:
    parsed = urlparse(ayar.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        LOG.warning("Heartbeat atlandi; heartbeat_url gecersiz: %s", ayar.url)
        return

    payload = heartbeat_payload_uret(ayar)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    eth_mac = str(payload.get("ethernet_mac") or payload.get("mac") or "").strip()
    headers = {"Content-Type": "application/json"}
    if eth_mac:
        headers["X-Tabby-Device-Mac"] = eth_mac
    req = urlrequest.Request(
        ayar.url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            ham = resp.read().decode("utf-8", errors="ignore").strip()
            LOG.info("Heartbeat basarili: http=%s body=%s", resp.getcode(), ham[:500])
            try:
                yanit = json.loads(ham or "{}")
                if isinstance(yanit, dict):
                    _bekleyen_guncellemeyi_isle(yanit)
            except ValueError:
                pass
    except urlerror.HTTPError as e:
        detay = e.read().decode("utf-8", errors="ignore").strip()
        LOG.warning("Heartbeat HTTP hatasi: %s %s", e.code, detay[:500])
    except Exception as e:
        LOG.warning("Heartbeat gonderilemedi: %s", e)


class HeartbeatServisi:
    def __init__(self) -> None:
        self._dur = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def baslat(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._dur.clear()
        self._thread = threading.Thread(
            target=self._dongu,
            name="tabby-heartbeat",
            daemon=True,
        )
        self._thread.start()
        LOG.info("Heartbeat servisi baslatildi.")

    def durdur(self) -> None:
        self._dur.set()

    def _dongu(self) -> None:
        while not self._dur.is_set():
            ayar = _ayar_oku()
            if not ayar.aktif:
                if self._dur.wait(_PASIF_KONTROL_S):
                    break
                continue
            if not ayar.url:
                LOG.warning("Heartbeat aktif ama heartbeat_url bos; gonderim atlandi.")
                if self._dur.wait(_PASIF_KONTROL_S):
                    break
                continue

            _heartbeat_gonder(ayar)
            if self._dur.wait(max(1.0, ayar.interval_s)):
                break
