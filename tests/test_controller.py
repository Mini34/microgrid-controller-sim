import unittest

from microgrid_controller.controller import ControllerConfig, MicrogridController, PowerState
from microgrid_controller.simulation import day_profile


class MicrogridControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = MicrogridController()

    def test_surplus_solar_charges_battery(self) -> None:
        result = self.controller.dispatch(PowerState(8.0, 3.0, 0.50))
        self.assertEqual(result.mode, "solar_charging")
        self.assertEqual(result.battery_charge_kw, 5.0)
        self.assertGreater(result.next_soc, 0.50)

    def test_peak_shaving_holds_grid_limit(self) -> None:
        result = self.controller.dispatch(PowerState(0.0, 10.0, 0.80))
        self.assertEqual(result.mode, "peak_shaving")
        self.assertAlmostEqual(result.grid_import_kw, 6.0)
        self.assertAlmostEqual(result.battery_discharge_kw, 4.0)

    def test_outage_uses_battery(self) -> None:
        result = self.controller.dispatch(PowerState(1.0, 4.0, 0.70, grid_available=False))
        self.assertEqual(result.mode, "islanded")
        self.assertEqual(result.grid_import_kw, 0.0)
        self.assertEqual(result.unserved_load_kw, 0.0)

    def test_empty_battery_causes_unserved_load(self) -> None:
        cfg = ControllerConfig(min_soc=0.20)
        controller = MicrogridController(cfg)
        result = controller.dispatch(PowerState(0.0, 4.0, 0.20, grid_available=False))
        self.assertEqual(result.mode, "load_shed")
        self.assertEqual(result.unserved_load_kw, 4.0)
        self.assertEqual(result.next_soc, 0.20)

    def test_grid_import_limit_is_enforced_when_battery_is_empty(self) -> None:
        controller = MicrogridController(
            ControllerConfig(min_soc=0.20, grid_import_limit_kw=6.0)
        )
        result = controller.dispatch(PowerState(0.0, 10.0, 0.20))
        self.assertEqual(result.mode, "load_shed")
        self.assertEqual(result.grid_import_kw, 6.0)
        self.assertEqual(result.unserved_load_kw, 4.0)
        self.assertEqual(result.balance_error_kw, 0.0)

    def test_balance_error_is_zero_for_each_operating_mode(self) -> None:
        states = [
            PowerState(8.0, 3.0, 0.50),
            PowerState(0.0, 10.0, 0.80),
            PowerState(1.0, 4.0, 0.70, grid_available=False),
            PowerState(0.0, 4.0, 0.15, grid_available=False),
        ]
        self.assertTrue(
            all(self.controller.dispatch(state).balance_error_kw == 0.0 for state in states)
        )

    def test_efficiencies_must_be_physical(self) -> None:
        with self.assertRaises(ValueError):
            ControllerConfig(charge_efficiency=0.0)
        with self.assertRaises(ValueError):
            ControllerConfig(discharge_efficiency=1.01)

    def test_day_profile_respects_soc_and_grid_limit(self) -> None:
        rows = day_profile()
        self.assertTrue(all(0.15 <= float(row["next_soc"]) <= 0.95 for row in rows))
        self.assertTrue(all(float(row["grid_import_kw"]) <= 6.0 for row in rows))
        self.assertTrue(all(abs(float(row["balance_error_kw"])) < 1e-9 for row in rows))
        outage_rows = [row for row in rows if not row["grid_available"]]
        self.assertTrue(outage_rows)
        self.assertTrue(all(float(row["grid_import_kw"]) == 0.0 for row in outage_rows))
        self.assertTrue(all(row["mode"] in {"islanded", "load_shed"} for row in outage_rows))


if __name__ == "__main__":
    unittest.main()
