# Source this file (do not run it) to point the AWS CLI at the local Floci emulator.
# It only affects the terminal you source it in.
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
unset AWS_PROFILE AWS_SESSION_TOKEN
echo "AWS CLI in this terminal now talks to $AWS_ENDPOINT_URL (Floci), not real AWS."