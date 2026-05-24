import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
TARGET = HERE / "Historical Amex Combined.csv"
PATTERN = re.compile(r"activity \((\d+)\)\.csv$", re.IGNORECASE)


def find_inputs() -> list[Path]:
    files = [p for p in HERE.iterdir() if p.is_file() and PATTERN.search(p.name)]
    files.sort(key=lambda p: int(PATTERN.search(p.name).group(1)))
    return files


def convert_one(src: Path, writer: csv.writer) -> tuple[int, int, int, int]:
    total = written = pos_out = neg_out = 0
    with src.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            raw_amount = (row.get("Amount") or "").strip()
            if not raw_amount:
                continue
            try:
                value = float(raw_amount)
            except ValueError:
                continue
            flipped = -value
            writer.writerow([
                (row.get("Date") or "").strip(),
                (row.get("Description") or "").strip(),
                f"{flipped:.2f}",
            ])
            written += 1
            if flipped > 0:
                pos_out += 1
            elif flipped < 0:
                neg_out += 1
    return total, written, pos_out, neg_out


def main() -> None:
    inputs = find_inputs()
    if not inputs:
        print(f"No files matching 'activity (N).csv' found in {HERE}", file=sys.stderr)
        sys.exit(1)

    grand_total = grand_written = grand_pos = grand_neg = 0
    with TARGET.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["Date", "Description", "Amount"])
        for src in inputs:
            total, written, pos_out, neg_out = convert_one(src, writer)
            grand_total += total
            grand_written += written
            grand_pos += pos_out
            grand_neg += neg_out
            print(f"  {src.name}: read {total}, wrote {written} ({neg_out} charges, {pos_out} credits)")

    print()
    print(f"Combined {len(inputs)} file(s) -> {TARGET.name}")
    print(f"Total read:   {grand_total}")
    print(f"Total wrote:  {grand_written}")
    print(f"  charges (negative Amount): {grand_neg}")
    print(f"  credits (positive Amount): {grand_pos}")


if __name__ == "__main__":
    main()
