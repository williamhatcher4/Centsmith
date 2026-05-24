import csv
from pathlib import Path

SOURCE = Path(__file__).with_name("Historical Monthly Amex Formal.csv")
TARGET = Path(__file__).with_name("Historical Monthly Amex Converted.csv")


def main() -> None:
    total = 0
    written = 0
    pos_out = 0
    neg_out = 0

    with SOURCE.open("r", encoding="utf-8-sig", newline="") as src, \
         TARGET.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["Date", "Description", "Amount"])

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

    print(f"Read:    {total} rows from {SOURCE.name}")
    print(f"Wrote:   {written} rows to   {TARGET.name}")
    print(f"  charges (negative Amount): {neg_out}")
    print(f"  credits (positive Amount): {pos_out}")


if __name__ == "__main__":
    main()
