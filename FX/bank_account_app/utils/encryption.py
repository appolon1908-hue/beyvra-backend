from cryptography.fernet import Fernet
import base64
from django.conf import settings

def generate_key():
    return base64.urlsafe_b64encode(Fernet.generate_key())

def get_cipher():
    return Fernet(settings.ENCRYPTION_KEY)

def encrypt_data(data: str) -> str:
    cipher = get_cipher()
    encrypted_data = cipher.encrypt(data.encode())
    return encrypted_data.decode()

def decrypt_data(encrypted_data: str) -> str:
    cipher = get_cipher()
    decrypted_data = cipher.decrypt(encrypted_data.encode())
    return decrypted_data.decode()
