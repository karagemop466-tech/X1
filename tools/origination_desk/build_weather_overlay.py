#!/usr/bin/env python3
"""Build the Week 11 Stadium Roof/Surface & Official NWS Weather Overlay register (Brief Row 59).

Joins every Week 11 NFL fixture's verified Game Center venue transcription
(`data/decision_review/venues.tsv`) with live official US National Weather Service
(`https://api.weather.gov`) forecast grids retrieved on 2026-11-19.

Strict zero-inference policy:
  * Pre-kickoff NFL Game Center pages do not print roof or playing surface
    (`surface-not-on-page;roof-not-on-page`). Both columns remain strictly blank ("")
    until confirmed by an official 90-minute roof designation or post-game Game Book.
  * International fixtures outside US NWS coverage (`vikings-at-49ers` in Mexico City)
    leave all NWS weather cells blank ("") and carry an explicit coverage flag.

Usage:
  python3 tools/origination_desk/build_weather_overlay.py
  python3 tools/origination_desk/build_weather_overlay.py --check
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "origination_desk" / "weather"
CAPTURED_DATE = "2026-11-19"
SCHEDULE_W11_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"

# Exact NWS gridpoint forecasts fetched live from https://api.weather.gov on 2026-11-19T06:56-07:20Z.
# Keyed by Week 11 Game Center slug.
NWS_BY_SLUG = {
    "colts-at-texans": {
        "away": "IND", "home": "HOU", "kickoff_et": "2026-11-19 8:15 PM ET",
        "lat_lon": "29.6847,-95.4107", "nws_grid": "HGX/61,91", "elevation_m": "15.8",
        "nws_update_utc": "2026-11-19T06:21:10Z",
        "forecast_period": "Hourly 2026-11-19 19:00-22:00 CST",
        "temp_f": "66", "wind": "5 mph NE (0 mph after 20:00 CST)", "precip_pct": "0",
        "short_forecast": "Partly Cloudy",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "GATED_ON_90MIN_ROOF (tonight 6:45 PM ET declaration; calm exterior; Game Center prints legacy RELIANT STADIUM vs NRG Stadium)",
        "nws_source_url": "https://api.weather.gov/gridpoints/HGX/61,91/forecast/hourly",
    },
    "dolphins-at-bills": {
        "away": "MIA", "home": "BUF", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "42.7738,-78.7870", "nws_grid": "BUF/39,42", "elevation_m": "224.0",
        "nws_update_utc": "2026-11-19T06:22:16Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 EST",
        "temp_f": "64", "wind": "8 mph S", "precip_pct": "10",
        "short_forecast": "Partly Sunny",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "LOW_WEATHER_RISK (mild 64F, 8 mph S, 10% PoP; roof/surface unprinted on pre-kickoff Game Center)",
        "nws_source_url": "https://api.weather.gov/gridpoints/BUF/39,42/forecast",
    },
    "ravens-at-panthers": {
        "away": "BAL", "home": "CAR", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "35.2258,-80.8528", "nws_grid": "GSP/118,65", "elevation_m": "198.1",
        "nws_update_utc": "2026-11-19T06:23:41Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 EST",
        "temp_f": "68", "wind": "6 to 12 mph N", "precip_pct": "19",
        "short_forecast": "Slight Chance Light Rain",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "LOW_PRECIP_WATCH (19% PoP before 1pm ET, 6-12 mph N; roof/surface unprinted on Game Center)",
        "nws_source_url": "https://api.weather.gov/gridpoints/GSP/118,65/forecast",
    },
    "saints-at-bears": {
        "away": "NO", "home": "CHI", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "41.8623,-87.6167", "nws_grid": "LOT/76,72", "elevation_m": "181.1",
        "nws_update_utc": "2026-11-19T06:21:01Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 CST",
        "temp_f": "57", "wind": "15 mph WSW", "precip_pct": "80",
        "short_forecast": "Rain Showers",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "HIGH_PRECIP_AND_WIND_ALERT (80% PoP Rain Showers + 15 mph WSW wind; highest Week 11 totals/passing exposure)",
        "nws_source_url": "https://api.weather.gov/gridpoints/LOT/76,72/forecast",
    },
    "titans-at-cowboys": {
        "away": "TEN", "home": "DAL", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "32.7473,-97.0945", "nws_grid": "FWD/78,103", "elevation_m": "177.1",
        "nws_update_utc": "2026-11-19T06:26:07Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 CST",
        "temp_f": "65", "wind": "10 to 15 mph NW (gusts 30 mph)", "precip_pct": "0",
        "short_forecast": "Sunny",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "GATED_ON_90MIN_ROOF (exterior gusts up to 30 mph NW; indoor/retractable exposure depends on 90-min club roof declaration)",
        "nws_source_url": "https://api.weather.gov/gridpoints/FWD/78,103/forecast",
    },
    "buccaneers-at-lions": {
        "away": "TB", "home": "DET", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "42.3400,-83.0456", "nws_grid": "DTX/66,34", "elevation_m": "174.0",
        "nws_update_utc": "2026-11-19T06:24:14Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 EST",
        "temp_f": "60", "wind": "10 mph SSW", "precip_pct": "58",
        "short_forecast": "Light Rain Likely",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "GATED_ON_ROOF_VERIFICATION (exterior 58% PoP rain; Game Center omits Ford Field roof/surface metadata pre-kickoff)",
        "nws_source_url": "https://api.weather.gov/gridpoints/DTX/66,34/forecast",
    },
    "cardinals-at-chiefs": {
        "away": "AZ", "home": "KC", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "39.0489,-94.4839", "nws_grid": "EAX/47,48", "elevation_m": "271.0",
        "nws_update_utc": "2026-11-19T06:41:17Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 CST",
        "temp_f": "51", "wind": "8 to 13 mph NNW", "precip_pct": "8",
        "short_forecast": "Mostly Sunny",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "MODERATE_BREEZE_POST_RAIN (95% Sat night rain clears to 8% PoP Sunday, 51F, 8-13 mph NNW)",
        "nws_source_url": "https://api.weather.gov/gridpoints/EAX/47,48/forecast",
    },
    "steelers-at-eagles": {
        "away": "PIT", "home": "PHI", "kickoff_et": "2026-11-22 1:00 PM ET",
        "lat_lon": "39.9008,-75.1675", "nws_grid": "PHI/50,76", "elevation_m": "0.9",
        "nws_update_utc": "2026-11-18T23:59:18Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 EST",
        "temp_f": "64", "wind": "5 mph NE", "precip_pct": "45",
        "short_forecast": "Chance Light Rain",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "MODERATE_PRECIP_WATCH (45% PoP Chance Light Rain, light 5 mph NE wind)",
        "nws_source_url": "https://api.weather.gov/gridpoints/PHI/50,76/forecast",
    },
    "jets-at-chargers": {
        "away": "NYJ", "home": "LAC", "kickoff_et": "2026-11-22 4:05 PM ET",
        "lat_lon": "33.9535,-118.3392", "nws_grid": "LOX/151,41", "elevation_m": "29.9",
        "nws_update_utc": "2026-11-19T06:26:34Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 PST",
        "temp_f": "67", "wind": "0 to 5 mph NNE", "precip_pct": "10",
        "short_forecast": "Sunny",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "BENIGN_WEATHER (67F, 0-5 mph NNE, 10% PoP; SoFi roof/canopy unprinted on pre-kickoff Game Center)",
        "nws_source_url": "https://api.weather.gov/gridpoints/LOX/151,41/forecast",
    },
    "jaguars-at-giants": {
        "away": "JAX", "home": "NYG", "kickoff_et": "2026-11-22 4:25 PM ET",
        "lat_lon": "40.8128,-74.0742", "nws_grid": "OKX/30,46", "elevation_m": "2.1",
        "nws_update_utc": "2026-11-19T06:21:36Z",
        "forecast_period": "Sun Day -> Sun Night (16:25-19:30 EST)",
        "temp_f": "61 -> 52", "wind": "5 to 14 mph NE", "precip_pct": "30 -> 65",
        "short_forecast": "Chance Light Rain -> Light Rain Likely",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "SECOND_HALF_RAIN_ESCALATION (PoP rises from 30% afternoon to 65% after 6:00 PM ET with 5-14 mph NE wind)",
        "nws_source_url": "https://api.weather.gov/gridpoints/OKX/30,46/forecast",
    },
    "raiders-at-broncos": {
        "away": "LV", "home": "DEN", "kickoff_et": "2026-11-22 4:25 PM ET",
        "lat_lon": "39.7439,-105.0201", "nws_grid": "BOU/62,62", "elevation_m": "1584.0",
        "nws_update_utc": "2026-11-19T06:46:26Z",
        "forecast_period": "Sunday 2026-11-22 06:00-18:00 MST",
        "temp_f": "48", "wind": "0 to 5 mph N", "precip_pct": "0",
        "short_forecast": "Mostly Sunny",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "ALTITUDE_CLEAR_COOL (1,584m / 5,197ft NWS grid elevation, 48F, 0-5 mph N, 0% PoP)",
        "nws_source_url": "https://api.weather.gov/gridpoints/BOU/62,62/forecast",
    },
    "vikings-at-49ers": {
        "away": "MIN", "home": "SF", "kickoff_et": "2026-11-22 8:20 PM ET",
        "lat_lon": "", "nws_grid": "", "elevation_m": "",
        "nws_update_utc": "",
        "forecast_period": "",
        "temp_f": "", "wind": "", "precip_pct": "",
        "short_forecast": "",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "OUTSIDE_US_NWS_COVERAGE (Mexico City Estadio Banorte; NWS covers US territories only; weather & roof left blank)",
        "nws_source_url": "",
    },
    "bengals-at-commanders": {
        "away": "CIN", "home": "WAS", "kickoff_et": "2026-11-23 8:15 PM ET",
        "lat_lon": "38.9076,-76.8645", "nws_grid": "LWX/102,73", "elevation_m": "29.9",
        "nws_update_utc": "2026-11-19T06:22:37Z",
        "forecast_period": "Monday Night 2026-11-23 18:00-06:00 EST",
        "temp_f": "37", "wind": "9 to 13 mph NW", "precip_pct": "7",
        "short_forecast": "Partly Cloudy",
        "roof_90min_status": "", "playing_surface": "",
        "totals_passing_flag": "COLD_NIGHT_BREEZE (37F low, 9-13 mph NW, 7% PoP; schedule hotel link still prints legacy FedEx Field vs Northwest Stadium)",
        "nws_source_url": "https://api.weather.gov/gridpoints/LWX/102,73/forecast",
    },
}


def build_all() -> dict[str, str]:
    venues_path = ROOT / "data" / "decision_review" / "venues.tsv"
    w11_venues: dict[str, dict[str, str]] = {}
    with venues_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for r in reader:
            if r["season"] == "2026" and r["week"] == "11":
                w11_venues[r["slug"]] = r

    if set(w11_venues.keys()) != set(NWS_BY_SLUG.keys()):
        missing = set(w11_venues.keys()) ^ set(NWS_BY_SLUG.keys())
        raise RuntimeError(f"Week 11 venue slug mismatch vsvenues.tsv: {sorted(missing)}")

    headers = [
        "season", "week", "slug", "away", "home", "kickoff_et",
        "game_center_stadium", "game_center_location",
        "official_90min_roof_status", "official_playing_surface",
        "nws_grid_id", "nws_elevation_m", "nws_update_utc", "nws_forecast_window",
        "nws_temp_f", "nws_wind", "nws_precip_pct", "nws_short_forecast",
        "overlay_risk_flag", "nws_source_url", "game_center_url",
    ]

    ordered_slugs = [
        "colts-at-texans", "dolphins-at-bills", "ravens-at-panthers", "saints-at-bears",
        "titans-at-cowboys", "buccaneers-at-lions", "cardinals-at-chiefs", "steelers-at-eagles",
        "jets-at-chargers", "jaguars-at-giants", "raiders-at-broncos", "vikings-at-49ers",
        "bengals-at-commanders",
    ]

    rows: list[list[object]] = []
    json_rows: list[dict[str, object]] = []
    for slug in ordered_slugs:
        v = w11_venues[slug]
        w = NWS_BY_SLUG[slug]
        # Verify Game Center too leaves surface & roof empty pre-kickoff
        assert v["surface"] == "" and v["roof"] == "", f"Unexpected roof/surface in venues.tsv for {slug}"
        row = [
            2026, 11, slug, w["away"], w["home"], w["kickoff_et"],
            v["stadium"], v["location"],
            w["roof_90min_status"], w["playing_surface"],
            w["nws_grid"], w["elevation_m"], w["nws_update_utc"], w["forecast_period"],
            w["temp_f"], w["wind"], w["precip_pct"], w["short_forecast"],
            w["totals_passing_flag"], w["nws_source_url"], v["game_url"],
        ]
        rows.append(row)
        json_rows.append(dict(zip(headers, row)))

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    csv_text = buf.getvalue()

    summary = {
        "dataset": "week11_stadium_nws_overlay",
        "captured_date": CAPTURED_DATE,
        "schedule_source_url": SCHEDULE_W11_URL,
        "weather_authority": "US National Weather Service API (https://api.weather.gov)",
        "venue_authority": "NFL.com Game Center pages via data/decision_review/venues.tsv",
        "counts": {
            "week11_fixtures": len(rows),
            "us_nws_covered_fixtures": sum(1 for r in json_rows if r["nws_grid_id"]),
            "international_blank_fixtures": sum(1 for r in json_rows if not r["nws_grid_id"]),
            "pre_90min_roof_confirmed": sum(1 for r in json_rows if r["official_90min_roof_status"]),
            "high_or_moderate_precip_alerts": sum(
                1 for r in json_rows
                if "HIGH_PRECIP" in str(r["overlay_risk_flag"])
                or "MODERATE_PRECIP" in str(r["overlay_risk_flag"])
                or "SECOND_HALF_RAIN" in str(r["overlay_risk_flag"])
            ),
        },
        "naming_discrepancies_flagged": [
            {
                "slug": "colts-at-texans",
                "game_center_prints": "RELIANT STADIUM",
                "schedule_page_hotel_link_prints": "NRG Stadium",
                "source_url": "https://www.nfl.com/games/colts-at-texans-2026-reg-11",
            },
            {
                "slug": "bengals-at-commanders",
                "game_center_prints": "NORTHWEST STADIUM",
                "schedule_page_hotel_link_prints": "FedEx Field",
                "source_url": "https://www.nfl.com/games/bengals-at-commanders-2026-reg-11",
            },
        ],
        "csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "rows": json_rows,
    }

    return {
        "week11_stadium_nws_overlay.csv": csv_text,
        "week11_stadium_nws_overlay.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    files = build_all()
    if args.check:
        diffs = []
        for name, content in sorted(files.items()):
            p = OUT_DIR / name
            if not p.exists():
                diffs.append(f"missing {p.relative_to(ROOT)}")
            elif p.read_text(encoding="utf-8") != content:
                diffs.append(f"stale {p.relative_to(ROOT)}")
        if diffs:
            print("FAIL weather overlay check:", "; ".join(diffs))
            return 1
        print(f"OK: {len(files)} weather-overlay files verified up to date in {OUT_DIR.relative_to(ROOT)}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        (OUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
