import os
import tempfile

# A fixed instance secret, so seeds and flags are the same in every test run and nothing writes the repo's own.
os.environ.setdefault("SILVERLAKE_INSTANCE_SECRET", "test-instance-secret")

# No certificate unless a test makes one, so the TLS ports only start when a test asks for them and the repo's own
# .tls/ never leaks in.
os.environ.setdefault("SILVERLAKE_TLS_DIR", os.path.join(tempfile.mkdtemp(prefix="silverlake-tls-"), "none"))
