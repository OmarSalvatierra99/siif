from io import BytesIO
import tempfile
import unittest

from flask import Flask
from openpyxl import Workbook

from scripts.utils import (
    LoteCarga,
    Transaccion,
    _read_one_excel,
    db,
    process_files_to_database,
)


def _build_auxiliar_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active

    for row in rows:
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _build_macro_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active

    for row in rows:
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _base_auxiliar_rows():
    return [
        ["", "ENTE DE PRUEBA", "", "", "", "", "", "", ""],
        ["", "AUXILIAR DE CUENTA", "", "", "", "", "", "", ""],
        ["FECHA", "POLIZA", "", "", "O.P.", "SALDO INICIAL", "CARGOS", "ABONOS", "SALDO FINAL"],
        ["", "No.", "BENEFICIARIO", "DESCRIPCION", "", "", "", "", ""],
    ]


def _build_auxiliar_file(account_code, account_name, opening_balance, entries, period_start="01/01/2025"):
    rows = _base_auxiliar_rows() + [
        [f"CUENTA CONTABLE: {account_code} - {account_name}", "", "", "", "", "", "", "", ""],
        ["", "", "", f"SALDO INICIAL CUENTA {account_code} AL {period_start}", "", opening_balance, "", "", ""],
    ]
    rows.extend(entries)
    return _build_auxiliar_bytes(rows)


class ImportBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls.db_file.close()

        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{cls.db_file.name}"
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(cls.app)

        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.query(Transaccion).delete(synchronize_session=False)
            db.session.query(LoteCarga).delete(synchronize_session=False)
            db.session.commit()

    def test_read_one_excel_keeps_integer_cargo_in_cargos_column(self):
        rows = _base_auxiliar_rows() + [
            ["CUENTA CONTABLE: 111100000000000000001 - ACTIVO", "", "", "", "", "", "", "", ""],
            ["", "", "", "SALDO INICIAL CUENTA 111100000000000000001 AL 01/01/2025", "", 0, "", "", ""],
            ["2025-01-02", "TR - 1", "", "MOVIMIENTO DE PRUEBA", "", "", 109, 0, 109],
        ]

        df, _ = _read_one_excel(("prueba.xlsx", _build_auxiliar_bytes(rows)))

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["orden_pago"], "")
        self.assertEqual(df.iloc[0]["cargos"], "109")
        self.assertEqual(df.iloc[0]["abonos"], "0")
        self.assertEqual(df.iloc[0]["saldo_final"], "109")

    def test_process_files_to_database_rejects_unbalanced_batch(self):
        rows = _base_auxiliar_rows() + [
            ["CUENTA CONTABLE: 111100000000000000001 - ACTIVO", "", "", "", "", "", "", "", ""],
            ["", "", "", "SALDO INICIAL CUENTA 111100000000000000001 AL 01/01/2025", "", 0, "", "", ""],
            ["2025-01-02", "TR - 1", "", "MOVIMIENTO SIN CONTRAPARTIDA", "", "", 109, 0, 109],
        ]

        with self.app.app_context():
            with self.assertRaisesRegex(ValueError, "desbalanceada|desbalanceadas"):
                process_files_to_database(
                    [("desbalance.xlsx", _build_auxiliar_bytes(rows))],
                    usuario="test",
                    selected_ente_siglas="EJECUTIVO",
                    selected_ente_nombre="ENTE DE PRUEBA",
                    selected_ente_grupo="ESTATALES",
                )

            self.assertEqual(Transaccion.query.count(), 0)
            self.assertEqual(LoteCarga.query.count(), 1)
            lote = LoteCarga.query.first()
            self.assertEqual(lote.estado, "error")

    def test_process_files_to_database_accepts_split_contable_batch(self):
        activo = _build_auxiliar_file(
            "111100000000000000001",
            "ACTIVO",
            0,
            [["2025-01-02", "TR - 1", "", "MOVIMIENTO ACTIVO", "", "", 100, 0, 100]],
        )
        ingreso = _build_auxiliar_file(
            "415100000000000000001",
            "INGRESO",
            0,
            [["2025-01-02", "TR - 1", "", "MOVIMIENTO INGRESO", "", "", 0, 100, 100]],
        )

        with self.app.app_context():
            lote_id, total = process_files_to_database(
                [("activo.xlsx", activo), ("ingreso.xlsx", ingreso)],
                usuario="test",
                selected_ente_siglas="OPD_SALUD",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            self.assertEqual(total, 2)
            self.assertTrue(lote_id)
            self.assertEqual(Transaccion.query.count(), 2)
            lote = LoteCarga.query.filter_by(lote_id=lote_id).first()
            self.assertIsNotNone(lote)
            self.assertEqual(lote.estado, "completado")
            self.assertEqual(lote.total_registros, 2)

    def test_process_files_to_database_accepts_presupuestal_rollforward(self):
        presupuesto = _build_auxiliar_file(
            "8110002010001P6139121",
            "LEY DE INGRESOS ESTIMADA",
            338415348,
            [
                ["2025-01-01", "AALI - 100004", "", "POLIZA APERTURA INGRESO [ ABRIL ]", "", "", 92845193, 0, 431260541],
                ["2025-01-01", "AALI - 100005", "", "POLIZA APERTURA INGRESO [ MAYO ]", "", "", 117823041, 0, 549083582],
                ["2025-01-01", "AALI - 100006", "", "POLIZA APERTURA INGRESO [ JUNIO ]", "", "", 99443551, 0, 648527133],
            ],
            period_start="01/04/2025",
        )

        with self.app.app_context():
            lote_id, total = process_files_to_database(
                [("81.xlsx", presupuesto)],
                usuario="test",
                selected_ente_siglas="OPD_SALUD",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            self.assertEqual(total, 3)
            lote = LoteCarga.query.filter_by(lote_id=lote_id).first()
            self.assertEqual(lote.estado, "completado")

            transacciones = (
                Transaccion.query
                .order_by(Transaccion.id.asc())
                .all()
            )
            self.assertEqual(len(transacciones), 3)
            self.assertEqual([float(t.saldo_inicial) for t in transacciones], [338415348.0, 431260541.0, 549083582.0])
            self.assertEqual([float(t.saldo_final) for t in transacciones], [431260541.0, 549083582.0, 648527133.0])

    def test_process_files_to_database_rejects_invalid_rollforward(self):
        presupuesto = _build_auxiliar_file(
            "8110002010001P6139121",
            "LEY DE INGRESOS ESTIMADA",
            338415348,
            [
                ["2025-01-01", "AALI - 100004", "", "POLIZA APERTURA INGRESO [ ABRIL ]", "", "", 92845193, 0, 431260541],
                ["2025-01-01", "AALI - 100005", "", "POLIZA APERTURA INGRESO [ MAYO ]", "", "", 117823041, 0, 549000000],
            ],
            period_start="01/04/2025",
        )

        with self.app.app_context():
            with self.assertRaisesRegex(ValueError, "secuencia de saldos|saldos finales"):
                process_files_to_database(
                    [("81_invalid.xlsx", presupuesto)],
                    usuario="test",
                    selected_ente_siglas="OPD_SALUD",
                    selected_ente_nombre="ENTE DE PRUEBA",
                    selected_ente_grupo="ESTATALES",
                )

            self.assertEqual(Transaccion.query.count(), 0)
            lote = LoteCarga.query.first()
            self.assertIsNotNone(lote)
            self.assertEqual(lote.estado, "error")

    def test_process_files_to_database_preserves_repeated_source_lines(self):
        presupuesto = _build_auxiliar_file(
            "8110002010001P6139121",
            "LEY DE INGRESOS ESTIMADA",
            100,
            [
                ["2025-01-01", "AALI - 100004", "", "POLIZA APERTURA INGRESO [ ABRIL ]", "", "", 10, 0, 110],
                ["2025-01-01", "AALI - 100004", "", "POLIZA APERTURA INGRESO [ ABRIL ]", "", "", 10, 0, 120],
            ],
            period_start="01/04/2025",
        )

        with self.app.app_context():
            lote_id, total = process_files_to_database(
                [("81_repeat.xlsx", presupuesto)],
                usuario="test",
                selected_ente_siglas="OPD_SALUD",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            self.assertEqual(total, 2)
            self.assertEqual(Transaccion.query.filter_by(lote_id=lote_id).count(), 2)

    def test_process_files_to_database_accepts_macro_without_explicit_opening_balance(self):
        macro = _build_macro_bytes([
            [
                "Cuenta Contable", "Nombre Cuenta", "Fecha", "Poliza", "Beneficiario",
                "Descripcion", "O.P.", "Saldo Inicial", "Cargos", "Abonos", "Saldo Final",
            ],
            [
                "111100000000000000001", "ACTIVO", "2025-04-01", "POL-1", "", "Cargo activo",
                "", "", "100", "0", "1100",
            ],
            [
                "415100000000000000001", "INGRESO", "2025-04-01", "POL-1", "", "Abono ingreso",
                "", "", "0", "100", "1100",
            ],
        ])

        with self.app.app_context():
            lote_id, total = process_files_to_database(
                [("macro.xlsx", macro)],
                usuario="test",
                tipo_archivo="macro",
                selected_ente_siglas="EJECUTIVO",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            self.assertEqual(total, 2)
            transacciones = (
                Transaccion.query
                .filter_by(lote_id=lote_id)
                .order_by(Transaccion.cuenta_contable.asc())
                .all()
            )
            self.assertEqual(len(transacciones), 2)
            self.assertEqual(float(transacciones[1].saldo_inicial), 1000.0)
            self.assertEqual(float(transacciones[0].saldo_inicial), 1000.0)

    def test_process_files_to_database_seeds_macro_from_historical_balance(self):
        anterior = _build_macro_bytes([
            [
                "Cuenta Contable", "Nombre Cuenta", "Fecha", "Poliza", "Beneficiario",
                "Descripcion", "O.P.", "Saldo Inicial", "Cargos", "Abonos", "Saldo Final",
            ],
            [
                "42130080B0L6PP203832F", "INGRESO", "2025-06-19", "POL-ANT", "", "Cierre previo",
                "", "0", "0", "2750147.38", "2750147.38",
            ],
        ])
        siguiente = _build_macro_bytes([
            [
                "Cuenta Contable", "Nombre Cuenta", "Fecha", "Poliza", "Beneficiario",
                "Descripcion", "O.P.", "Saldo Inicial", "Cargos", "Abonos", "Saldo Final",
            ],
            [
                "42130080B0L6PP203832F", "INGRESO", "2025-07-01", "POL-7000001", "", "Movimiento nuevo",
                "", "0", "0", "1386624.31", "4136771.69",
            ],
        ])

        with self.app.app_context():
            process_files_to_database(
                [("junio.xlsx", anterior)],
                usuario="test",
                tipo_archivo="macro",
                enforce_contable_balance=False,
                selected_ente_siglas="EJECUTIVO",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            lote_id, total = process_files_to_database(
                [("julio.xlsx", siguiente)],
                usuario="test",
                tipo_archivo="macro",
                enforce_contable_balance=False,
                seed_historical_opening_balances=True,
                selected_ente_siglas="EJECUTIVO",
                selected_ente_nombre="ENTE DE PRUEBA",
                selected_ente_grupo="ESTATALES",
            )

            self.assertEqual(total, 1)
            movimiento = Transaccion.query.filter_by(lote_id=lote_id).first()
            self.assertIsNotNone(movimiento)
            self.assertEqual(float(movimiento.saldo_inicial), 2750147.38)
            self.assertEqual(float(movimiento.saldo_final), 4136771.69)
