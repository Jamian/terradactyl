import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from django.conf import settings
from django.db.models import CharField


class EncryptedCharField(CharField):
    """Custom Encrypted CharField
    Requires that both ENCRYPTED_CHAR_FIELD_SALT and ENCRYPTED_CHAR_FIELD_KEY
    are set in the settings file.
    """

    salt = bytes(settings.ENCRYPTED_CHAR_FIELD_SALT, encoding="raw_unicode_escape")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), 
                    length=32, 
                    salt=salt, 
                    iterations=100000, 
                    backend=default_backend())

    key = base64.urlsafe_b64encode(kdf.derive(settings.ENCRYPTED_CHAR_FIELD_KEY.encode('utf-8')))
    f = Fernet(key)

    def from_db_value(self, value, expression, connection):
        return self.f.decrypt(value).decode('utf-8')

    def get_prep_value(self, value):
        return self.f.encrypt(value.encode('utf-8'))