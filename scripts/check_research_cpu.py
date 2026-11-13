"""Offline synthetic integration checks for the full CPU research profile."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Literal, TypedDict
from unittest.mock import patch


def check_integrations(root: Path) -> None:
    import duckdb
    import mlflow
    import optuna
    import pyarrow as pa
    import pyarrow.parquet as pq
    from check_ml_baseline import main as check_models
    from langgraph.graph import END, START, StateGraph
    from pydantic import BaseModel, ValidationError

    table = pa.table({"synthetic_id": [0, 1, 2], "value": [1.0, 2.0, 3.0]})
    path = root / "synthetic.parquet"
    pq.write_table(table, path)
    restored = pq.read_table(path)
    if not restored.equals(table):
        raise RuntimeError("Parquet round trip changed synthetic data")
    with duckdb.connect(":memory:") as connection:
        connection.register("synthetic", restored)
        if connection.execute("SELECT SUM(value) FROM synthetic").fetchone() != (6.0,):
            raise RuntimeError("DuckDB/Arrow integration failed")

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(sampler=optuna.samplers.RandomSampler(seed=42))
    study.optimize(lambda trial: (trial.suggest_float("x", -1, 1) - 0.2) ** 2, n_trials=4)
    if len(study.trials) != 4:
        raise RuntimeError("Synthetic optimization failed")

    mlflow.set_tracking_uri("sqlite:///" + str(root / "tracking.db"))
    experiment = mlflow.create_experiment(
        "synthetic-environment-smoke", artifact_location=(root / "artifacts").as_uri())
    mlflow.set_experiment(experiment_id=experiment)
    with mlflow.start_run() as run:
        mlflow.log_param("data", "SYNTHETIC_ONLY")
        mlflow.log_metric("synthetic_loss", study.best_value)
        mlflow.log_artifact(str(path))
        run_id = run.info.run_id
    if mlflow.get_run(run_id).data.params.get("data") != "SYNTHETIC_ONLY":
        raise RuntimeError("Local MLflow tracking round trip failed")

    class State(TypedDict):
        steps: int

    graph = StateGraph(State)
    graph.add_node("local_step", lambda state: {"steps": state["steps"] + 1})
    graph.add_edge(START, "local_step")
    graph.add_edge("local_step", END)
    if graph.compile().invoke({"steps": 0}) != {"steps": 1}:
        raise RuntimeError("Local LangGraph state transition failed")

    class Decision(BaseModel):
        action: Literal["NO_TRADE"]

    if Decision.model_validate_json('{"action":"NO_TRADE"}').action != "NO_TRADE":
        raise RuntimeError("Pydantic decision contract failed")
    try:
        Decision.model_validate_json('{"action":"BUY"}')
    except ValidationError:
        pass
    else:
        raise RuntimeError("Synthetic decision contract accepted an execution action")
    check_models()
    print("PASS: synthetic Parquet/DuckDB, Optuna, local MLflow, LangGraph and Pydantic")


def main() -> None:
    attempts = []

    def forbid_network(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("Network access is forbidden during the research smoke test")

    with tempfile.TemporaryDirectory(prefix="gold-research-smoke-") as temp:
        root = Path(temp)
        settings = {
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
            "MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING": "false",
            "MLFLOW_DISABLE_AGENT_HINT": "1",
            "MLFLOW_DISABLE_TELEMETRY": "true",
            "MLFLOW_TRACKING_URI": "sqlite:///" + str(root / "tracking.db"),
        }
        with patch.dict(os.environ, settings), patch("socket.socket.connect", forbid_network), \
                patch("socket.socket.connect_ex", forbid_network), \
                patch("socket.create_connection", forbid_network):
            check_integrations(root)
    if attempts:
        raise RuntimeError(f"Integration attempted {len(attempts)} blocked network connections")
    print("PASS: offline CPU integration smoke; no market data, external model or trading")


if __name__ == "__main__":
    main()
