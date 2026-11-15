# AWS setup (S3 landing zone), about 20 minutes, free tier

1. **Create a bucket.** S3 → Create bucket → name e.g. `shessols-psx-data`, region `ap-south-1` (Mumbai). Keep "Block all public access" ON.
2. **Put the name in `config.yaml`:** `storage.s3_bucket`, and set `storage.mode: s3`.
3. **A user for the pipeline.** IAM → Users → Create `psx-pipeline`. Attach an inline policy allowing `s3:PutObject` and `s3:ListBucket` on your bucket only. Create an access key, then on your laptop run `aws configure`.
4. **A role for Snowflake to read the bucket.** IAM → Roles → Create role → "AWS account" → this account, tick "Require external ID" (put `0000` for now). Attach an inline policy: `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucket` on the bucket. Name it `snowflake-psx-reader`.
5. **Connect Snowflake.** Run `snowflake/02_s3_stage.sql` with your account ID and bucket. `DESC INTEGRATION` shows `STORAGE_AWS_IAM_USER_ARN` and `STORAGE_AWS_EXTERNAL_ID`. Put both in the role's **Trust relationships** (Principal = the ARN, `sts:ExternalId` = the external ID).
6. **Test.** `python ingest/upload_s3.py --all`, then `LIST @PSX.RAW.S3_LANDING/prices/;` in Snowflake.

Later (optional): move `extract_psx.py` + `upload_s3.py` into an AWS Lambda triggered by EventBridge at 18:00 PKT, so it runs without your laptop.
