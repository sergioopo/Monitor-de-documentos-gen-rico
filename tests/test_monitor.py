import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor import discover, load_sources, run


class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "prueba", "name": "Prueba", "url": "https://example.org/listado/",
            "selector": "main a[href]", "extensions": [".pdf"], "enabled": True,
        }

    def test_filtro_y_enlaces_relativos(self):
        html = '<a href="/fuera.pdf">Fuera</a><main><a href="../uno.pdf">Uno</a><a href="otro">No</a></main>'
        self.assertEqual([v["url"] for v in discover(self.source, html).values()],
                         ["https://example.org/uno.pdf"])

    def test_type_application_y_aria_label(self):
        html = ('<main><a href="/archivo/123" type="application/pdf" '
                'aria-label="Resolución de prueba"></a>'
                '<a href="/pagina" type="application/xhtml+xml">No es documento</a></main>')
        found = list(discover(self.source, html).values())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "Resolución de prueba")

    def test_atributo_download_y_marcadores(self):
        html = ('<main><a href="/fichero/123" download>Adjunto</a>'
                '<a href="/descargas/456">Resolución</a></main>')
        source = {**self.source, "download_markers": ["/descargas/"]}
        self.assertEqual(len(discover(source, html)), 2)

    def test_extension_en_query(self):
        html = '<main><a href="/archivo?id=123&nombre=acta.pdf">Acta</a></main>'
        self.assertEqual(len(discover(self.source, html)), 1)

    def test_deduplicacion(self):
        html = '<main><a href="/a.pdf">A</a><a href="/a.pdf">A</a></main>'
        self.assertEqual(len(discover(self.source, html)), 1)

    def test_id_por_fuente(self):
        html = '<main><a href="/a.pdf">A</a></main>'
        self.assertNotEqual(list(discover(self.source, html)),
                            list(discover({**self.source, "id": "otra"}, html)))

    def test_inventario_y_envio_posterior(self):
        first = discover(self.source, '<main><a href="/a.pdf">A</a></main>')
        second = discover(self.source, '<main><a href="/a.pdf">A</a><a href="/b.pdf">B</a></main>')
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            with patch("monitor.discover", side_effect=[first, second]), patch("monitor.send_document") as send:
                self.assertEqual(run([self.source], state), [])
                send.assert_not_called()
                self.assertEqual(run([self.source], state, token="test", default_chat="-100"), [])
                send.assert_called_once()
            self.assertEqual(len(json.loads(state.read_text())["prueba"]["processed"]), 2)

    def test_cambio_de_url_crea_nuevo_inventario_sin_enviar(self):
        first = discover(self.source, '<main><a href="/a.pdf">A</a></main>')
        other = {**self.source, "url": "https://otra.example.org/documentos"}
        changed = discover(other, '<main><a href="/nuevo.pdf">Nuevo</a></main>')
        later = discover(other, '<main><a href="/nuevo.pdf">Nuevo</a><a href="/posterior.pdf">Posterior</a></main>')
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            with patch("monitor.discover", side_effect=[first, changed, later]), patch("monitor.send_document") as send:
                self.assertEqual(run([self.source], state), [])
                self.assertEqual(run([other], state, token="test", default_chat="-100"), [])
                send.assert_not_called()
                data = json.loads(state.read_text())["prueba"]
                self.assertEqual(data["url"], other["url"])
                self.assertEqual(len(data["processed"]), 1)
                self.assertEqual(run([other], state, token="test", default_chat="-100"), [])
                send.assert_called_once()

    def test_migracion_de_estado_antiguo_sin_envios(self):
        found = discover(self.source, '<main><a href="/a.pdf">A</a></main>')
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            state.write_text(json.dumps({"prueba": ["identificador_antiguo"]}))
            with patch("monitor.discover", return_value=found), patch("monitor.send_document") as send:
                self.assertEqual(run([self.source], state, token="test", default_chat="-100"), [])
                send.assert_not_called()
            self.assertEqual(json.loads(state.read_text())["prueba"]["url"], self.source["url"])

    def test_simulacion_sin_estado(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            with patch("monitor.discover", return_value={}):
                self.assertEqual(run([self.source], state, dry_run=True), [])
            self.assertFalse(state.exists())

    def test_identificador_duplicado(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "sources.json"
            config.write_text(json.dumps({"sources": [self.source, self.source]}))
            with self.assertRaises(ValueError):
                load_sources(config)


if __name__ == "__main__":
    unittest.main()
