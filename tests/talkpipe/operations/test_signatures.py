"""Unit tests for the signatures module.

Tests cover key generation, serialization, signing, verification, and the segments.
"""

import pytest
import os
import tempfile
import json
import base64
from unittest.mock import patch, mock_open

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption
)

# Import the module under test
from talkpipe.operations.signatures import (
    generate_key_pair,
    pem_encode_key,
    save_key_pair,
    acquire_private_key,
    acquire_public_key,
    load_key_pair_from_file,
    serialize_for_signing,
    sign_message,
    verify_signature,
    SignSegment,
    VerifySegment,
    generate_keys_cli
)


class TestKeyGeneration:
    """Test key generation and encoding functionality."""
    
    def test_generate_key_pair_default(self):
        """Test generating a key pair with default parameters."""
        private_key = generate_key_pair()
        assert isinstance(private_key, rsa.RSAPrivateKey)
        assert private_key.key_size == 2048
        
    def test_generate_key_pair_custom_size(self):
        """Test generating a key pair with custom key size."""
        private_key = generate_key_pair(key_size=1024)
        assert isinstance(private_key, rsa.RSAPrivateKey)
        assert private_key.key_size == 1024
        
    def test_pem_encode_key_no_password(self):
        """Test encoding keys to PEM format without password."""
        private_key = generate_key_pair(key_size=1024)  # Smaller for faster tests
        private_pem, public_pem = pem_encode_key(private_key)
        
        assert isinstance(private_pem, bytes)
        assert isinstance(public_pem, bytes)
        assert b'BEGIN PRIVATE KEY' in private_pem
        assert b'BEGIN PUBLIC KEY' in public_pem
        
    def test_pem_encode_key_with_password(self):
        """Test encoding keys to PEM format with password."""
        private_key = generate_key_pair(key_size=1024)
        password = "test_password"
        private_pem, public_pem = pem_encode_key(private_key, password)
        
        assert isinstance(private_pem, bytes)
        assert isinstance(public_pem, bytes)
        assert b'BEGIN ENCRYPTED PRIVATE KEY' in private_pem
        assert b'BEGIN PUBLIC KEY' in public_pem
        
    def test_pem_encode_key_with_bytes_password(self):
        """Test encoding keys to PEM format with bytes password."""
        private_key = generate_key_pair(key_size=1024)
        password = b"test_password"
        private_pem, public_pem = pem_encode_key(private_key, password)
        
        assert isinstance(private_pem, bytes)
        assert isinstance(public_pem, bytes)
        assert b'BEGIN ENCRYPTED PRIVATE KEY' in private_pem


class TestKeySaving:
    """Test key saving and loading functionality."""
    
    def test_save_key_pair(self, tmp_path):
        """Test saving key pair to files."""
        private_key = generate_key_pair(key_size=1024)
        private_pem, public_pem = pem_encode_key(private_key)
        
        private_path = tmp_path / "test_private.pem"
        public_path = tmp_path / "test_public.pem"
        
        save_key_pair(private_pem, public_pem, str(private_path), str(public_path))
        
        assert private_path.exists()
        assert public_path.exists()
        
        # Verify content
        with open(private_path, "rb") as f:
            saved_private = f.read()
        with open(public_path, "rb") as f:
            saved_public = f.read()
            
        assert saved_private == private_pem
        assert saved_public == public_pem


class TestKeyAcquisition:
    """Test key acquisition from various formats."""
    
    def test_acquire_private_key_from_object(self):
        """Test acquiring private key from RSAPrivateKey object."""
        original_key = generate_key_pair(key_size=1024)
        acquired_key = acquire_private_key(original_key)
        assert acquired_key is original_key
        
    def test_acquire_private_key_from_bytes(self):
        """Test acquiring private key from PEM bytes."""
        original_key = generate_key_pair(key_size=1024)
        private_pem, _ = pem_encode_key(original_key)
        
        acquired_key = acquire_private_key(private_pem)
        assert isinstance(acquired_key, rsa.RSAPrivateKey)
        assert acquired_key.key_size == 1024
        
    def test_acquire_private_key_from_string(self):
        """Test acquiring private key from PEM string."""
        original_key = generate_key_pair(key_size=1024)
        private_pem, _ = pem_encode_key(original_key)
        
        acquired_key = acquire_private_key(private_pem.decode('utf-8'))
        assert isinstance(acquired_key, rsa.RSAPrivateKey)
        assert acquired_key.key_size == 1024
        
    def test_acquire_private_key_from_file(self, tmp_path):
        """Test acquiring private key from file path."""
        original_key = generate_key_pair(key_size=1024)
        private_pem, _ = pem_encode_key(original_key)
        
        key_file = tmp_path / "private_key.pem"
        with open(key_file, "wb") as f:
            f.write(private_pem)
            
        acquired_key = acquire_private_key(str(key_file))
        assert isinstance(acquired_key, rsa.RSAPrivateKey)
        assert acquired_key.key_size == 1024
        
    def test_acquire_private_key_with_password(self, tmp_path):
        """Test acquiring encrypted private key with password."""
        original_key = generate_key_pair(key_size=1024)
        password = "test_password"
        private_pem, _ = pem_encode_key(original_key, password)
        
        key_file = tmp_path / "private_key.pem"
        with open(key_file, "wb") as f:
            f.write(private_pem)
            
        acquired_key = acquire_private_key(str(key_file), password=password)
        assert isinstance(acquired_key, rsa.RSAPrivateKey)
        assert acquired_key.key_size == 1024
        
    def test_acquire_private_key_invalid_format(self):
        """Test acquiring private key with invalid format."""
        with pytest.raises(ValueError, match="Key must be a PEM file path"):
            acquire_private_key(123)
            
    def test_acquire_public_key_from_object(self):
        """Test acquiring public key from RSAPublicKey object."""
        private_key = generate_key_pair(key_size=1024)
        original_public = private_key.public_key()
        
        acquired_key = acquire_public_key(original_public)
        assert acquired_key is original_public
        
    def test_acquire_public_key_from_private_key(self):
        """Test acquiring public key from RSAPrivateKey object."""
        private_key = generate_key_pair(key_size=1024)
        
        acquired_key = acquire_public_key(private_key)
        assert isinstance(acquired_key, rsa.RSAPublicKey)
        
    def test_acquire_public_key_from_bytes(self):
        """Test acquiring public key from PEM bytes."""
        private_key = generate_key_pair(key_size=1024)
        _, public_pem = pem_encode_key(private_key)
        
        acquired_key = acquire_public_key(public_pem)
        assert isinstance(acquired_key, rsa.RSAPublicKey)
        
    def test_acquire_public_key_from_string(self):
        """Test acquiring public key from PEM string."""
        private_key = generate_key_pair(key_size=1024)
        _, public_pem = pem_encode_key(private_key)
        
        acquired_key = acquire_public_key(public_pem.decode('utf-8'))
        assert isinstance(acquired_key, rsa.RSAPublicKey)
        
    def test_acquire_public_key_from_file(self, tmp_path):
        """Test acquiring public key from file path."""
        private_key = generate_key_pair(key_size=1024)
        _, public_pem = pem_encode_key(private_key)
        
        key_file = tmp_path / "public_key.pem"
        with open(key_file, "wb") as f:
            f.write(public_pem)
            
        acquired_key = acquire_public_key(str(key_file))
        assert isinstance(acquired_key, rsa.RSAPublicKey)
        
    def test_acquire_public_key_invalid_format(self):
        """Test acquiring public key with invalid format."""
        with pytest.raises(ValueError, match="Key must be a PEM file path"):
            acquire_public_key(123)


class TestLoadKeyPairFromFile:
    """Test loading key pairs from files."""
    
    def test_load_key_pair_from_file(self, tmp_path):
        """Test loading key pair from files."""
        original_private = generate_key_pair(key_size=1024)
        private_pem, public_pem = pem_encode_key(original_private)
        
        private_path = tmp_path / "private_key.pem"
        public_path = tmp_path / "public_key.pem"
        
        with open(private_path, "wb") as f:
            f.write(private_pem)
        with open(public_path, "wb") as f:
            f.write(public_pem)
            
        private_key, public_key = load_key_pair_from_file(
            str(private_path), str(public_path)
        )
        
        assert isinstance(private_key, rsa.RSAPrivateKey)
        assert isinstance(public_key, rsa.RSAPublicKey)
        assert private_key.key_size == 1024


class TestSerialization:
    """Test data serialization for signing."""
    
    def test_serialize_bytes(self):
        """Test serializing bytes data."""
        data = b"test bytes"
        result = serialize_for_signing(data)
        assert result == data
        
    def test_serialize_string(self):
        """Test serializing string data."""
        data = "test string"
        result = serialize_for_signing(data)
        assert result == data.encode('utf-8')
        
    def test_serialize_dict(self):
        """Test serializing dictionary data."""
        data = {"key": "value", "number": 42}
        result = serialize_for_signing(data)
        expected = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
        assert result == expected
        
    def test_serialize_list(self):
        """Test serializing list data."""
        data = [1, 2, "three"]
        result = serialize_for_signing(data)
        expected = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
        assert result == expected
        
    def test_serialize_non_serializable(self):
        """Test serializing non-JSON-serializable data."""
        class CustomObject:
            pass
            
        data = CustomObject()
        with pytest.raises(ValueError, match="Data must be bytes, string, or JSON-serializable"):
            serialize_for_signing(data)


class TestSigningAndVerification:
    """Test signing and verification functionality."""
    
    @pytest.fixture
    def key_pair(self):
        """Generate a key pair for testing."""
        private_key = generate_key_pair(key_size=1024)
        public_key = private_key.public_key()
        return private_key, public_key
        
    def test_sign_and_verify_bytes(self, key_pair):
        """Test signing and verifying bytes data."""
        private_key, public_key = key_pair
        message = b"test message"
        
        signature = sign_message(private_key, message)
        assert isinstance(signature, bytes)
        
        verified = verify_signature(public_key, message, signature)
        assert verified is True
        
    def test_sign_and_verify_string(self, key_pair):
        """Test signing and verifying string data."""
        private_key, public_key = key_pair
        message = "test message"
        
        signature = sign_message(private_key, message)
        assert isinstance(signature, bytes)
        
        verified = verify_signature(public_key, message, signature)
        assert verified is True
        
    def test_sign_and_verify_dict(self, key_pair):
        """Test signing and verifying dictionary data."""
        private_key, public_key = key_pair
        message = {"key": "value", "number": 42}
        
        signature = sign_message(private_key, message)
        assert isinstance(signature, bytes)
        
        verified = verify_signature(public_key, message, signature)
        assert verified is True
        
    def test_verify_invalid_signature(self, key_pair):
        """Test verifying with invalid signature."""
        private_key, public_key = key_pair
        message = b"test message"
        
        # Create a valid signature
        signature = sign_message(private_key, message)
        
        # Modify the signature to make it invalid
        invalid_signature = signature[:-1] + b'\x00'
        
        verified = verify_signature(public_key, message, invalid_signature)
        assert verified is False
        
    def test_verify_wrong_message(self, key_pair):
        """Test verifying with wrong message."""
        private_key, public_key = key_pair
        original_message = b"original message"
        wrong_message = b"wrong message"
        
        signature = sign_message(private_key, original_message)
        
        verified = verify_signature(public_key, wrong_message, signature)
        assert verified is False
        
    def test_sign_with_pem_key(self, key_pair):
        """Test signing with PEM-encoded key."""
        private_key, public_key = key_pair
        private_pem, _ = pem_encode_key(private_key)
        message = b"test message"
        
        signature = sign_message(private_pem, message)
        verified = verify_signature(public_key, message, signature)
        assert verified is True


class TestSignSegment:
    """Test the SignSegment class."""
    
    @pytest.fixture
    def key_pair(self):
        """Generate a key pair for testing."""
        private_key = generate_key_pair(key_size=1024)
        public_key = private_key.public_key()
        return private_key, public_key
        
    def test_sign_segment_init_validation(self, key_pair):
        """Test SignSegment initialization validation."""
        private_key, _ = key_pair
        
        # This should raise an error - can't use "_" with append_as
        with pytest.raises(ValueError, match="The message_field cannot be '_'"):
            SignSegment(private_key, message_field="_", append_as="signature")
            
    def test_sign_segment_basic(self, key_pair):
        """Test basic SignSegment functionality."""
        private_key, _ = key_pair
        
        segment = SignSegment(private_key, message_field="data")
        items = [{"data": "message1"}, {"data": "message2"}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 2
        for result in results:
            assert isinstance(result, str)  # Base64-encoded signature
            
    def test_sign_segment_append_as(self, key_pair):
        """Test SignSegment with append_as parameter."""
        private_key, _ = key_pair
        
        segment = SignSegment(private_key, message_field="data", append_as="signature")
        items = [{"data": "message1", "id": 1}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        result = results[0]
        assert "signature" in result
        assert result["id"] == 1
        assert result["data"] == "message1"
        assert isinstance(result["signature"], str)
        
    def test_sign_segment_no_encoding(self, key_pair):
        """Test SignSegment without base64 encoding."""
        private_key, _ = key_pair
        
        segment = SignSegment(private_key, message_field="data", encode_signature=False)
        items = [{"data": "message1"}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, bytes)
        
    def test_sign_segment_whole_item(self, key_pair):
        """Test SignSegment signing the whole item."""
        private_key, _ = key_pair
        
        segment = SignSegment(private_key, message_field="_")
        items = [{"data": "message1", "id": 1}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, str)  # Base64-encoded signature
        
    def test_sign_segment_with_password(self, tmp_path):
        """Test SignSegment with password-protected key."""
        private_key = generate_key_pair(key_size=1024)
        password = "test_password"
        private_pem, _ = pem_encode_key(private_key, password)
        
        key_file = tmp_path / "private_key.pem"
        with open(key_file, "wb") as f:
            f.write(private_pem)
            
        segment = SignSegment(str(key_file), password=password, message_field="data")
        items = [{"data": "message1"}]
        
        results = list(segment.transform(items))
        assert len(results) == 1
        assert isinstance(results[0], str)


class TestVerifySegment:
    """Test the VerifySegment class."""
    
    @pytest.fixture
    def key_pair(self):
        """Generate a key pair for testing."""
        private_key = generate_key_pair(key_size=1024)
        public_key = private_key.public_key()
        return private_key, public_key
        
    def test_verify_segment_init_validation(self, key_pair):
        """Test VerifySegment initialization validation."""
        _, public_key = key_pair
        
        # This should raise an error - can't use "_" with signature_field
        with pytest.raises(ValueError, match="The message_field cannot be '_'"):
            VerifySegment(public_key, message_field="_", signature_field="signature")
            
    def test_verify_segment_basic(self, key_pair):
        """Test basic VerifySegment functionality."""
        private_key, public_key = key_pair
        
        # First create a signed message
        message = "test message"
        signature = sign_message(private_key, message)
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        segment = VerifySegment(public_key, message_field="data", signature_field="sig")
        items = [{"data": message, "sig": signature_b64}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        assert results[0] is True
        
    def test_verify_segment_append_as(self, key_pair):
        """Test VerifySegment with append_as parameter."""
        private_key, public_key = key_pair
        
        message = "test message"
        signature = sign_message(private_key, message)
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        segment = VerifySegment(
            public_key, 
            message_field="data", 
            signature_field="sig",
            append_as="verified"
        )
        items = [{"data": message, "sig": signature_b64, "id": 1}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        result = results[0]
        assert result["verified"] is True
        assert result["id"] == 1
        assert result["data"] == message
        
    def test_verify_segment_invalid_signature(self, key_pair):
        """Test VerifySegment with invalid signature."""
        _, public_key = key_pair
        
        segment = VerifySegment(public_key, message_field="data", signature_field="sig")
        items = [{"data": "test message", "sig": "invalid_signature"}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        assert results[0] is False
        
    def test_verify_segment_bytes_signature(self, key_pair):
        """Test VerifySegment with bytes signature."""
        private_key, public_key = key_pair
        
        message = "test message"
        signature = sign_message(private_key, message)
        
        segment = VerifySegment(public_key, message_field="data", signature_field="sig")
        items = [{"data": message, "sig": signature}]
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        assert results[0] is True
        
    def test_verify_segment_wrong_signature_type(self, key_pair):
        """Test VerifySegment with wrong signature type."""
        _, public_key = key_pair
        
        segment = VerifySegment(
            public_key, 
            message_field="data", 
            signature_field="sig",
            append_as="verified"
        )
        items = [{"data": "test message", "sig": 123}]  # Wrong type
        
        results = list(segment.transform(items))
        
        assert len(results) == 1
        assert results[0]["verified"] is False


class TestCLI:
    """Test the command-line interface."""
    
    @patch('sys.argv', ['script', '--key-size', '1024', 
                        '--private-key', 'test_private.pem',
                        '--public-key', 'test_public.pem'])
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_generate_keys_cli(self, mock_print, mock_file):
        """Test the CLI key generation function."""
        generate_keys_cli()
        
        # Verify print statements
        mock_print.assert_any_call("Generating RSA key pair with size 1024 bits...")
        mock_print.assert_any_call("Saving private key to test_private.pem")
        mock_print.assert_any_call("Saving public key to test_public.pem")
        mock_print.assert_any_call("Key pair generated and saved successfully!")
        
        # Verify files were opened for writing
        assert mock_file.call_count == 2


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_end_to_end_workflow(self, tmp_path):
        """Test complete end-to-end workflow."""
        # Generate and save keys
        private_key = generate_key_pair(key_size=1024)
        private_pem, public_pem = pem_encode_key(private_key)
        
        private_path = tmp_path / "private.pem"
        public_path = tmp_path / "public.pem"
        
        save_key_pair(private_pem, public_pem, str(private_path), str(public_path))
        
        # Sign data using segment
        sign_segment = SignSegment(
            str(private_path), 
            message_field="message", 
            append_as="signature"
        )
        
        data = [
            {"message": "Hello, world!", "id": 1},
            {"message": "Another message", "id": 2}
        ]
        
        signed_data = list(sign_segment.transform(data))
        
        # Verify signatures using segment
        verify_segment = VerifySegment(
            str(public_path),
            message_field="message",
            signature_field="signature",
            append_as="verified"
        )
        
        verified_data = list(verify_segment.transform(signed_data))
        
        # Check results
        assert len(verified_data) == 2
        for item in verified_data:
            assert item["verified"] is True
            assert "signature" in item
            assert "message" in item
            assert "id" in item
            
    def test_tampered_data_detection(self, tmp_path):
        """Test that tampered data is detected."""
        # Generate keys
        private_key = generate_key_pair(key_size=1024)
        public_key = private_key.public_key()
        
        # Sign original data
        original_data = {"message": "Original message", "id": 1}
        sign_segment = SignSegment(
            private_key, 
            message_field="message", 
            append_as="signature"
        )
        
        signed_data = list(sign_segment.transform([original_data]))[0]
        
        # Tamper with the message
        signed_data["message"] = "Tampered message"
        
        # Verify (should fail)
        verify_segment = VerifySegment(
            public_key,
            message_field="message",
            signature_field="signature",
            append_as="verified"
        )
        
        verified_data = list(verify_segment.transform([signed_data]))[0]
        
        assert verified_data["verified"] is False