import argparse
import sys
from pathlib import Path

import pandas as pd


def load_excel(file_path: str | Path, sheet_name: str | int = 0, **kwargs) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    if path.suffix.lower() not in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
        raise ValueError(f"Неподдерживаемый формат: {path.suffix}")
    return pd.read_excel(path, sheet_name=sheet_name, **kwargs)


def load_sheets(file_path: str | Path) -> dict[str, pd.DataFrame]:
    return pd.read_excel(file_path, sheet_name=None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Извлечение таблицы из Excel в pandas DataFrame")
    parser.add_argument("file", help="Путь к Excel-файлу")
    parser.add_argument("-s", "--sheet", default=0, help="Имя или номер листа (по умолчанию 0)")
    parser.add_argument("-o", "--out", help="Сохранить результат в CSV")
    args = parser.parse_args()

    sheet: str | int = int(args.sheet) if str(args.sheet).isdigit() else args.sheet

    try:
        df = load_excel(args.file, sheet_name=sheet)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(df.head().to_string())
    print(f"\nСтрок: {len(df)}, столбцов: {len(df.columns)}")

    if args.out:
        df.to_csv(args.out, index=False)
        print(f"Сохранено в {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
