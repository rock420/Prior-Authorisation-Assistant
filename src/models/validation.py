"""Validation utilities and custom validators for PA Healthcare Agent."""

import re
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
from pydantic import ValidationError


class ValidationUtils:
    """Utility class for data validation and sanitization."""
    
    # Regex patterns for common validations
    NPI_PATTERN = re.compile(r'^\d{10}$')
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    CPT_PATTERN = re.compile(r'^[A-Z]?\d{4,5}$')
    HCPCS_PATTERN = re.compile(r'^[A-Z]\d{4}$')
    ICD10_PATTERN = re.compile(r'^[A-Z]\d{2}(\.[A-Z0-9]{1,4})?$')
    ZIP_CODE_PATTERN = re.compile(r'^\d{5}(-\d{4})?$')
    
    @classmethod
    def sanitize_string(cls, value: str) -> str:
        """Sanitize string input by trimming whitespace and normalizing."""
        if not isinstance(value, str):
            return str(value)
        return value.strip()
    
    @classmethod
    def sanitize_phone(cls, phone: str) -> str:
        """Sanitize phone number by removing formatting characters."""
        if not phone:
            return phone
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        return digits_only
    
    @classmethod
    def validate_npi(cls, npi: str) -> bool:
        """Validate National Provider Identifier format."""
        if not npi:
            return False
        return bool(cls.NPI_PATTERN.match(npi))
    
    @classmethod
    def validate_phone(cls, phone: str) -> bool:
        """Validate phone number format (must have 10 digits)."""
        if not phone:
            return False
        sanitized = cls.sanitize_phone(phone)
        return len(sanitized) == 10
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email address format."""
        if not email:
            return False
        return bool(cls.EMAIL_PATTERN.match(email))
    
    @classmethod
    def validate_cpt_code(cls, code: str) -> bool:
        """Validate CPT code format (5 digits)."""
        if not code:
            return False
        return bool(cls.CPT_PATTERN.match(code))
    
    @classmethod
    def validate_hcpcs_code(cls, code: str) -> bool:
        """Validate HCPCS code format (letter followed by 4 digits)."""
        if not code:
            return False
        return bool(cls.HCPCS_PATTERN.match(code))
    
    @classmethod
    def validate_icd10_code(cls, code: str) -> bool:
        """Validate ICD-10 code format."""
        if not code:
            return False
        return bool(cls.ICD10_PATTERN.match(code))
    
    @classmethod
    def validate_zip_code(cls, zip_code: str) -> bool:
        """Validate ZIP code format (5 digits or 5+4 format)."""
        if not zip_code:
            return False
        return bool(cls.ZIP_CODE_PATTERN.match(zip_code))
    
    @classmethod
    def validate_date_range(cls, start_date: datetime, end_date: datetime) -> bool:
        """Validate that end date is after start date."""
        if not start_date or not end_date:
            return False
        return end_date >= start_date
    
    @classmethod
    def validate_required_fields(cls, data: Dict[str, Any], required_fields: List[str]) -> List[str]:
        """Validate that all required fields are present and non-empty."""
        missing_fields = []
        for field in required_fields:
            if field not in data or not data[field]:
                missing_fields.append(field)
        return missing_fields
    
    @classmethod
    def validate_address_completeness(cls, address: Dict[str, str]) -> List[str]:
        """Validate that address contains all required fields."""
        required_fields = ['street', 'city', 'state', 'zip_code']
        return cls.validate_required_fields(address, required_fields)
    
    @classmethod
    def validate_medical_codes(cls, codes: List[str], code_type: str) -> List[str]:
        """Validate a list of medical codes based on type."""
        invalid_codes = []
        
        for code in codes:
            if not code or not code.strip():
                invalid_codes.append(f"Empty {code_type} code")
                continue
                
            code = code.strip().upper()
            
            if code_type.lower() == 'cpt':
                if not cls.validate_cpt_code(code):
                    invalid_codes.append(code)
            elif code_type.lower() == 'hcpcs':
                if not cls.validate_hcpcs_code(code):
                    invalid_codes.append(code)
            elif code_type.lower() == 'icd10':
                if not cls.validate_icd10_code(code):
                    invalid_codes.append(code)
        
        return invalid_codes

