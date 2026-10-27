import os

# A fixed instance secret, so seeds and flags are the same in every test run and nothing writes the repo's own.
os.environ.setdefault("SILVERLAKE_INSTANCE_SECRET", "test-instance-secret")
