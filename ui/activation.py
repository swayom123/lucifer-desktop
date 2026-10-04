"""Bring the existing desktop window forward when its launcher is clicked again."""

import getpass
import hashlib
import os
from pathlib import Path

from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_name(data_dir: Path) -> str:
    identity = f"{os.getuid() if hasattr(os, 'getuid') else getpass.getuser()}:{data_dir}"
    return "lucifer-" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def show_existing(name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name)
    connected = socket.waitForConnected(500)
    socket.disconnectFromServer()
    return connected


def listen_for_activation(name: str, show_window, parent=None) -> QLocalServer:
    server = QLocalServer(parent)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def incoming() -> None:
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            show_window()
            connection.disconnectFromServer()

    server.newConnection.connect(incoming)
    if not server.listen(name):
        # A crash may leave a stale socket. The instance lock is held by this
        # process, so no other live Lucifer instance can own this name.
        QLocalServer.removeServer(name)
        if not server.listen(name):
            raise RuntimeError(
                f"Could not create the desktop activation socket: {server.errorString()}"
            )
    return server
