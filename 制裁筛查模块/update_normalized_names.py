"""
Deprecated.

This script used offset pagination while updating the same result set, which can
skip records. Use recompute_normalized_names.py for a full refresh, or
repair_null_normalized_names.py for NULL-only repair.
"""


def main():
    print(
        "Deprecated: use recompute_normalized_names.py or repair_null_normalized_names.py instead."
    )


if __name__ == "__main__":
    main()
