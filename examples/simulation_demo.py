"""
Quick demo of the MIDAS condition index simulation pipeline.

Generates a single installation, runs a 24-month degradation simulation,
and prints a summary of results.

Run from the repo root:
    uv run python examples/simulation_demo.py
"""

from datetime import datetime
from pathlib import Path

from src.config import MIDASSettings
from src.simulation.generator import DataGenerator
from src.simulation.runner import SimulationRunner
from src.simulation.weather import WeatherStressProvider
from src.simulation.work_orders import WorkOrderReader


WORK_ORDERS_PATH = Path("src/simulation/work_orders/data/sample_work_orders.xlsx")


CONFIG_PATH = Path("src/config/midas_config_values.xlsx")


def main():
    # Setup
    print("Loading config...")
    settings = MIDASSettings.from_excel(CONFIG_PATH)

    print("Loading weather stress data...")
    weather = WeatherStressProvider()

    print(f"Weather data loaded for {len(weather.all_bases())} bases.\n")

    # Generate a simulated installation
    generator = DataGenerator(settings=settings, seed=42)
    installation, facilities, _ = generator.generate_installation()

    print(f"Installation : {installation.title}")
    print(f"Location     : {installation.location}, {installation.region}")
    print(f"Facilities   : {len(facilities)}")

    # Show the weather stress and location bucket for this base
    from src.simulation.location import LocationProfile
    profile = LocationProfile.from_base_name(installation.title)
    stress  = weather.get_stress(installation.title)
    in_forecast = installation.title in weather.all_bases()
    stress_note = "from forecast data" if in_forecast else "cluster fallback — base not in forecast dataset"
    print(f"Climate      : {profile.bucket.value}  (factor={profile.degradation_factor}x)")
    print(f"Weather stress: {stress:.3f}  ({stress_note})\n")

    # Run 24-month simulation
    print("Running 24-month simulation...")
    runner = SimulationRunner(
        installation=installation,
        facilities=facilities,
        weather=weather,
        work_orders=None, # no work order Excel yet
        interval="monthly",
        start_date=datetime(2026, 1, 1),
        seed=42,
    )

    result = runner.run(n_steps=24)

    # Print results
    print(f"\n{'Month':<8} {'Installation CI':>16}")
    print("-" * 26)
    for i, ci in enumerate(result.installation_ci_history, start=1):
        print(f"{i:<8} {ci:>16.2f}")

    print(f"\nFinal installation CI : {result.final_installation_ci:.2f}")

    print(f"\n{'Facility':<38} {'Start CI':>9} {'Final CI':>9} {'State'}")
    print("-" * 70)
    for fac, res in zip(facilities, result.facility_results.values()):
        start_ci = res.condition_history[0]
        print(f"{fac.id:<38} {start_ci:>9.2f} {res.final_ci:>9.2f}  {res.final_state}")

    degraded = result.degraded_facilities
    if degraded:
        print(f"\n  {len(degraded)} facility/facilities reached Moderate or worse:")
        for r in degraded:
            print(f"   {r.facility_id}  ->  {r.final_state}  (CI={r.final_ci:.2f})")
    else:
        print("\nAll facilities remain in Minor or better condition.")

    # Second run: known base with real forecast data + work orders
    print("SECOND RUN - Peterson Space Force Base + work orders (stressed config, 10 years)")

    print("Loading work orders...")
    work_orders = WorkOrderReader(WORK_ORDERS_PATH)
    print(f"Installations in work order file: {work_orders.installations()}")

    from src.models import Installation

    peterson_profile = LocationProfile.from_base_name("Peterson Space Force Base")
    peterson_stress  = weather.get_stress("Peterson Space Force Base")
    in_forecast = "Peterson Space Force Base" in weather.all_bases()
    stress_note = "from forecast data" if in_forecast else "cluster fallback"
    print(f"Climate      : {peterson_profile.bucket.value}  (factor={peterson_profile.degradation_factor}x)")
    print(f"Weather stress: {peterson_stress:.3f}  ({stress_note})")
    print(f"Facilities in work order file: {work_orders.facilities('Peterson SFB')}\n")

    # Trying to get show a degraded test run, technically this case isn't or is very rarely ever possible bc you cant just say oh weather hits harder but yknow what i mean
    from src.simulation.condition_index import ConditionModelConfig

    stressed_config = ConditionModelConfig(
        initial_condition=60.0,         # start degraded, not brand new
        annual_base_degradation=6.0,    # 6 CI points/year base aging
        alpha_weather=10.0,             # weather hits harder
        beta_deferred=1.5,              # deferred backlog piles up faster
        noise_std=1.5,                  # more realistic variation
    )

    # Use Peterson Space Force Base as the full title so location/cluster lookup
    # resolves correctly, but pass wo_installation_name="Peterson SFB" so the
    # work order reader finds the right rows (generator uses the short name).
    peterson = Installation(
        title="Peterson Space Force Base",
        location="Colorado Springs",
        region="Colorado",
    )

    result2 = SimulationRunner(
        installation=peterson,
        facilities=facilities,
        weather=weather,
        work_orders=work_orders,
        interval="monthly",
        start_date=datetime(2026, 2, 1),
        model_config=stressed_config,
        seed=42,
        wo_installation_name="Peterson SFB",
    ).run(n_steps=120)  # 10 years

    print(f"\n{'Month':<8} {'Installation CI':>16} {'State band'}")
    print("-" * 45)
    for i, ci in enumerate(result2.installation_ci_history, start=1):
        band = "Healthy" if ci >= 80 else "Minor" if ci >= 60 else "Moderate" if ci >= 40 else "Severe" if ci >= 20 else "Failed"
        print(f"{i:<8} {ci:>16.2f}   {band}")

    print(f"\n{'Facility':<38} {'Start CI':>9} {'Final CI':>9} {'State'}")
    print("-" * 70)
    for fac, res in zip(facilities, result2.facility_results.values()):
        print(f"{fac.id:<38} {res.condition_history[0]:>9.2f} {res.final_ci:>9.2f}  {res.final_state}")

    print(f"\nFinal installation CI: {result2.final_installation_ci:.2f}")


if __name__ == "__main__":
    main()
