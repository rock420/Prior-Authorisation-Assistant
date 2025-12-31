"""
Medical Database tools for NCD/LCD lookups and code validation.

This module provides tools to check medical necessity criteria, validate
CPT/ICD code pairs, and retrieve coverage determination information.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

_DATA_DIR = Path(__file__).parent.parent.parent / "data"



class ProcedureDetail(BaseModel):
    """Details about a medical procedure from NCD/LCD database."""
    code: str = Field(..., description="CPT/HCPCS code")
    description: str = Field(..., description="Procedure description")
    lcd_reference: Optional[str] = Field(None, description="Local Coverage Determination reference")
    ncd_reference: Optional[str] = Field(None, description="National Coverage Determination reference")
    medical_necessity_criteria: List[str] = Field(default_factory=list)
    required_documentation: List[str] = Field(default_factory=list)


class DrugDetail(BaseModel):
    """Details about a specialty drug from coverage database."""
    code: str = Field(..., description="HCPCS/J-code")
    drug_name: str = Field(..., description="Drug name")
    description: str = Field(..., description="Drug description")
    lcd_reference: Optional[str] = Field(None)
    medical_necessity_criteria: List[str] = Field(default_factory=list)
    step_therapy_required: bool = Field(default=False)
    step_therapy_requirements: List[str] = Field(default_factory=list)
    required_documentation: List[str] = Field(default_factory=list)
    covered_indications: List[str] = Field(default_factory=list)


class CodeValidationResult(BaseModel):
    """Result of CPT/ICD code pair validation."""
    cpt_code: str
    icd_code: str
    is_valid: bool
    linkage_status: str
    reason: str
    lcd_reference: Optional[str] = None


def _load_medical_data() -> dict:
    """Load medical coverage data from JSON file."""
    with open(_DATA_DIR / "medical_coverage_db.json") as f:
        return json.load(f)


def _get_procedures() -> Dict[str, ProcedureDetail]:
    """Get procedures dict, converting from JSON."""
    data = _load_medical_data()
    return {code: ProcedureDetail(**proc) for code, proc in data["procedures"].items()}


def _get_drugs() -> Dict[str, DrugDetail]:
    """Get drugs dict, converting from JSON."""
    data = _load_medical_data()
    return {code: DrugDetail(**drug) for code, drug in data["drugs"].items()}


def _get_valid_linkages() -> Dict[tuple, str]:
    """Get valid linkages dict, converting pipe-separated keys to tuples."""
    data = _load_medical_data()
    return {
        tuple(key.split("|")): value for key, value in data["valid_linkages"].items()
    }

@tool
async def get_procedure_details(codes: List[str]) -> List[ProcedureDetail]:
    """Checks NCD/LCD database to fetch details about medical procedures.
    Returns medical necessity criteria and required documentation.

    Args:
        codes: List of CPT/HCPCS codes to look up.
    """
    procedures = _get_procedures()
    results = []
    for code in codes:
        if code in procedures:
            results.append(procedures[code])
        else:
            results.append(
                ProcedureDetail(
                    code=code,
                    description="Unknown procedure",
                    medical_necessity_criteria=[],
                    required_documentation=[],
                )
            )
    return results


@tool
async def get_drug_coverage_details(codes: List[str]) -> List[DrugDetail]:
    """Checks coverage database for specialty drug information.
    Returns step therapy requirements and required documentation.

    Args:
        codes: List of HCPCS/J-codes to look up.
    """
    drugs = _get_drugs()
    results = []
    for code in codes:
        if code in drugs:
            results.append(drugs[code])
        else:
            results.append(
                DrugDetail(
                    code=code,
                    drug_name="Unknown drug",
                    description="Not found in database",
                    step_therapy_required=False,
                    covered_indications=[],
                    medical_necessity_criteria=[],
                    step_therapy_requirements=[],
                    required_documentation=[],
                )
            )
    return results


@tool
async def validate_codes(cpt: str, icd: str) -> CodeValidationResult:
    """Checks NCD/LCD database for CPT/ICD code pair validity.

    Args:
        cpt: CPT/HCPCS Code
        icd: ICD-10 Diagnosis Code
    """
    procedures = _get_procedures()
    drugs = _get_drugs()
    valid_linkages = _get_valid_linkages()
    linkage_key = (cpt, icd)

    if linkage_key in valid_linkages:
        lcd_ref = None
        if cpt in procedures:
            lcd_ref = procedures[cpt].lcd_reference
        elif cpt in drugs:
            lcd_ref = drugs[cpt].lcd_reference

        return CodeValidationResult(
            cpt_code=cpt,
            icd_code=icd,
            is_valid=True,
            linkage_status="valid",
            reason=valid_linkages[linkage_key],
            lcd_reference=lcd_ref,
        )

    if cpt in procedures:
        return CodeValidationResult(
            cpt_code=cpt,
            icd_code=icd,
            is_valid=False,
            linkage_status="invalid",
            reason=f"Diagnosis {icd} may not support procedure {cpt}",
            lcd_reference=procedures[cpt].lcd_reference,
        )

    if cpt in drugs:
        return CodeValidationResult(
            cpt_code=cpt,
            icd_code=icd,
            is_valid=False,
            linkage_status="invalid",
            reason=f"Diagnosis {icd} may not be covered for {cpt}",
            lcd_reference=drugs[cpt].lcd_reference,
        )

    return CodeValidationResult(
        cpt_code=cpt,
        icd_code=icd,
        is_valid=False,
        linkage_status="unknown",
        reason=f"Code {cpt} not found in database",
        lcd_reference=None,
    )


@tool
async def check_step_therapy_requirements(drug_code: str, diagnosis_code: str) -> dict:
    """Check step therapy requirements for a specialty drug.

    Args:
        drug_code: HCPCS/J-code for the drug
        diagnosis_code: ICD-10 diagnosis code
    """
    drugs = _get_drugs()
    valid_linkages = _get_valid_linkages()

    if drug_code not in drugs:
        return {
            "drug_code": drug_code,
            "found": False,
            "step_therapy_required": False,
            "message": f"Drug {drug_code} not found",
        }

    drug = drugs[drug_code]
    linkage_key = (drug_code, diagnosis_code)
    is_covered = linkage_key in valid_linkages

    return {
        "drug_code": drug_code,
        "drug_name": drug.drug_name,
        "found": True,
        "diagnosis_code": diagnosis_code,
        "is_covered_indication": is_covered,
        "step_therapy_required": drug.step_therapy_required,
        "step_therapy_requirements": drug.step_therapy_requirements,
        "required_documentation": drug.required_documentation,
        "medical_necessity_criteria": drug.medical_necessity_criteria,
    }
