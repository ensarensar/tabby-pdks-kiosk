# -*- coding: utf-8 -*-
"""SQLite yerel personel ve kart kuyrugu depolama."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

_DB_YOLU = os.environ.get("TABBY_OFFLINE_DB", "/var/lib/tabby-kiosk/tabby_offline.db")


@contextmanager
def _baglanti():
    dizin = os.path.dirname(_DB_YOLU)
    if dizin:
        os.makedirs(dizin, exist_ok=True)
    conn = sqlite3.connect(_DB_YOLU, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def veritabani_hazirla() -> None:
    with _baglanti() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS personel (
                personel_reg_no TEXT PRIMARY KEY,
                card_no TEXT,
                card_no2 TEXT,
                isim TEXT,
                soyisim TEXT,
                durum TEXT,
                rfid TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_personel_card_no ON personel(card_no);
            CREATE INDEX IF NOT EXISTS idx_personel_card_no2 ON personel(card_no2);
            CREATE TABLE IF NOT EXISTS kart_kuyrugu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kart_numarasi TEXT NOT NULL,
                okuyucu_adi TEXT,
                okuyucu_kisa TEXT,
                usb_port INTEGER,
                yon TEXT,
                zaman TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                gonderildi INTEGER NOT NULL DEFAULT 0,
                hata TEXT,
                olusturma TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kuyruk_bekleyen ON kart_kuyrugu(gonderildi, id);
            """
        )


def meta_oku(anahtar: str, varsayilan: str = "") -> str:
    veritabani_hazirla()
    with _baglanti() as conn:
        satir = conn.execute("SELECT value FROM meta WHERE key = ?", (anahtar,)).fetchone()
    if not satir:
        return varsayilan
    return str(satir["value"] or varsayilan)


def meta_yaz(anahtar: str, deger: str) -> None:
    veritabani_hazirla()
    with _baglanti() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (anahtar, deger),
        )


def personel_sayisi() -> int:
    veritabani_hazirla()
    with _baglanti() as conn:
        satir = conn.execute("SELECT COUNT(*) AS sayi FROM personel").fetchone()
    return int(satir["sayi"] if satir else 0)


def personel_temizle() -> int:
    veritabani_hazirla()
    with _baglanti() as conn:
        cur = conn.execute("DELETE FROM personel")
        return int(cur.rowcount or 0)


def personel_toplu_yaz(kayitlar: List[Dict[str, Any]]) -> int:
    if not kayitlar:
        return 0
    veritabani_hazirla()
    satirlar = []
    for ham in kayitlar:
        reg = str(ham.get("personelRegNo") or ham.get("personel_reg_no") or "").strip()
        if not reg:
            continue
        satirlar.append(
            (
                reg,
                str(ham.get("cardNo") or ham.get("card_no") or "").strip().upper(),
                str(ham.get("cardNo2") or ham.get("card_no2") or "").strip().upper(),
                str(ham.get("isim") or "").strip(),
                str(ham.get("soyisim") or "").strip(),
                str(ham.get("durum") or "").strip(),
                str(ham.get("rfid") or "").strip().upper(),
            )
        )
    if not satirlar:
        return 0
    with _baglanti() as conn:
        conn.executemany(
            """
            INSERT INTO personel(personel_reg_no, card_no, card_no2, isim, soyisim, durum, rfid)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(personel_reg_no) DO UPDATE SET
                card_no = excluded.card_no,
                card_no2 = excluded.card_no2,
                isim = excluded.isim,
                soyisim = excluded.soyisim,
                durum = excluded.durum,
                rfid = excluded.rfid
            """,
            satirlar,
        )
    return len(satirlar)


def personel_bul_kart(kart_numarasi: str) -> Optional[Dict[str, str]]:
    kart = str(kart_numarasi or "").strip().upper()
    if not kart:
        return None
    veritabani_hazirla()
    with _baglanti() as conn:
        satir = conn.execute(
            """
            SELECT personel_reg_no, card_no, card_no2, isim, soyisim, durum, rfid
            FROM personel
            WHERE UPPER(IFNULL(card_no, '')) = ?
               OR UPPER(IFNULL(card_no2, '')) = ?
            LIMIT 1
            """,
            (kart, kart),
        ).fetchone()
    if not satir:
        return None
    return {k: str(satir[k] or "") for k in satir.keys()}


def kuyruga_ekle(payload: Dict[str, Any]) -> int:
    veritabani_hazirla()
    simdi = datetime.now().isoformat(timespec="seconds")
    with _baglanti() as conn:
        cur = conn.execute(
            """
            INSERT INTO kart_kuyrugu(
                kart_numarasi, okuyucu_adi, okuyucu_kisa, usb_port, yon, zaman,
                payload_json, gonderildi, hata, olusturma
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, '', ?)
            """,
            (
                str(payload.get("kart_numarasi", "")).strip(),
                str(payload.get("okuyucu_adi", "")).strip(),
                str(payload.get("okuyucu_kisa", "")).strip(),
                payload.get("usb_port"),
                str(payload.get("yon", "")).strip(),
                str(payload.get("zaman", simdi)).strip() or simdi,
                json.dumps(payload, ensure_ascii=False),
                simdi,
            ),
        )
        return int(cur.lastrowid or 0)


def bekleyen_kuyruk(limit: int = 50) -> List[Dict[str, Any]]:
    veritabani_hazirla()
    with _baglanti() as conn:
        satirlar = conn.execute(
            """
            SELECT id, payload_json
            FROM kart_kuyrugu
            WHERE gonderildi = 0
            ORDER BY id ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    sonuc: List[Dict[str, Any]] = []
    for satir in satirlar:
        try:
            payload = json.loads(satir["payload_json"])
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            payload["_kuyruk_id"] = int(satir["id"])
            sonuc.append(payload)
    return sonuc


def kuyruk_isaretle_gonderildi(kuyruk_id: int) -> None:
    veritabani_hazirla()
    with _baglanti() as conn:
        conn.execute(
            "UPDATE kart_kuyrugu SET gonderildi = 1, hata = '' WHERE id = ?",
            (int(kuyruk_id),),
        )


def kuyruk_isaretle_hata(kuyruk_id: int, hata: str) -> None:
    veritabani_hazirla()
    with _baglanti() as conn:
        conn.execute(
            "UPDATE kart_kuyrugu SET hata = ? WHERE id = ?",
            (str(hata or "")[:500], int(kuyruk_id)),
        )


def kuyruk_temizle(gonderilmis: bool = True) -> int:
    veritabani_hazirla()
    with _baglanti() as conn:
        if gonderilmis:
            cur = conn.execute("DELETE FROM kart_kuyrugu WHERE gonderildi = 1")
        else:
            cur = conn.execute("DELETE FROM kart_kuyrugu")
        return int(cur.rowcount or 0)


def bekleyen_kuyruk_sayisi() -> int:
    veritabani_hazirla()
    with _baglanti() as conn:
        satir = conn.execute(
            "SELECT COUNT(*) AS sayi FROM kart_kuyrugu WHERE gonderildi = 0"
        ).fetchone()
    return int(satir["sayi"] if satir else 0)


def gonderilen_kuyruk_sayisi() -> int:
    veritabani_hazirla()
    with _baglanti() as conn:
        satir = conn.execute(
            "SELECT COUNT(*) AS sayi FROM kart_kuyrugu WHERE gonderildi = 1"
        ).fetchone()
    return int(satir["sayi"] if satir else 0)


def durum_ozeti() -> Dict[str, Any]:
    son_gonderilen = meta_oku("son_kuyruk_flush_gonderilen", "")
    son_kalan = meta_oku("son_kuyruk_flush_kalan", "")
    return {
        "personel_sayisi": personel_sayisi(),
        "bekleyen_kuyruk": bekleyen_kuyruk_sayisi(),
        "gonderilen_kuyruk": gonderilen_kuyruk_sayisi(),
        "son_sync": meta_oku("son_personel_sync", ""),
        "son_sync_metni": meta_oku("son_personel_sync_metni", ""),
        "son_flush": meta_oku("son_kuyruk_flush", ""),
        "son_flush_neden": meta_oku("son_kuyruk_flush_neden", ""),
        "son_flush_gonderilen": int(son_gonderilen) if str(son_gonderilen).isdigit() else 0,
        "son_flush_kalan": int(son_kalan) if str(son_kalan).isdigit() else 0,
    }
