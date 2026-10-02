"""Upload TradingAgents results to Backblaze B2 (S3-compatible API).

B2 requires four env vars:
  B2_KEY_ID          - Application Key ID  (not the account ID)
  B2_APPLICATION_KEY - Application Key secret
  B2_BUCKET_NAME     - Name of your B2 bucket
  B2_ENDPOINT_URL    - e.g. https://s3.us-west-004.backblazeb2.com
                       (find it in B2 > Buckets > Endpoint)

Files are stored under:
  tradingagents/{ticker}/{date}/...
"""

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def get_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: environment variable {name!r} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def upload_directory(
    local_dir: Path,
    bucket: str,
    prefix: str,
    s3_client,
) -> int:
    """Recursively upload *local_dir* to B2 under *prefix*. Returns file count."""
    count = 0
    for file_path in sorted(local_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(local_dir)
        key = f"{prefix}/{relative}".replace("\\", "/")
        print(f"  uploading {file_path} -> s3://{bucket}/{key}")
        try:
            s3_client.upload_file(str(file_path), bucket, key)
            count += 1
        except (BotoCoreError, ClientError) as exc:
            print(f"  WARNING: failed to upload {file_path}: {exc}", file=sys.stderr)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload results to Backblaze B2")
    parser.add_argument("--results-dir", required=True, help="Local results directory")
    parser.add_argument("--ticker",      required=True, help="Ticker that was analyzed")
    parser.add_argument("--date",        required=True, help="Analysis date YYYY-MM-DD")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"WARNING: results directory {results_dir} does not exist; nothing to upload.")
        sys.exit(0)

    key_id          = get_env("B2_KEY_ID")
    application_key = get_env("B2_APPLICATION_KEY")
    bucket_name     = get_env("B2_BUCKET_NAME")
    endpoint_url    = get_env("B2_ENDPOINT_URL")

    # B2 S3-compatible endpoint — no AWS SigV4 quirks needed
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
    )

    # Safe path component: replace characters that are bad in S3 keys
    safe_ticker = args.ticker.replace("/", "_").replace("\\", "_")
    prefix = f"tradingagents/{safe_ticker}/{args.date}"

    # The CLI writes per-ticker subdirs; upload everything under results_dir
    run_dir = results_dir / safe_ticker / args.date
    upload_root = run_dir if run_dir.exists() else results_dir

    print(f"Uploading {upload_root} to B2 bucket {bucket_name!r} under prefix {prefix!r}")
    count = upload_directory(upload_root, bucket_name, prefix, s3)

    if count == 0:
        print("WARNING: no files were uploaded (directory may be empty).", file=sys.stderr)
    else:
        print(f"Done — {count} file(s) uploaded to B2.")
        print(f"Browse: {endpoint_url.rstrip('/')}/{bucket_name}/{prefix}/")


if __name__ == "__main__":
    main()
