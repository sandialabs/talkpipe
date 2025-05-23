"""Signature operations for TalkPipe.

This module provides segments for signing operations including key generation,
digital signatures, and signature verification.
"""

import os
import logging
import argparse
import json
import base64
from typing import Optional, Tuple, Union, Iterable, Iterator, Any, List

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key, 
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
    BestAvailableEncryption
)

from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.data_manipulation import extract_property

logger = logging.getLogger(__name__)

def generate_key_pair(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """Generate a public/private key pair for digital signatures.
    
    Args:
        key_size (int): Size of the RSA key in bits. Default is 2048.
        
    Returns:
        rsa.RSAPrivateKey: a private key, from which the public key can be extracted.
    """
    logger.info(f"Generating RSA key pair with size {key_size} bits")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size
    )
    
    return private_key

def pem_encode_key(key: rsa.RSAPrivateKey, password: Optional[Union[bytes, str]] = None) -> Tuple[bytes, bytes]:
    """Encode a private key to PEM format.
    
    Args:
        key (rsa.RSAPrivateKey): RSA private key object
        password (Optional[Union[bytes, str]]): Password for encryption. If None, no encryption is applied.
        
    Returns:
        Tuple[bytes, bytes]: PEM-encoded private and public keys.
    """
    logger.info("Encoding private key to PEM format")
    password_bytes = password.encode('utf-8') if isinstance(password, str) else password
    private_pem = key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption() if password_bytes is None else BestAvailableEncryption(password_bytes)
    )
    public_pem = key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem, public_pem

def save_key_pair(private_key: bytes, public_key: bytes, 
                  private_path: str = "private_key.pem", 
                  public_path: str = "public_key.pem") -> None:
    """Save a key pair to files.
    
    Args:
        private_key (bytes): PEM-encoded private key
        public_key (bytes): PEM-encoded public key
        private_path (str): Path to save the private key
        public_path (str): Path to save the public key
    """
    logger.info(f"Saving private key to {private_path}")
    with open(private_path, "wb") as f:
        f.write(private_key)
    
    logger.info(f"Saving public key to {public_path}")
    with open(public_path, "wb") as f:
        f.write(public_key)

def acquire_private_key(key: Union[rsa.RSAPrivateKey, bytes, str], password: Optional[Union[str, bytes]]=None) -> rsa.RSAPrivateKey:
    """Acquire a private key from various formats.
    
    Args:
        key: RSA private key or path to PEM file or PEM content
        password: Password to decrypt the private key, if encrypted
        
    Returns:
        rsa.RSAPrivateKey: Loaded private key
        
    Raises:
        ValueError: If there's an issue with the key
    """
    password_bytes = password.encode('utf-8') if isinstance(password, str) else password
    if isinstance(key, str):
        if os.path.exists(key):
            logger.info(f"Loading private key from file: {key}")
            with open(key, "rb") as f:
                private_key_data = f.read()
            return load_pem_private_key(private_key_data, password=password_bytes)
        else:
            logger.info("Loading private key from PEM string")
            return load_pem_private_key(key.encode('utf-8'), password=password_bytes)
    elif isinstance(key, bytes):
        logger.info("Loading private key from PEM bytes")
        return load_pem_private_key(key, password=password_bytes)
    elif isinstance(key, rsa.RSAPrivateKey):
        logger.info("Using provided private key object")
        return key
    else:
        logger.error("Invalid key format")
        raise ValueError("Key must be a PEM file path, PEM content, or RSAPrivateKey object")
    
def acquire_public_key(key: Union[rsa.RSAPublicKey, rsa.RSAPrivateKey, bytes, str]) -> rsa.RSAPublicKey:
    """Acquire a public key from various formats.
    
    Args:
        key: RSA public key or path to PEM file or PEM content
        
    Returns:
        rsa.RSAPublicKey: Loaded public key
        
    Raises:
        ValueError: If there's an issue with the key
    """
    if isinstance(key, str):
        if os.path.exists(key):
            logger.info(f"Loading public key from file: {key}")
            with open(key, "rb") as f:
                public_key_data = f.read()
            return load_pem_public_key(public_key_data)
        else:
            logger.info("Loading public key from PEM string")
            return load_pem_public_key(key.encode('utf-8'))
    elif isinstance(key, bytes):
        logger.info("Loading public key from PEM bytes")
        return load_pem_public_key(key)
    elif isinstance(key, rsa.RSAPublicKey):
        logger.info("Using provided public key object")
        return key
    elif isinstance(key, rsa.RSAPrivateKey):
        logger.info("Using public key from provided private key object")
        return key.public_key()
    else:
        logger.error("Invalid key format")
        raise ValueError("Key must be a PEM file path, PEM content, RSAPrivateKey, or RSAPublicKey object")

def load_key_pair_from_file(private_path: str = "private_key.pem", 
                 public_path: str = "public_key.pem",
                 password: Optional[bytes] = None) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Load a key pair from files.
    
    Args:
        private_path (str): Path to the private key file
        public_path (str): Path to the public key file
        password (bytes, optional): Password to decrypt the private key, if encrypted
        
    Returns:
        Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]: Loaded private and public keys
        
    Raises:
        FileNotFoundError: If the key files don't exist
        ValueError: If there's an issue loading the keys
    """
    private_key = acquire_private_key(private_path, password)
    public_key = acquire_public_key(public_path)
    return private_key, public_key

def serialize_for_signing(data):
    """Serialize data deterministically for signing."""
    if isinstance(data, bytes):
        return data
    elif isinstance(data, str):
        return data.encode('utf-8')
    else:
        try:
            # Use canonical JSON (sorted keys, no whitespace)
            json_str = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            return json_str.encode('utf-8')
        except TypeError as e:
            logger.error(f"Failed to serialize data for signing: {e}")
            raise ValueError("Data must be bytes, string, or JSON-serializable object") from e


def sign_message(private_key: Union[rsa.RSAPrivateKey, bytes, str], 
                message: Any) -> bytes:
    """Sign a message using RSA-PSS with SHA-256.
    
    Args:
        private_key: RSA private key or path to PEM file or PEM content
        message: Message to sign (will be encoded to bytes if it's a string)
        
    Returns:
        bytes: Digital signature
        
    Raises:
        ValueError: If there's an issue with the key or message
    """
    # Convert message to bytes if needed
    if not isinstance(message, bytes):
        logger.info(f"Message is {type(message)}, not bytes, converting to json")
        message = serialize_for_signing(message)
    
    # Load private key if it's a file path or PEM content
    key = acquire_private_key(private_key)
        
    logger.info(f"Signing message of length {len(message)} bytes")
    signature = key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return signature

def verify_signature(public_key: Union[rsa.RSAPublicKey, bytes, str], 
                    message: Union[bytes, str], 
                    signature: bytes) -> bool:
    """Verify a digital signature using RSA-PSS with SHA-256.
    
    Args:
        public_key: RSA public key or path to PEM file or PEM content
        message: Original message (will be encoded to bytes if it's a string)
        signature: Digital signature to verify
        
    Returns:
        bool: True if the signature is valid, False otherwise
    """
    # Convert message to bytes if needed
    if not isinstance(message, bytes):
        logger.info(f"Message is {type(message)}, not bytes, converting to json")
        message = serialize_for_signing(message)
    
    # Load public key if it's a file path or PEM content
    key = acquire_public_key(public_key)
    
    try:
        logger.info(f"Verifying signature of length {len(signature)} bytes")
        key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        logger.info("Signature verified successfully")
        return True
    except Exception as e:
        logger.warning(f"Signature verification failed: {e}")
        return False

@registry.register_segment("sign")
class SignSegment(core.AbstractSegment):
    """
    Sign items using a private key.
    
    This segment signs each item in the input stream using RSA-PSS with SHA-256.
    """
    
    def __init__(self, private_key, message_field="_", password=None,
                 append_as=None, encode_signature=True):
        """
        Initialize the sign segment.
        
        Args:
            private_key: Private key path, PEM content, or RSAPrivateKey object
            message_field (str): Field containing the message to sign. Defaults to "_" (the whole item)
            password: Password for encrypted private key
            append_as (str): Field to store the signature in. If None, returns just the signature
            encode_signature (bool): Whether to base64-encode the signature
        
        Raises:
            ValueError: If invalid parameters are provided
        """
        super().__init__()
        if message_field == "_" and append_as is not None:
            raise ValueError("The message_field cannot be '_' if append_as is specified, because appending the signature would change the signature of the data. Choose a field to sign.")
        
        self.private_key_actual = acquire_private_key(private_key, password=password)
        self.message_field = message_field
        self.append_as = append_as
        self.encode_signature = encode_signature
        
    def process_item(self, item):
        """Process a single item by signing it.
        
        Args:
            item: The item to sign
            
        Returns:
            The item with signature added or just the signature
        """
        try:
            # Get the message to sign
            message = extract_property(item, self.message_field, fail_on_missing=True)
            
            # Sign the message
            signature = sign_message(self.private_key_actual, message)

            if self.encode_signature:
                signature = base64.b64encode(signature).decode('utf-8')
            
            # Return signature or append to item
            if self.append_as is None:
                return signature
            else:
                item[self.append_as] = signature
                return item
            
        except Exception as e:
            error_msg = f"Failed to sign item: {e}"
            logger.error(error_msg)
            raise e
    
    def transform(self, input_iter):
        """Process a stream of items.
        
        Args:
            input_iter: An iterable of items to process
            
        Yields:
            Processed items with signatures
        """
        for item in input_iter:
            yield self.process_item(item)

@registry.register_segment("verify")
class VerifySegment(core.AbstractSegment):
    """
    Verify signatures on items using a public key.
    
    This segment verifies the signature on each item in the input stream using RSA-PSS with SHA-256.
    """
    
    def __init__(self, public_key, message_field="_", 
                 signature_field="signature", append_as=None):
        """
        Initialize the verify segment.
        
        Args:
            public_key: Public key path, PEM content, or RSAPublicKey object
            message_field (str): Field containing the original message. Defaults to "_" (the whole item)
            signature_field (str): Field containing the signature. Defaults to "signature"
            append_as (str): Field to store the verification result in. If None, returns just the result
        
        Raises:
            ValueError: If invalid parameters are provided
        """
        super().__init__()
        if message_field == "_" and signature_field is not None:
            raise ValueError("The message_field cannot be '_' because it would make the signature part of the thing being verified.")

        self.public_key_actual = acquire_public_key(public_key)
        self.message_field = message_field
        self.signature_field = signature_field
        self.append_as = append_as
        
    def process_item(self, item):
        """Process a single item by verifying its signature.
        
        Args:
            item: The item to verify
            
        Returns:
            The item with verification result added or just the result
        """
        try:
            message = extract_property(item, self.message_field, fail_on_missing=True)
            signature = extract_property(item, self.signature_field, fail_on_missing=True)
            
            if isinstance(signature, str):
                # Assume base64 encoding if it's a string
                signature = base64.b64decode(signature)
            elif not isinstance(signature, bytes):
                raise ValueError(f"Signature must be bytes or base64 string, got {type(signature)}")            
            
            # Verify the signature
            verified = verify_signature(self.public_key_actual, message, signature)
            
            # Return result or append to item
            if self.append_as is None:
                return verified
            else:
                item[self.append_as] = verified
                return item
                
        except Exception as e:
            error_msg = f"Failed to verify item: {e}"
            logger.error(error_msg)
            if self.append_as is not None:
                item[self.append_as] = False
                return item
            else:
                return False
    
    def transform(self, input_iter):
        """Process a stream of items.
        
        Args:
            input_iter: An iterable of items to process
            
        Yields:
            Processed items with verification results
        """
        for item in input_iter:
            yield self.process_item(item)


def generate_keys_cli():
    """Command-line interface for generating and saving RSA key pairs."""
    
    parser = argparse.ArgumentParser(description="Generate RSA key pair for digital signatures")
    parser.add_argument("--key-size", type=int, default=2048, 
                        help="Size of the RSA key in bits")
    parser.add_argument("--private-key", type=str, default="private_key.pem",
                        help="Path to save the private key")
    parser.add_argument("--public-key", type=str, default="public_key.pem",
                        help="Path to save the public key")
    
    args = parser.parse_args()
    
    print(f"Generating RSA key pair with size {args.key_size} bits...")
    private_key_obj = generate_key_pair(key_size=args.key_size)
    private_key, public_key = pem_encode_key(private_key_obj)
    
    print(f"Saving private key to {args.private_key}")
    with open(args.private_key, "wb") as f:
        f.write(private_key)
    
    print(f"Saving public key to {args.public_key}")
    with open(args.public_key, "wb") as f:
        f.write(public_key)
    
    print("Key pair generated and saved successfully!")

if __name__ == "__main__":
    generate_keys_cli()