"""Store staged Headway quotes in typed Parquet and verify a lossless value round trip."""

import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

FIELDS = ("native_time_msc", "bid", "ask", "flags")
QUANTUM = Decimal("0.00000001")
BATCH = 65_536


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def semantic_update(digest, row):
    ordinal, native, bid, ask, flags = row
    digest.update(f"{ordinal},{native},{bid:.8f},{ask:.8f},{flags}\n".encode("ascii"))


def price(text):
    value = Decimal(text)
    fixed = value.quantize(QUANTUM)
    if not value.is_finite() or fixed != value or fixed <= 0:
        raise ValueError("Native price cannot be represented exactly at the Parquet scale")
    return fixed


def write_quotes(source, output):
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([
        pa.field("row_ordinal", pa.int64(), nullable=False),
        pa.field("native_time_msc", pa.int64(), nullable=False),
        pa.field("bid", pa.decimal128(24, 8), nullable=False),
        pa.field("ask", pa.decimal128(24, 8), nullable=False),
        pa.field("flags", pa.uint32(), nullable=False),
    ], metadata={b"time_basis": b"native_mt5_milliseconds_not_utc", b"server": b"Headway-Demo",
                 b"symbol": b"XAUUSD", b"evaluation_ready": b"false"})
    digest = hashlib.sha256()
    current = []
    count = 0
    previous = None

    def flush(writer):
        columns = [pa.array(values, type=field.type) for field, values in zip(schema, zip(*current), strict=True)]
        writer.write_batch(pa.RecordBatch.from_arrays(columns, schema=schema))

    with source.open(newline="", encoding="utf-8") as stream, pq.ParquetWriter(output, schema, compression="zstd") as writer:
        rows = csv.reader(stream, strict=True)
        if tuple(next(rows, ())) != FIELDS:
            raise ValueError("Expected staged native Headway columns")
        for stamp, bid, ask, flags in rows:
            try:
                native, bid_value, ask_value, flags_value = int(stamp), price(bid), price(ask), int(flags)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid native quote row {rows.line_num}") from exc
            if (native < 0 or (previous is not None and native < previous)
                    or bid_value > ask_value or not 0 <= flags_value < 2**32):
                raise ValueError("Invalid or out-of-order native quote")
            row = (count, native, bid_value, ask_value, flags_value)
            semantic_update(digest, row)
            current.append(row)
            previous, count = native, count + 1
            if len(current) == BATCH:
                flush(writer)
                current.clear()
        if current:
            flush(writer)
    reopened = pq.ParquetFile(output)
    if not reopened.schema_arrow.equals(schema, check_metadata=True):
        raise ValueError("Parquet round trip changed the schema or clock metadata")
    check = hashlib.sha256()
    restored_count = 0
    for batch in reopened.iter_batches(batch_size=BATCH):
        for row in zip(*(col.to_pylist() for col in batch.columns), strict=True):
            semantic_update(check, row)
            restored_count += 1
    if not count or restored_count != count or check.digest() != digest.digest():
        raise ValueError("Parquet round trip changed native quotes or row order")
    return count, digest.hexdigest(), pa.__version__


def pack(stage, expected, output):
    manifest_path = stage / "manifest.json"
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Native stage manifest fingerprint differs")
    manifest = json.loads(raw)
    if ((manifest["schema_version"], manifest["server"], manifest["symbol"], manifest["time_basis"])
            != (1, "Headway-Demo", "XAUUSD", "native_mt5_milliseconds_not_utc")
            or manifest["evaluation_ready"] is not False):
        raise ValueError("Expected a native-only Headway stage")
    source = stage / "quotes-native.csv"
    source_hash = sha(source)
    if source_hash != manifest["quotes_native_sha256"]:
        raise ValueError("Staged native CSV fingerprint differs")
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as temp:
        packed = Path(temp) / "quotes-native.parquet"
        count, roundtrip, version = write_quotes(source, packed)
        if count != manifest["quote_rows"] or source_hash != sha(source):
            raise ValueError("Staged native CSV changed or its row count differs")
        report = {"schema_version": 1, "server": "Headway-Demo", "symbol": "XAUUSD",
                  "reconciliation_sha256": manifest["reconciliation_sha256"], "source_manifest_sha256": expected,
                  "source_native_csv_sha256": source_hash, "parquet_sha256": sha(packed),
                  "parquet_bytes": packed.stat().st_size, "source_csv_bytes": source.stat().st_size,
                  "semantic_row_sha256": roundtrip, "quote_rows": count, "pyarrow_version": version,
                  "window_status_counts": manifest["window_status_counts"], "value_roundtrip_verified": True,
                  "utc_mapping_verified": False, "market_coverage_verified": False,
                  "evaluation_ready": False, "holdout_scored": False}
        record = Path(temp) / "manifest.json"
        record.write_text(json.dumps(report, indent=2) + "\n")
        output.mkdir(mode=0o700)
        packed.rename(output / packed.name)
        record.rename(output / record.name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("manifest_sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(pack(args.stage, args.manifest_sha256, args.output), indent=2))


if __name__ == "__main__":
    main()
