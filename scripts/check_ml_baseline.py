"""Safe synthetic ML training smoke test. No financial data or trading."""

import numpy as np
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score


def main() -> None:
    rng = np.random.default_rng(42)

    features = rng.normal(size=(500, 6))

    labels = (
        1.2 * features[:, 0]
        - 0.8 * features[:, 1]
        + 0.25 * rng.normal(size=500)
        > 0
    ).astype(int)

    x_train, x_test = features[:400], features[400:]
    y_train, y_test = labels[:400], labels[400:]

    models = {
        "LightGBM": LGBMClassifier(
            n_estimators=40,
            max_depth=3,
            num_leaves=7,
            random_state=42,
            n_jobs=2,
            verbosity=-1,
        ),
        "CatBoost": CatBoostClassifier(
            iterations=40,
            depth=3,
            learning_rate=0.1,
            random_seed=42,
            thread_count=2,
            verbose=False,
            allow_writing_files=False,
        ),
    }

    for name, model in models.items():
        model.fit(x_train, y_train)

        predictions = np.asarray(
            model.predict(x_test)
        ).reshape(-1)

        if predictions.shape != y_test.shape:
            raise RuntimeError(
                f"{name}: Invalid prediction shape"
            )

        if not np.isin(predictions, [0, 1]).all():
            raise RuntimeError(
                f"{name}: Invalid predicted classes"
            )

        accuracy = float(
            accuracy_score(y_test, predictions)
        )

        if not np.isfinite(accuracy) or accuracy < 0.75:
            raise RuntimeError(
                f"{name}: Synthetic smoke test failed"
            )

        print(f"{name}: PASS — accuracy={accuracy:.4f}")

    print("PASS: ML baseline training smoke test")


if __name__ == "__main__":
    main()
