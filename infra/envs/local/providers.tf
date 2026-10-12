# Points the AWS provider at the local Floci emulator instead of real AWS.
# The credentials are fake on purpose: Floci accepts any non-empty values, and
# hard-coding them here means your real AWS credentials are never used.
provider "aws" {
  region     = "us-east-1"
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    cloudwatch     = var.emulator_endpoint
    cloudwatchlogs = var.emulator_endpoint
    ec2            = var.emulator_endpoint
    ecs            = var.emulator_endpoint
    iam            = var.emulator_endpoint
    sns            = var.emulator_endpoint
    sts            = var.emulator_endpoint
  }
}
