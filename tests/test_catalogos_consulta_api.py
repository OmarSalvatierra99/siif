import os
import tempfile
import unittest
from datetime import date


DB_FILE = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
DB_FILE.close()
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.name}"

from app import create_app  # noqa: E402
from scripts.utils import Transaccion, Usuario, db  # noqa: E402


class CatalogosConsultaApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app("default")
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            for username, nombre_completo in (("juan", "Juan"), ("miguel", "Miguel")):
                user = Usuario.query.filter_by(username=username).first()
                if user is None:
                    user = Usuario(username=username)
                user.nombre_completo = nombre_completo
                user.activo = True
                db.session.add(user)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

        if os.path.exists(DB_FILE.name):
            os.unlink(DB_FILE.name)

    def _login_as(self, username):
        with self.client.session_transaction() as session:
            session["auth_user"] = username

    def setUp(self):
        with self.app.app_context():
            db.session.query(Transaccion).delete()
            db.session.commit()

    def _seed_estatal_and_municipal_transacciones(self):
        with self.app.app_context():
            db.session.add_all(
                [
                    Transaccion(
                        lote_id="lote-estatal",
                        archivo_origen="estatal.xlsx",
                        ente_siglas_catalogo="EJECUTIVO",
                        ente_nombre_catalogo="PODER EJECUTIVO DEL ESTADO DE TLAXCALA",
                        ente_grupo_catalogo="entes",
                        cuenta_contable="111111111111111111111",
                        nombre_cuenta="Caja",
                        genero="1",
                        grupo="1",
                        rubro="1",
                        cuenta="1",
                        subcuenta="1",
                        dependencia="01",
                        unidad_responsable="01",
                        centro_costo="01",
                        proyecto_presupuestario="01",
                        fuente="1",
                        subfuente="01",
                        tipo_recurso="1",
                        partida_presupuestal="1111",
                        fecha_transaccion=date(2026, 1, 15),
                        poliza="P-EST-001",
                        saldo_inicial=0,
                        cargos=100,
                        abonos=0,
                        saldo_final=100,
                        hash_registro="hash-estatal-001",
                    ),
                    Transaccion(
                        lote_id="lote-municipal",
                        archivo_origen="municipal.xlsx",
                        ente_siglas_catalogo="ACUAMANALA",
                        ente_nombre_catalogo="ACUAMANALA DE MIGUEL HIDALGO",
                        ente_grupo_catalogo="municipios",
                        cuenta_contable="222222222222222222222",
                        nombre_cuenta="Bancos",
                        genero="1",
                        grupo="1",
                        rubro="1",
                        cuenta="1",
                        subcuenta="1",
                        dependencia="0A",
                        unidad_responsable="01",
                        centro_costo="01",
                        proyecto_presupuestario="01",
                        fuente="1",
                        subfuente="01",
                        tipo_recurso="1",
                        partida_presupuestal="2222",
                        fecha_transaccion=date(2026, 1, 16),
                        poliza="P-MUN-001",
                        saldo_inicial=0,
                        cargos=200,
                        abonos=0,
                        saldo_final=200,
                        hash_registro="hash-municipal-001",
                    ),
                ]
            )
            db.session.commit()

    def test_catalogos_consulta_permissions_by_user(self):
        self._login_as("juan")
        response = self.client.get("/api/catalogos-consulta")
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertEqual(payload["catalogo_consulta_inicial"], "poder_ejecutivo")
        self.assertEqual(
            [item["id"] for item in payload["catalogos_consulta_disponibles"]],
            ["poder_ejecutivo"],
        )

        forbidden_response = self.client.get("/api/catalogos-consulta/opd_salud")
        self.assertEqual(forbidden_response.status_code, 403)

        self._login_as("miguel")
        response = self.client.get("/api/catalogos-consulta")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            [item["id"] for item in payload["catalogos_consulta_disponibles"]],
            ["opd_salud"],
        )

        self._login_as("luis")
        response = self.client.get("/api/catalogos-consulta")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            [item["id"] for item in payload["catalogos_consulta_disponibles"]],
            ["poder_ejecutivo", "opd_salud"],
        )

    def test_catalogos_consulta_detail_uses_reference_entities(self):
        self._login_as("luis")

        ejecutivo_response = self.client.get("/api/catalogos-consulta/poder_ejecutivo")
        self.assertEqual(ejecutivo_response.status_code, 200)
        ejecutivo_payload = ejecutivo_response.get_json()["catalogo_consulta"]

        ejecutivo_siglas = {item["siglas"] for item in ejecutivo_payload["entes_referencia"]}
        self.assertIn("EJECUTIVO", ejecutivo_siglas)
        self.assertIn("DG", ejecutivo_siglas)
        self.assertNotIn("OPD_SALUD", ejecutivo_siglas)
        self.assertGreater(ejecutivo_payload["totales"]["fuentes_financiamiento_referencia"], 0)

        opd_response = self.client.get("/api/catalogos-consulta/opd_salud")
        self.assertEqual(opd_response.status_code, 200)
        opd_payload = opd_response.get_json()["catalogo_consulta"]

        opd_siglas = [item["siglas"] for item in opd_payload["entes_referencia"]]
        self.assertTrue(opd_siglas)
        self.assertTrue(all(sigla == "OPD_SALUD" for sigla in opd_siglas))
        self.assertGreater(opd_payload["totales"]["fuentes_financiamiento_referencia"], 0)

    def test_existing_catalog_and_transaccion_endpoints_still_respond(self):
        self._login_as("luis")

        catalogo_general_response = self.client.get("/api/catalogo-general")
        self.assertEqual(catalogo_general_response.status_code, 200)
        catalogo_general_payload = catalogo_general_response.get_json()
        self.assertIn("opciones", catalogo_general_payload)
        self.assertIn("stats", catalogo_general_payload)

        resumen_response = self.client.get("/api/transacciones/resumen")
        self.assertEqual(resumen_response.status_code, 200)
        resumen_payload = resumen_response.get_json()
        self.assertIn("total_registros", resumen_payload)
        self.assertIn("coincide", resumen_payload)

    def test_luis_and_juan_do_not_see_municipios_in_catalogo_or_transacciones(self):
        self._seed_estatal_and_municipal_transacciones()

        for username in ("luis", "juan"):
            self._login_as(username)

            catalogo_response = self.client.get("/api/catalogo-general")
            self.assertEqual(catalogo_response.status_code, 200)
            catalogo_payload = catalogo_response.get_json()
            self.assertEqual(catalogo_payload["stats"]["municipios"], 0)
            self.assertTrue(
                all(item["grupo"] == "entes" for item in catalogo_payload["opciones"])
            )

            transacciones_response = self.client.get("/api/transacciones?include_totals=true")
            self.assertEqual(transacciones_response.status_code, 200)
            transacciones_payload = transacciones_response.get_json()
            self.assertEqual(transacciones_payload["total"], 1)
            self.assertEqual(transacciones_payload["total_registros"], 1)
            self.assertEqual(
                [item["ente_siglas_catalogo"] for item in transacciones_payload["transacciones"]],
                ["EJECUTIVO"],
            )

            filtros_response = self.client.get("/api/transacciones/filtros?fields=ente_catalogo")
            self.assertEqual(filtros_response.status_code, 200)
            filtros_payload = filtros_response.get_json()
            ente_catalogo_items = filtros_payload["options"]["ente_catalogo"]["items"]
            self.assertTrue(ente_catalogo_items)
            self.assertTrue(
                all(item["ambito"] != "MUNICIPAL" for item in ente_catalogo_items)
            )


if __name__ == "__main__":
    unittest.main()
