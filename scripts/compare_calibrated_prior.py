"""Compare calibrated classifiers against their training-prior Brier baseline."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("output")
    args = parser.parse_args()
    with open(args.report) as stream:
        report = json.load(stream)
    output = {"metric": "test Brier loss, lower is better", "feeds": {},
              "limitation": "Exploratory interval previously inspected"}
    wins = 0
    total = 0
    for feed, config in report["feeds"].items():
        horizons = {}
        for horizon, results in config["horizons"].items():
            prior = results["direction"]["prior"]["brier"]
            candidates = {}
            for name, calibration in results["calibration"].items():
                loss = calibration["calibrated_test_brier"]
                candidates[name] = {
                    "brier": loss, "prior_brier": prior,
                    "loss_reduction": prior - loss, "beats_prior": loss < prior,
                }
                wins += loss < prior
                total += 1
            horizons[horizon] = candidates
        output["feeds"][feed] = horizons
    output.update(cases_beating_prior=wins, cases=total)
    with open(args.output, "x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
