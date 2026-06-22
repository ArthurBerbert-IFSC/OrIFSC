import sys
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QStatusBar
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtCore import QObject, pyqtSlot, QUrl, QFile, QIODevice, pyqtSignal


class MapBridge(QObject):
    """Bridge between the Leaflet map (JS) and Python backend."""

    statusMessage = pyqtSignal(str)

    def __init__(self, window):
        super().__init__()
        self._window = window

    @pyqtSlot(str)
    def exportGeoJSON(self, geojson_str: str):
        path, _ = QFileDialog.getSaveFileName(
            self._window, "Salvar GeoJSON", "mapa.geojson", "GeoJSON (*.geojson)"
        )
        if not path:
            return
        data = json.loads(geojson_str)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.statusMessage.emit(f"Salvo: {path}")


def _inject_qwebchannel(view: QWebEngineView) -> None:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    f.open(QIODevice.OpenModeFlag.ReadOnly)
    js = bytes(f.readAll()).decode("utf-8")
    f.close()

    script = QWebEngineScript()
    script.setName("qwebchannel")
    script.setSourceCode(js)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    view.page().scripts().insert(script)


def main():
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("OrMap — POC")
    window.resize(1280, 800)

    status = QStatusBar()
    window.setStatusBar(status)
    status.showMessage("Pronto. Use as ferramentas de desenho no mapa.")

    view = QWebEngineView()

    channel = QWebChannel()
    bridge = MapBridge(window)
    bridge.statusMessage.connect(status.showMessage)
    channel.registerObject("backend", bridge)
    view.page().setWebChannel(channel)

    _inject_qwebchannel(view)

    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map.html")
    view.setUrl(QUrl.fromLocalFile(html_path))

    window.setCentralWidget(view)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
