"""Create local authentication and explicit demo configuration without cloud access."""
from getpass import getpass
from pathlib import Path
import os
import bcrypt


def main():
    root = Path(__file__).resolve().parents[1]
    secrets = root / '.secrets'
    if secrets.is_symlink():
        raise SystemExit('The secrets directory must not be a symbolic link.')
    secrets.mkdir(mode=0o700, exist_ok=True)
    secrets.chmod(0o700)
    for name in ('access_password_hash', 'llm_api_key'):
        if (secrets / name).is_symlink():
            raise SystemExit('Secret files must not be symbolic links.')
    hash_path = secrets / 'access_password_hash'
    if not hash_path.exists():
        password = getpass('Choose an application password (at least 12 characters): ')
        if len(password) < 12 or len(password.encode('utf-8')) > 72:
            raise SystemExit('Use at least 12 characters and at most 72 UTF-8 bytes.')
        if password != getpass('Confirm password: '):
            raise SystemExit('Passwords did not match. No configuration was written.')
        fd = os.open(hash_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as target:
            target.write(bcrypt.hashpw(password.encode(), bcrypt.gensalt()))
    key_path = secrets / 'llm_api_key'
    if not key_path.exists():
        key_path.touch(mode=0o600)
    # The private parent protects host access; individual mounts must be readable
    # by the container's nonroot user on native Linux.
    hash_path.chmod(0o644)
    key_path.chmod(0o644)
    env_path = root / '.env'
    if not env_path.exists():
        with env_path.open('x') as target:
            target.write((root / '.env.example').read_text())
        env_path.chmod(0o600)
    print('Local configuration is ready. Existing secrets and settings were preserved.')
    print('Demo mode makes no model calls. Its labeled output is for trying the workflow.')
    print('To analyze comments, configure a provider, model and budget in .env first.')


if __name__ == '__main__':
    main()
