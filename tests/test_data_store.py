import pandas as pd
import pytest

from motor_fault.data_store import (RAW_COLUMNS, CsvWriter, DataFormatError, csv_bytes, df_to_csv_bytes,
                                    new_run_id, read_raw_csv)


def test_writer_columns_and_no_overwrite(tmp_path):
    p = tmp_path / "x.csv"
    w = CsvWriter(p, RAW_COLUMNS)
    assert csv_bytes(p) is None  # header only => empty export
    w.write({c: 1 for c in RAW_COLUMNS})
    w.close()
    assert list(pd.read_csv(p).columns) == RAW_COLUMNS
    assert csv_bytes(p) is not None
    with pytest.raises(FileExistsError):
        CsvWriter(p, RAW_COLUMNS)


def test_read_raw_validation(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(DataFormatError):
        read_raw_csv(p)
    q = tmp_path / "empty.csv"
    q.write_text(",".join(RAW_COLUMNS) + "\n")
    with pytest.raises(DataFormatError):
        read_raw_csv(q)


def test_empty_df_export():
    assert df_to_csv_bytes(pd.DataFrame()) is None
    assert csv_bytes(None) is None


def test_run_id_marks_mode():
    assert new_run_id("simulation", "a b!").startswith("simulation_")
