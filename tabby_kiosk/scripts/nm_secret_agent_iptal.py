#!/usr/bin/env python3
"""
NetworkManager secret agent — GUI sifre/baglanti penceresi yerine
istekleri sessizce iptal eder (kiosk). Internet gerekmez.
"""
from __future__ import annotations

import logging
import os
import sys

LOG = logging.getLogger("tabby-nm-secret")

AGENT_IFACE = "org.freedesktop.NetworkManager.SecretAgent"
AGENT_PATH = "/org/freedesktop/NetworkManager/SecretAgent"
NM_AGENT_MANAGER = "org.freedesktop.NetworkManager"
NM_AGENT_MANAGER_PATH = "/org/freedesktop/NetworkManager/AgentManager"
NM_AGENT_MANAGER_IFACE = "org.freedesktop.NetworkManager.AgentManager"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[nm-secret] %(message)s",
        stream=sys.stderr,
    )
    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
    except Exception as exc:
        LOG.error("dbus/gi yok, secret agent baslatilamadi: %s", exc)
        return 1

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    class CancelSecretAgent(dbus.service.Object):
        def __init__(self) -> None:
            super().__init__(bus, AGENT_PATH)

        # NM SecretAgent.GetSecrets:
        #   IN  a{sa{sv}} connection, o path, s setting, as hints, u flags
        #   OUT a{sa{sv}} secrets
        @dbus.service.method(
            AGENT_IFACE,
            in_signature="a{sa{sv}}osasu",
            out_signature="a{sa{sv}}",
        )
        def GetSecrets(self, connection, connection_path, setting_name, hints, flags):
            id_ = ""
            try:
                id_ = str(connection.get("connection", {}).get("id", ""))
            except Exception:
                pass
            LOG.info(
                "GetSecrets iptal: setting=%s id=%s flags=%s",
                setting_name,
                id_,
                flags,
            )
            raise dbus.exceptions.DBusException(
                "org.freedesktop.NetworkManager.SecretAgent.UserCanceled",
                "Tabby kiosk: secret dialog engellendi",
            )

        @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
        def CancelGetSecrets(self, connection_path, setting_name):
            return

        @dbus.service.method(AGENT_IFACE, in_signature="a{sa{sv}}o", out_signature="")
        def SaveSecrets(self, connection, connection_path):
            return

        @dbus.service.method(AGENT_IFACE, in_signature="a{sa{sv}}o", out_signature="")
        def DeleteSecrets(self, connection, connection_path):
            return

    agent = CancelSecretAgent()
    mgr = bus.get_object(NM_AGENT_MANAGER, NM_AGENT_MANAGER_PATH)
    iface = dbus.Interface(mgr, NM_AGENT_MANAGER_IFACE)
    try:
        iface.RegisterWithCapabilities("tabby-kiosk", dbus.UInt32(0))
    except Exception:
        iface.Register("tabby-kiosk")
    LOG.info("secret agent kayitli (GUI popup iptal)")

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            iface.Unregister("tabby-kiosk")
        except Exception:
            pass
        del agent
    return 0


if __name__ == "__main__":
    os.environ.setdefault("G_MESSAGES_DEBUG", "")
    raise SystemExit(main())
