-- Only needed when storage.mode = s3. Run once, as ACCOUNTADMIN.
-- Step-by-step AWS side: docs/aws_setup.md

-- 1. Let Snowflake read your bucket through an IAM role (no keys stored)
CREATE STORAGE INTEGRATION IF NOT EXISTS PSX_S3_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::<your-account-id>:role/snowflake-psx-reader'
  STORAGE_ALLOWED_LOCATIONS = ('s3://your-psx-bucket/psx/');

-- Copy STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID from this
-- into the IAM role's trust policy in AWS:
DESC INTEGRATION PSX_S3_INT;

-- 2. File format + stage
CREATE FILE FORMAT IF NOT EXISTS PSX.RAW.PARQUET_FMT TYPE = PARQUET;

CREATE STAGE IF NOT EXISTS PSX.RAW.S3_LANDING
  STORAGE_INTEGRATION = PSX_S3_INT
  URL = 's3://your-psx-bucket/psx/'
  FILE_FORMAT = PSX.RAW.PARQUET_FMT;

-- 3. Check you can see the files
LIST @PSX.RAW.S3_LANDING/prices/;
